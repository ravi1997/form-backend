import pytest
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from schemas.form import FormSchema
from services.form_service import FormService


def test_form_schema_accepts_submission_settings_and_defaults_redirect_state():
    form = FormSchema(
        title="Submission Contract",
        slug="submission-contract",
        organization_id="org-1",
        created_by="user-1",
        submission_settings={
            "confirmation_message": "Thanks for submitting",
            "redirect_after_submit": True,
            "redirect_url": "https://example.com/thanks",
            "allow_multiple_submissions": True,
            "save_and_resume": True,
            "draft_handling": {"mode": "auto"},
        },
    )

    assert form.submission_settings.confirmation_message == "Thanks for submitting"
    assert form.submission_settings.redirect_after_submit is True
    assert form.submission_settings.redirect_url == "https://example.com/thanks"
    assert form.submission_settings.allow_multiple_submissions is True
    assert form.submission_settings.save_and_resume is True
    assert form.submission_settings.draft_handling == {"mode": "auto"}


def test_submission_settings_rejects_redirect_without_url():
    with pytest.raises(ValidationError):
        FormSchema(
            title="Invalid Submission Contract",
            slug="invalid-submission-contract",
            organization_id="org-1",
            created_by="user-1",
            submission_settings={"redirect_after_submit": True},
        )


def test_sync_form_canvas_persists_submission_settings_without_clearing_sections():
    service = FormService()
    mock_form = MagicMock()
    mock_form.id = "form-1"
    mock_form.organization_id = "org-1"
    mock_form.sections = ["existing-section"]
    mock_form.submission_settings = None
    mock_form.save = MagicMock()

    mock_query = MagicMock()
    mock_query.first.return_value = mock_form

    with patch("services.form_service.Form.objects", return_value=mock_query), patch(
        "services.form_service.FormService.sync_draft_version"
    ) as sync_draft_version:
        sync_draft_version.return_value = MagicMock()

        updated = service.sync_form_canvas(
            "form-1",
            "org-1",
            {
                "submission_settings": {
                    "confirmation_message": "Thanks",
                    "redirect_after_submit": False,
                    "allow_multiple_submissions": False,
                    "save_and_resume": False,
                }
            },
        )

    assert updated is mock_form
    assert mock_form.sections == ["existing-section"]
    assert mock_form.submission_settings == {
        "confirmation_message": "Thanks",
        "redirect_after_submit": False,
        "allow_multiple_submissions": False,
        "save_and_resume": False,
    }
    mock_form.save.assert_called()
    sync_draft_version.assert_called_once_with("form-1", "org-1")


def test_build_draft_snapshot_includes_submission_settings():
    service = FormService()
    mock_form = MagicMock()
    mock_form.sections = []
    mock_form.translations = {}
    mock_form.workflows = {"submission": {"mode": "auto"}}
    mock_form.submission_settings = {
        "confirmation_message": "Thanks",
        "allow_multiple_submissions": True,
    }

    snapshot = service._build_draft_snapshot(mock_form)

    assert snapshot["sections"] == []
    assert snapshot["translations"] == {}
    assert snapshot["workflows"] == {"submission": {"mode": "auto"}}
    assert snapshot["submission_settings"] == {
        "confirmation_message": "Thanks",
        "allow_multiple_submissions": True,
    }


def test_update_form_routes_submission_settings_through_canvas_sync(app):
    from routes.v1.form.form import update_form

    form_id = "12345678-1234-5678-1234-567812345678"
    existing_form = MagicMock()
    existing_form.model_dump.return_value = {
        "title": "Submission Contract",
        "slug": "submission-contract",
        "organization_id": "org-1",
        "created_by": "user-1",
        "status": "draft",
        "ui_type": "flex",
        "sections": [],
        "submission_settings": None,
    }

    updated_form = MagicMock()
    updated_form.id = form_id
    mock_user = MagicMock(organization_id="org-1")

    with app.test_request_context(
        f"/mahasangraha/api/v1/forms/{form_id}",
        method="PUT",
        json={
            "submission_settings": {
                "confirmation_message": "Thanks",
                "allow_multiple_submissions": True,
            }
        },
    ), patch(
        "flask_jwt_extended.view_decorators.verify_jwt_in_request"
    ), patch(
        "utils.security_helpers.verify_jwt_in_request"
    ), patch(
        "utils.security_helpers.get_current_user", return_value=mock_user
    ), patch(
        "utils.security_helpers.Form.objects"
    ) as security_form_objects, patch(
        "utils.security_helpers.AccessControlService.check_form_permission",
        return_value=True,
    ), patch(
        "routes.v1.form.form.get_current_user", return_value=mock_user
    ), patch(
        "routes.v1.form.form.form_service.get_by_id", return_value=existing_form
    ), patch(
        "routes.v1.form.form.form_service.sync_form_canvas",
        return_value=updated_form,
    ) as sync_form_canvas, patch(
        "routes.v1.form.form.form_service.update"
    ) as form_update:
        security_form_objects.return_value.first.return_value = MagicMock()

        response, status = update_form(form_id=form_id)

    assert status == 200
    assert response.get_json()["success"] is True
    assert response.get_json()["data"]["form_id"] == form_id
    sync_form_canvas.assert_called_once()
    form_update.assert_not_called()
