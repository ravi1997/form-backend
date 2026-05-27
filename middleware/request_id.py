import uuid
import json
from pprint import pformat
from flask import request, g
from logger.unified_logger import app_logger, access_logger


def _sanitize_headers(headers):
    return {
        key: ("[MASKED]" if key.lower() == "authorization" else value)
        for key, value in headers.items()
    }


def _safe_body_preview(body):
    if body is None:
        return None
    if isinstance(body, bytes):
        try:
            body = body.decode("utf-8")
        except Exception:
            return "[binary body]"
    return body


def _pretty_body(body):
    if body is None:
        return None
    if isinstance(body, (dict, list)):
        return body
    if isinstance(body, str):
        stripped = body.strip()
        if not stripped:
            return body
        try:
            return json.loads(stripped)
        except Exception:
            return body
    return body


def _pretty_block(
    kind, method=None, path=None, status=None, headers=None, body=None, request_id=None
):
    payload = {
        "kind": kind,
        "request_id": request_id,
        "method": method,
        "path": path,
        "status": status,
        "headers": headers,
        "body": _pretty_body(body),
    }
    return json.dumps(payload, indent=4, sort_keys=False)


def setup_request_id(app):
    @app.before_request
    def add_request_id():
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        g.request_id = request_id
        g.log_sequence = 1
        g.request_body_preview = None
        g.request_headers_snapshot = _sanitize_headers(request.headers)

        if request.method not in {"GET", "HEAD"}:
            try:
                if request.is_json:
                    g.request_body_preview = _pretty_body(request.get_json(silent=True))
                else:
                    g.request_body_preview = _safe_body_preview(
                        request.get_data(as_text=True)
                    )
            except Exception:
                g.request_body_preview = "[unavailable]"

        access_logger.info(
            ">>> REQUEST >>>\n%s",
            _pretty_block(
                "request",
                method=request.method,
                path=request.path,
                headers=g.request_headers_snapshot,
                body=g.request_body_preview,
                request_id=request_id,
            ),
        )

    @app.after_request
    def log_request(response):
        # Optional: Add request ID to response headers
        request_id = getattr(g, "request_id", "unknown")
        response.headers["X-Request-ID"] = request_id

        response_headers = _sanitize_headers(response.headers)
        response_body = None
        try:
            if not response.direct_passthrough:
                response_body = _safe_body_preview(response.get_data(as_text=True))
        except Exception:
            response_body = "[unavailable]"

        g.log_sequence = 2

        access_logger.info(
            "<<< RESPONSE <<<\n%s",
            _pretty_block(
                "response",
                method=request.method,
                path=request.path,
                status=response.status_code,
                headers=response_headers,
                body=response_body,
                request_id=request_id,
            ),
        )
        return response
