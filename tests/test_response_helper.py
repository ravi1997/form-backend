from utils.response_helper import (
    BaseSerializer,
    FormSerializer,
    error_response,
    pagination_response,
    success_response,
)


def test_base_serializer_strips_meta_data_by_default():
    payload = {
        "id": "form-1",
        "meta_data": {"internal": True},
        "sections": [{"id": "section-1", "meta_data": {"startCollapsed": True}}],
    }

    serialized = BaseSerializer.clean_dict(payload)

    assert "meta_data" not in serialized
    assert "meta_data" not in serialized["sections"][0]


def test_form_serializer_preserves_builder_meta_data():
    payload = {
        "id": "form-1",
        "organization_id": "org-1",
        "versions": [
            {
                "version": "0.1.0",
                "sections": [
                    {
                        "id": "section-1",
                        "title": "General",
                        "meta_data": {"startCollapsed": True},
                    }
                ],
            }
        ],
    }

    serialized = FormSerializer.serialize(payload)

    assert "organization_id" not in serialized
    assert serialized["versions"][0]["sections"][0]["meta_data"] == {
        "startCollapsed": True
    }


def test_success_response_uses_canonical_envelope(app):
    with app.test_request_context(headers={"X-Request-ID": "req-123"}):
        from flask import g

        g.request_id = "req-123"
        response, status = success_response(
            data={"id": "1"}, message="Created", status_code=201
        )

    assert status == 201
    assert response.get_json() == {
        "success": True,
        "message": "Created",
        "request_id": "req-123",
        "data": {"id": "1"},
    }


def test_error_response_uses_structured_error(app):
    with app.test_request_context(headers={"X-Request-ID": "req-456"}):
        from flask import g

        g.request_id = "req-456"
        response, status = error_response(
            message="Invalid payload",
            status_code=422,
            field_errors={"title": ["required"]},
        )

    assert status == 422
    assert response.get_json() == {
        "success": False,
        "request_id": "req-456",
        "error": {
            "code": "VALIDATION_FAILED",
            "message": "Invalid payload",
            "field_errors": {"title": ["required"]},
        },
    }


def test_pagination_response_shape():
    assert pagination_response([{"id": "1"}], page=2, page_size=10, total=25) == {
        "items": [{"id": "1"}],
        "page": 2,
        "page_size": 10,
        "total": 25,
        "total_pages": 3,
        "has_next": True,
        "has_prev": True,
    }
