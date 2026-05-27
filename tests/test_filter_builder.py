"""
tests/test_filter_builder.py

Unit tests for FilterBuilderService.

All tests exercise the pure service layer and do not require a live MongoDB
connection or a running Flask application.

Run with:
    docker compose run --rm backend pytest tests/test_filter_builder.py -v
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch

from services.filter_builder_service import FilterBuilderService
from utils.exceptions import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ORG_ID = "org-abc-123"
FORM_ID = "form-xyz-456"


def build(filters):
    """Convenience wrapper."""
    return FilterBuilderService.build_mongo_query(
        filters=filters,
        organization_id=ORG_ID,
        form_id=FORM_ID,
    )


# ---------------------------------------------------------------------------
# Tenant Isolation – every query must always include org + form
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    def test_empty_filters_still_has_tenant_keys(self):
        q = build([])
        assert q["organization_id"] == ORG_ID
        assert q["form"] == FORM_ID
        assert q["is_deleted"] is False

    def test_string_filter_preserves_tenant_keys(self):
        q = build(
            [
                {
                    "field": "q-uuid-1",
                    "operator": "equals",
                    "value": "Male",
                    "field_type": "string",
                }
            ]
        )
        assert q["organization_id"] == ORG_ID
        assert q["form"] == FORM_ID

    def test_number_filter_preserves_tenant_keys(self):
        q = build(
            [
                {
                    "field": "q-uuid-2",
                    "operator": "gt",
                    "value": 25,
                    "field_type": "number",
                }
            ]
        )
        assert q["organization_id"] == ORG_ID
        assert q["form"] == FORM_ID

    def test_date_filter_preserves_tenant_keys(self):
        q = build(
            [
                {
                    "field": "submitted_at",
                    "operator": "between",
                    "value": ["2025-01-01", "2025-12-31"],
                    "field_type": "date",
                    "is_meta": True,
                }
            ]
        )
        assert q["organization_id"] == ORG_ID
        assert q["form"] == FORM_ID


# ---------------------------------------------------------------------------
# String operators
# ---------------------------------------------------------------------------


class TestStringOperators:
    def test_equals(self):
        q = build(
            [
                {
                    "field": "q1",
                    "operator": "equals",
                    "value": "Male",
                    "field_type": "string",
                }
            ]
        )
        cond = q["$and"][0]
        assert cond == {"data.q1": {"$eq": "Male"}}

    def test_not_equals(self):
        q = build(
            [
                {
                    "field": "q1",
                    "operator": "not_equals",
                    "value": "Female",
                    "field_type": "string",
                }
            ]
        )
        cond = q["$and"][0]
        assert cond == {"data.q1": {"$ne": "Female"}}

    def test_contains(self):
        q = build(
            [
                {
                    "field": "city",
                    "operator": "contains",
                    "value": "Delhi",
                    "field_type": "string",
                }
            ]
        )
        cond = q["$and"][0]
        assert "data.city" in cond
        assert "$regex" in cond["data.city"]
        assert "Delhi" in cond["data.city"]["$regex"]

    def test_starts_with(self):
        q = build(
            [
                {
                    "field": "city",
                    "operator": "starts_with",
                    "value": "New",
                    "field_type": "string",
                }
            ]
        )
        cond = q["$and"][0]
        assert cond["data.city"]["$regex"].startswith("^")

    def test_ends_with(self):
        q = build(
            [
                {
                    "field": "city",
                    "operator": "ends_with",
                    "value": "York",
                    "field_type": "string",
                }
            ]
        )
        cond = q["$and"][0]
        assert cond["data.city"]["$regex"].endswith("$")

    def test_in_list(self):
        q = build(
            [
                {
                    "field": "status",
                    "operator": "in",
                    "value": ["active", "pending"],
                    "field_type": "string",
                }
            ]
        )
        cond = q["$and"][0]
        assert cond["data.status"]["$in"] == ["active", "pending"]

    def test_not_in_list(self):
        q = build(
            [
                {
                    "field": "status",
                    "operator": "not_in",
                    "value": ["deleted"],
                    "field_type": "string",
                }
            ]
        )
        cond = q["$and"][0]
        assert "$nin" in cond["data.status"]

    def test_is_empty(self):
        q = build(
            [
                {
                    "field": "notes",
                    "operator": "is_empty",
                    "value": None,
                    "field_type": "string",
                }
            ]
        )
        cond = q["$and"][0]
        assert "$or" in cond

    def test_is_not_empty(self):
        q = build(
            [
                {
                    "field": "notes",
                    "operator": "is_not_empty",
                    "value": None,
                    "field_type": "string",
                }
            ]
        )
        cond = q["$and"][0]
        assert "$exists" in cond["data.notes"]


# ---------------------------------------------------------------------------
# Number operators
# ---------------------------------------------------------------------------


class TestNumberOperators:
    def test_gt(self):
        q = build(
            [{"field": "age", "operator": "gt", "value": 25, "field_type": "number"}]
        )
        cond = q["$and"][0]
        assert cond == {"data.age": {"$gt": 25.0}}

    def test_gte(self):
        q = build(
            [{"field": "age", "operator": "gte", "value": 18, "field_type": "number"}]
        )
        assert q["$and"][0] == {"data.age": {"$gte": 18.0}}

    def test_lt(self):
        q = build(
            [{"field": "score", "operator": "lt", "value": 50, "field_type": "number"}]
        )
        assert q["$and"][0] == {"data.score": {"$lt": 50.0}}

    def test_lte(self):
        q = build(
            [
                {
                    "field": "score",
                    "operator": "lte",
                    "value": 100,
                    "field_type": "number",
                }
            ]
        )
        assert q["$and"][0] == {"data.score": {"$lte": 100.0}}

    def test_equals(self):
        q = build(
            [
                {
                    "field": "count",
                    "operator": "equals",
                    "value": 5,
                    "field_type": "number",
                }
            ]
        )
        assert q["$and"][0] == {"data.count": {"$eq": 5.0}}

    def test_not_equals(self):
        q = build(
            [
                {
                    "field": "count",
                    "operator": "not_equals",
                    "value": 0,
                    "field_type": "number",
                }
            ]
        )
        assert q["$and"][0] == {"data.count": {"$ne": 0.0}}

    def test_between(self):
        q = build(
            [
                {
                    "field": "age",
                    "operator": "between",
                    "value": [18, 65],
                    "field_type": "number",
                }
            ]
        )
        cond = q["$and"][0]
        assert cond == {"data.age": {"$gte": 18.0, "$lte": 65.0}}

    def test_between_requires_two_element_list(self):
        with pytest.raises(ValidationError):
            build(
                [
                    {
                        "field": "age",
                        "operator": "between",
                        "value": [18],
                        "field_type": "number",
                    }
                ]
            )


# ---------------------------------------------------------------------------
# Date operators
# ---------------------------------------------------------------------------


class TestDateOperators:
    def test_before(self):
        q = build(
            [
                {
                    "field": "submitted_at",
                    "operator": "before",
                    "value": "2025-06-01",
                    "field_type": "date",
                    "is_meta": True,
                }
            ]
        )
        cond = q["$and"][0]
        assert "$lt" in cond["submitted_at"]
        assert isinstance(cond["submitted_at"]["$lt"], datetime)

    def test_after(self):
        q = build(
            [
                {
                    "field": "submitted_at",
                    "operator": "after",
                    "value": "2025-01-01",
                    "field_type": "date",
                    "is_meta": True,
                }
            ]
        )
        cond = q["$and"][0]
        assert "$gt" in cond["submitted_at"]

    def test_equals(self):
        q = build(
            [
                {
                    "field": "submitted_at",
                    "operator": "equals",
                    "value": "2025-03-15T00:00:00Z",
                    "field_type": "date",
                    "is_meta": True,
                }
            ]
        )
        cond = q["$and"][0]
        assert "$eq" in cond["submitted_at"]

    def test_between_date(self):
        q = build(
            [
                {
                    "field": "submitted_at",
                    "operator": "between",
                    "value": ["2025-01-01", "2025-12-31"],
                    "field_type": "date",
                    "is_meta": True,
                }
            ]
        )
        cond = q["$and"][0]
        assert "$gte" in cond["submitted_at"]
        assert "$lte" in cond["submitted_at"]
        assert isinstance(cond["submitted_at"]["$gte"], datetime)
        assert isinstance(cond["submitted_at"]["$lte"], datetime)

    def test_invalid_date_raises(self):
        with pytest.raises(ValidationError):
            build(
                [
                    {
                        "field": "submitted_at",
                        "operator": "before",
                        "value": "not-a-date",
                        "field_type": "date",
                        "is_meta": True,
                    }
                ]
            )


# ---------------------------------------------------------------------------
# Boolean operators
# ---------------------------------------------------------------------------


class TestBooleanOperators:
    def test_equals_true(self):
        q = build(
            [
                {
                    "field": "is_draft",
                    "operator": "equals",
                    "value": True,
                    "field_type": "boolean",
                    "is_meta": True,
                }
            ]
        )
        cond = q["$and"][0]
        assert cond == {"is_draft": {"$eq": True}}

    def test_equals_false(self):
        q = build(
            [
                {
                    "field": "is_draft",
                    "operator": "equals",
                    "value": False,
                    "field_type": "boolean",
                    "is_meta": True,
                }
            ]
        )
        cond = q["$and"][0]
        assert cond == {"is_draft": {"$eq": False}}

    def test_non_bool_value_raises(self):
        with pytest.raises(ValidationError):
            build(
                [
                    {
                        "field": "is_draft",
                        "operator": "equals",
                        "value": "yes",
                        "field_type": "boolean",
                        "is_meta": True,
                    }
                ]
            )


# ---------------------------------------------------------------------------
# MongoDB Key Mapping
# ---------------------------------------------------------------------------


class TestKeyMapping:
    def test_regular_field_prefixed_with_data(self):
        q = build(
            [
                {
                    "field": "q-uuid-999",
                    "operator": "equals",
                    "value": "x",
                    "field_type": "string",
                }
            ]
        )
        cond = q["$and"][0]
        key = list(cond.keys())[0]
        assert key == "data.q-uuid-999"

    def test_meta_field_not_prefixed(self):
        q = build(
            [
                {
                    "field": "submitted_at",
                    "operator": "before",
                    "value": "2025-01-01",
                    "field_type": "date",
                    "is_meta": True,
                }
            ]
        )
        cond = q["$and"][0]
        assert "submitted_at" in cond
        assert "data.submitted_at" not in cond

    def test_disallowed_meta_field_raises(self):
        with pytest.raises(ValidationError, match="allowed list"):
            build(
                [
                    {
                        "field": "password_hash",
                        "operator": "equals",
                        "value": "secret",
                        "field_type": "string",
                        "is_meta": True,
                    }
                ]
            )


# ---------------------------------------------------------------------------
# Security – Injection Rejection
# ---------------------------------------------------------------------------


class TestInjectionRejection:
    def test_field_with_dollar_sign_rejected(self):
        with pytest.raises(ValidationError):
            build(
                [
                    {
                        "field": "$where",
                        "operator": "equals",
                        "value": "1==1",
                        "field_type": "string",
                    }
                ]
            )

    def test_field_with_dot_rejected(self):
        """Field names with arbitrary dots must be rejected at input."""
        with pytest.raises(ValidationError):
            build(
                [
                    {
                        "field": "field.with.dots",
                        "operator": "equals",
                        "value": "bad",
                        "field_type": "string",
                    }
                ]
            )

    def test_value_with_dollar_sign_rejected(self):
        with pytest.raises(ValidationError):
            build(
                [
                    {
                        "field": "name",
                        "operator": "equals",
                        "value": "$ne",
                        "field_type": "string",
                    }
                ]
            )

    def test_list_value_with_dollar_sign_rejected(self):
        with pytest.raises(ValidationError):
            build(
                [
                    {
                        "field": "tags",
                        "operator": "in",
                        "value": ["ok", "$where"],
                        "field_type": "string",
                    }
                ]
            )

    def test_unknown_operator_rejected(self):
        with pytest.raises(ValidationError):
            build(
                [
                    {
                        "field": "name",
                        "operator": "hack_op",
                        "value": "foo",
                        "field_type": "string",
                    }
                ]
            )

    def test_unknown_field_type_rejected(self):
        with pytest.raises(ValidationError):
            build(
                [
                    {
                        "field": "name",
                        "operator": "equals",
                        "value": "foo",
                        "field_type": "js_code",
                    }
                ]
            )

    def test_operator_mismatch_rejected(self):
        """Using a number-only operator on a string field must be rejected."""
        with pytest.raises(ValidationError):
            build(
                [
                    {
                        "field": "name",
                        "operator": "gt",
                        "value": "foo",
                        "field_type": "string",
                    }
                ]
            )


# ---------------------------------------------------------------------------
# Multiple filters produce an $and array
# ---------------------------------------------------------------------------


class TestMultipleFilters:
    def test_multiple_filters_produce_and(self):
        q = build(
            [
                {
                    "field": "q1",
                    "operator": "equals",
                    "value": "Male",
                    "field_type": "string",
                },
                {"field": "q2", "operator": "gt", "value": 25, "field_type": "number"},
            ]
        )
        assert "$and" in q
        assert len(q["$and"]) == 2

    def test_and_conditions_are_correct(self):
        q = build(
            [
                {
                    "field": "q1",
                    "operator": "equals",
                    "value": "A",
                    "field_type": "string",
                },
                {"field": "q2", "operator": "gte", "value": 10, "field_type": "number"},
            ]
        )
        conds = q["$and"]
        keys = [list(c.keys())[0] for c in conds]
        assert "data.q1" in keys
        assert "data.q2" in keys
