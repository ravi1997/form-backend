"""
services/filter_builder_service.py

Converts a structured visual filter array (from the dashboard widget engine or
the response list endpoint) into a safe, tenant-scoped MongoDB query dictionary
compatible with MongoEngine's `FormResponse.objects(**query)` / `__raw__` syntax.

Security invariants:
  - Every MongoDB key built here is derived from an allow-list of meta field names
    or from a sanitised question-ID that is verified to contain no `$` or `.`.
  - Values are never eval'd or injected into JS; they are wrapped in typed Python
    structures that PyMongo serialises safely.
  - Any suspicious field or value raises ValidationError immediately.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from logger.unified_logger import error_logger
from utils.exceptions import ValidationError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Operators supported per field type (used in Pydantic validation)
_ALLOWED_OPERATORS: dict[str, set[str]] = {
    "string": {
        "equals",
        "not_equals",
        "contains",
        "starts_with",
        "ends_with",
        "in",
        "not_in",
        "is_empty",
        "is_not_empty",
    },
    "number": {"equals", "not_equals", "gt", "gte", "lt", "lte", "between"},
    "date": {"equals", "before", "after", "between"},
    "boolean": {"equals"},
}

# Allowed meta field names – these map directly to top-level document fields.
_ALLOWED_META_FIELDS: set[str] = {
    "submitted_at",
    "status",
    "review_status",
    "is_draft",
    "organization_id",
    "form",
}

# Regex that a question-ID field must satisfy (UUID-like or safe alphanumeric/dash)
_SAFE_FIELD_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")

# Detects MongoDB operators embedded in strings
_MONGO_OP_RE = re.compile(r"\$")


# ---------------------------------------------------------------------------
# Pydantic schema for a single filter rule
# ---------------------------------------------------------------------------


class FilterRule(BaseModel):
    """Strict schema for one entry in the filter array."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    field: str
    operator: str
    value: Optional[Any] = None  # None is valid for is_empty / is_not_empty
    field_type: str
    is_meta: bool = False

    # ── Security: reject `$` in field names ──────────────────────────────
    @field_validator("field")
    @classmethod
    def _validate_field(cls, v: str) -> str:
        if _MONGO_OP_RE.search(v):
            raise ValueError(f"Field name contains forbidden character '$': {v!r}")
        if "." in v and not v.startswith("data."):
            # Dot notation is only allowed internally; raw field input must not contain it
            raise ValueError(f"Field name must not contain '.': {v!r}")
        if not _SAFE_FIELD_RE.match(v):
            raise ValueError(
                f"Field name contains invalid characters: {v!r}. "
                "Only alphanumerics, underscores, and hyphens are allowed."
            )
        return v

    # ── Validate field_type ───────────────────────────────────────────────
    @field_validator("field_type")
    @classmethod
    def _validate_field_type(cls, v: str) -> str:
        if v not in _ALLOWED_OPERATORS:
            raise ValueError(
                f"Unsupported field_type {v!r}. Allowed: {sorted(_ALLOWED_OPERATORS)}"
            )
        return v

    # ── Validate operator against field_type ──────────────────────────────
    @model_validator(mode="after")
    def _validate_operator(self) -> "FilterRule":
        allowed = _ALLOWED_OPERATORS.get(self.field_type, set())
        if self.operator not in allowed:
            raise ValueError(
                f"Operator {self.operator!r} is not valid for field_type "
                f"{self.field_type!r}. Allowed: {sorted(allowed)}"
            )
        return self

    # ── Security: reject `$` in string values ────────────────────────────
    @field_validator("value", mode="before")
    @classmethod
    def _validate_value(cls, v: Any) -> Any:
        if isinstance(v, str) and _MONGO_OP_RE.search(v):
            raise ValueError(
                f"Value contains forbidden MongoDB operator character '$': {v!r}"
            )
        if isinstance(v, list):
            for item in v:
                if isinstance(item, str) and _MONGO_OP_RE.search(item):
                    raise ValueError(
                        f"List value contains forbidden MongoDB operator '$': {item!r}"
                    )
        return v


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FilterBuilderService:
    """
    Converts a list of FilterRule dicts into a MongoDB query dict that is:
      - Always scoped to the given organization_id and form_id (tenant isolation)
      - Free of NoSQL injection vectors
      - Compatible with ``FormResponse.objects(__raw__={...})``
    """

    @classmethod
    def build_mongo_query(
        cls,
        filters: List[dict],
        organization_id: str,
        form_id: str,
    ) -> dict:
        """
        Build and return a MongoDB query dict.

        Parameters
        ----------
        filters:
            List of raw filter dicts from the API body.
        organization_id:
            The caller's organisation – always included in the returned query.
        form_id:
            The target form – always included in the returned query.

        Returns
        -------
        dict
            A raw MongoDB query dict ready for ``FormResponse.objects(__raw__=...)``.

        Raises
        ------
        ValidationError
            If any filter rule is invalid or contains injection patterns.
        """
        # ── Tenant-isolation base ─────────────────────────────────────────
        query: dict[str, Any] = {
            "organization_id": organization_id,
            "form": form_id,
            "is_deleted": False,
        }

        if not filters:
            return query

        and_conditions: list[dict] = []

        for raw in filters:
            try:
                rule = FilterRule(**raw)
            except Exception as exc:
                error_logger.error(
                    "FilterBuilderService: invalid filter rule %r – %s",
                    raw,
                    exc,
                    exc_info=False,
                )
                raise ValidationError(
                    f"Invalid filter rule: {exc}",
                    details={"rule": raw},
                ) from exc

            condition = cls._build_condition(rule)
            if condition:
                and_conditions.append(condition)

        if and_conditions:
            query["$and"] = and_conditions

        return query

    # ── Internal helpers ─────────────────────────────────────────────────

    @classmethod
    def _mongo_key(cls, rule: FilterRule) -> str:
        """Return the MongoDB document key for the rule."""
        if rule.is_meta:
            if rule.field not in _ALLOWED_META_FIELDS:
                raise ValidationError(
                    f"Meta field {rule.field!r} is not in the allowed list.",
                    details={"field": rule.field},
                )
            return rule.field
        # Regular question field – stored under data.<question_id>
        return f"data.{rule.field}"

    @classmethod
    def _build_condition(cls, rule: FilterRule) -> Optional[dict]:
        """Translate one FilterRule into a MongoDB condition dict."""
        key = cls._mongo_key(rule)
        op = rule.operator
        val = rule.value

        # ── String operators ──────────────────────────────────────────────
        if rule.field_type == "string":
            return cls._string_condition(key, op, val)

        # ── Number operators ──────────────────────────────────────────────
        if rule.field_type == "number":
            return cls._number_condition(key, op, val)

        # ── Date operators ────────────────────────────────────────────────
        if rule.field_type == "date":
            return cls._date_condition(key, op, val)

        # ── Boolean operators ─────────────────────────────────────────────
        if rule.field_type == "boolean":
            if not isinstance(val, bool):
                raise ValidationError(
                    f"Boolean filter requires a bool value, got {type(val).__name__}",
                    details={"field": rule.field, "value": val},
                )
            return {key: {"$eq": val}}

        return None  # unreachable due to Pydantic validation

    # ── String ────────────────────────────────────────────────────────────

    @staticmethod
    def _string_condition(key: str, op: str, val: Any) -> dict:
        if op == "equals":
            return {key: {"$eq": str(val)}}
        if op == "not_equals":
            return {key: {"$ne": str(val)}}
        if op == "contains":
            return {key: {"$regex": re.escape(str(val)), "$options": "i"}}
        if op == "starts_with":
            return {key: {"$regex": f"^{re.escape(str(val))}", "$options": "i"}}
        if op == "ends_with":
            return {key: {"$regex": f"{re.escape(str(val))}$", "$options": "i"}}
        if op == "in":
            if not isinstance(val, list):
                raise ValidationError(
                    "Operator 'in' requires a list value.", details={"field": key}
                )
            return {key: {"$in": [str(v) for v in val]}}
        if op == "not_in":
            if not isinstance(val, list):
                raise ValidationError(
                    "Operator 'not_in' requires a list value.", details={"field": key}
                )
            return {key: {"$nin": [str(v) for v in val]}}
        if op == "is_empty":
            return {
                "$or": [
                    {key: {"$exists": False}},
                    {key: None},
                    {key: ""},
                ]
            }
        if op == "is_not_empty":
            return {
                key: {
                    "$exists": True,
                    "$ne": None,
                    "$nin": [""],
                }
            }
        raise ValidationError(f"Unknown string operator: {op!r}")

    # ── Number ────────────────────────────────────────────────────────────

    @staticmethod
    def _number_condition(key: str, op: str, val: Any) -> dict:
        if op == "between":
            if not isinstance(val, list) or len(val) != 2:
                raise ValidationError(
                    "Operator 'between' requires a list of exactly [min, max].",
                    details={"field": key},
                )
            lo, hi = float(val[0]), float(val[1])
            return {key: {"$gte": lo, "$lte": hi}}

        numeric_val: float
        try:
            numeric_val = float(val)
        except (TypeError, ValueError):
            raise ValidationError(
                f"Numeric filter requires a numeric value, got {val!r}",
                details={"field": key},
            )

        op_map = {
            "equals": "$eq",
            "not_equals": "$ne",
            "gt": "$gt",
            "gte": "$gte",
            "lt": "$lt",
            "lte": "$lte",
        }
        mongo_op = op_map.get(op)
        if not mongo_op:
            raise ValidationError(f"Unknown number operator: {op!r}")
        return {key: {mongo_op: numeric_val}}

    # ── Date ──────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_date(raw: Any) -> datetime:
        """Parse an ISO 8601 date string into an aware UTC datetime."""
        if isinstance(raw, datetime):
            return raw.replace(tzinfo=timezone.utc) if raw.tzinfo is None else raw
        if isinstance(raw, str):
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                raise ValidationError(
                    f"Cannot parse date value: {raw!r}. Expected ISO 8601 format.",
                    details={"value": raw},
                )
        raise ValidationError(
            f"Date value must be a string or datetime, got {type(raw).__name__}",
            details={"value": raw},
        )

    @classmethod
    def _date_condition(cls, key: str, op: str, val: Any) -> dict:
        if op == "between":
            if not isinstance(val, list) or len(val) != 2:
                raise ValidationError(
                    "Operator 'between' requires a list of exactly [start, end].",
                    details={"field": key},
                )
            start = cls._parse_date(val[0])
            end = cls._parse_date(val[1])
            return {key: {"$gte": start, "$lte": end}}

        dt = cls._parse_date(val)
        op_map = {
            "equals": "$eq",
            "before": "$lt",
            "after": "$gt",
        }
        mongo_op = op_map.get(op)
        if not mongo_op:
            raise ValidationError(f"Unknown date operator: {op!r}")
        return {key: {mongo_op: dt}}
