from flask import g, jsonify
from datetime import datetime


class BaseSerializer:
    @staticmethod
    def clean_dict(data, preserve_fields=()):
        """Recursively removes internal mongo fields and stringifies UUIDs/Dates."""
        if isinstance(data, list):
            return [
                BaseSerializer.clean_dict(i, preserve_fields=preserve_fields)
                for i in data
            ]
        if not isinstance(data, dict):
            return data

        cleaned = {}
        preserve_fields = set(preserve_fields or ())
        # HARDENED: Expanded list of internal/sensitive fields to exclude
        EXCLUDE_FIELDS = (
            "_id",
            "_cls",
            "organization_id",
            "__v",
            "editors",
            "viewers",
            "submitters",  # ACL internals
            "snapshot_ref",
            "snapshot",  # Snapshot raw data (use resolved fields)
            "meta_data",
            "internal_metadata",  # Internal flags
            "password_hash",
            "salt",  # Security
        )

        for k, v in data.items():
            if k in EXCLUDE_FIELDS and k not in preserve_fields:
                continue

            # Key mapping
            if k == "id" or k == "_id":
                cleaned["id"] = str(v)
            elif isinstance(v, datetime):
                cleaned[k] = v.isoformat()
            elif isinstance(v, dict):
                cleaned[k] = BaseSerializer.clean_dict(
                    v, preserve_fields=preserve_fields
                )
            elif isinstance(v, list):
                cleaned[k] = [
                    BaseSerializer.clean_dict(i, preserve_fields=preserve_fields)
                    for i in v
                ]
            else:
                cleaned[k] = v
        return cleaned


class FormSerializer(BaseSerializer):
    @staticmethod
    def serialize(form_dict, include_snapshot=False):
        """Sanitizes form dictionary for public API output."""
        cleaned = BaseSerializer.clean_dict(form_dict, preserve_fields=("meta_data",))

        # Ensure versions are cleaned but don't leak full snapshot unless requested
        if "versions" in cleaned:
            for v in cleaned["versions"]:
                if not include_snapshot:
                    v.pop("snapshot", None)
                    v.pop("snapshot_data", None)
                elif "snapshot" in v:
                    v["snapshot"] = BaseSerializer.clean_dict(
                        v["snapshot"],
                        preserve_fields=("meta_data",),
                    )

        # Clean top-level snapshots if any leaked through
        cleaned.pop("snapshot", None)
        cleaned.pop("snapshot_data", None)

        return cleaned


def _request_id():
    return getattr(g, "request_id", None)


def success_response(data=None, message="Success", status_code=200):
    """
    Canonical successful response envelope.
    """
    response = {
        "success": True,
        "message": message,
        "request_id": _request_id(),
    }
    if data is not None:
        response["data"] = data

    return jsonify(response), status_code


def error_response(
    message="An error occurred",
    details=None,
    status_code=400,
    code=None,
    field_errors=None,
    retry_after=None,
):
    """
    Canonical error response envelope.
    """
    error = {
        "code": code or _default_error_code(status_code),
        "message": message,
    }
    if details is not None:
        error["details"] = details
    if field_errors is not None:
        error["field_errors"] = field_errors
    if retry_after is not None:
        error["retry_after"] = retry_after

    response = {
        "success": False,
        "error": error,
        "request_id": _request_id(),
    }

    return jsonify(response), status_code


def _default_error_code(status_code):
    return {
        400: "VALIDATION_FAILED",
        401: "AUTH_REQUIRED",
        403: "FORBIDDEN",
        404: "RESOURCE_NOT_FOUND",
        409: "CONFLICT",
        413: "PAYLOAD_TOO_LARGE",
        415: "UNSUPPORTED_MEDIA_TYPE",
        422: "VALIDATION_FAILED",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        502: "UPSTREAM_ERROR",
        503: "SERVICE_UNAVAILABLE",
        504: "UPSTREAM_TIMEOUT",
    }.get(status_code, "API_ERROR")


def pagination_response(items, page, page_size, total, **extra):
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    payload = {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
    payload.update(extra)
    return payload


def get_pagination_params():
    """
    Extracts pagination parameters from request query arguments.
    Enforces safe defaults and max limits defined in settings.
    """
    from flask import request
    from config.settings import settings

    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", settings.DEFAULT_PAGE_SIZE))
    except (ValueError, TypeError):
        page = 1
        page_size = settings.DEFAULT_PAGE_SIZE

    # Enforce safe bounds
    page = max(1, page)
    page_size = max(1, min(page_size, settings.MAX_PAGE_SIZE))

    return page, page_size
