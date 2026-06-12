from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID

from bson.binary import Binary, UuidRepresentation

from routes.v1.form.advanced_responses import fetch_same_form_data


def test_fetch_same_form_data_validates_input_and_returns_structured_matches(app):
    form_id = "11111111-1111-1111-1111-111111111111"

    with app.test_request_context(
        f"/mahasangraha/api/v1/forms/{form_id}/fetch/same?question_id=question-1"
    ), patch("flask_jwt_extended.view_decorators.verify_jwt_in_request"), patch(
        "utils.security_helpers.verify_jwt_in_request"
    ):
        response, status = fetch_same_form_data(form_id)

    assert status == 400
    assert response.get_json()["error"]["field_errors"] == {"value": ["required"]}

    mock_user = MagicMock(id="user-1", organization_id="org-1")
    form_uuid = UUID(form_id)
    expected_form_ref = Binary.from_uuid(
        form_uuid, uuid_representation=UuidRepresentation.PYTHON_LEGACY
    )

    form = MagicMock()
    form.id = form_uuid
    version = MagicMock()
    version.resolved_snapshot = {
        "sections": [
            {
                "id": "section-a",
                "questions": [
                    {"id": "question-1", "variable_name": "patient_id"}
                ],
            }
        ]
    }
    form.versions = [version]

    response_doc = MagicMock()
    response_doc.id = "response-1"
    response_doc.submitted_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    response_doc.submitted_by = "user-9"
    response_doc.status = "submitted"
    response_doc.review_status = "pending"
    response_doc.get_decrypted_data.return_value = {
        "section-a": {"patient_id": "EMP001", "name": "Jane Doe"}
    }

    response_query = MagicMock()
    response_query.order_by.return_value = response_query
    response_query.__iter__.return_value = iter([response_doc])

    with app.test_request_context(
        f"/mahasangraha/api/v1/forms/{form_id}/fetch/same?question_id=question-1&value=EMP001"
    ), patch("flask_jwt_extended.view_decorators.verify_jwt_in_request"), patch(
        "utils.security_helpers.verify_jwt_in_request"
    ), patch("routes.v1.form.advanced_responses.get_current_user", return_value=mock_user), patch(
        "routes.v1.form.advanced_responses.has_form_permission", return_value=True
    ), patch(
        "routes.v1.form.advanced_responses.Form.objects"
    ) as form_objects, patch(
        "routes.v1.form.advanced_responses.FormResponse.objects", return_value=response_query
    ) as response_objects:
        form_objects.get.return_value = form
        response, status = fetch_same_form_data(form_id)

    assert status == 200
    payload = response.get_json()["data"]
    assert payload["form_id"] == form_id
    assert payload["query"] == {"question_id": "question-1", "value": "EMP001"}
    assert payload["count"] == 1
    assert payload["items"][0]["response_metadata"] == {
        "response_id": "response-1",
        "submitted_at": "2026-01-02T03:04:05+00:00",
        "submitted_by": "user-9",
        "status": "submitted",
        "review_status": "pending",
    }
    assert payload["items"][0]["matched_data"] == [
        {
            "question_id": "question-1",
            "field_key": "patient_id",
            "path": ["section-a", "patient_id"],
            "value": "EMP001",
            "variable_name": "patient_id",
            "section_id": "section-a",
            "section_path": ["section-a"],
        }
    ]
    form_objects.get.assert_called_once_with(
        id=form_uuid,
        organization_id="org-1",
        is_deleted=False,
    )
    response_objects.assert_called_once_with(
        __raw__={
            "organization_id": "org-1",
            "form": expected_form_ref,
            "is_deleted": False,
        }
    )
