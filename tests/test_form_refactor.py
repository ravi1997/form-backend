import pytest
from unittest.mock import MagicMock, patch
from bson import DBRef
from services.form_validation_service import FormValidationService
from models.Form import Form, FormVersion

pytestmark = pytest.mark.usefixtures("db_connection")


def test_unified_validation_simple():
    # Mock Form and FormVersion
    mock_form = MagicMock()
    mock_form.id = "form1"
    mock_form.active_version_id = "v1"
    mock_form.organization_id = "org1"

    mock_version = MagicMock()
    mock_version.id = "v1"
    mock_version.resolved_snapshot = mock_version.snapshot = {
        "sections": [
            {
                "title": "General",
                "questions": [
                    {
                        "label": "Name",
                        "field_type": "input",
                        "variable_name": "name",
                        "validation": {"is_required": True},
                    }
                ],
            }
        ]
    }

    with patch("models.Form.Form.objects") as mock_form_objs, patch(
        "models.Form.FormVersion.objects"
    ) as mock_version_objs:

        mock_form_objs.return_value.first.return_value = mock_form
        mock_version_objs.return_value.first.return_value = mock_version
        mock_version_objs.return_value.order_by.return_value.first.return_value = (
            mock_version
        )

        # Validate - Missing required field
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1", payload={}, organization_id="org1"
        )
        assert not valid
        assert any(e["field"] == "name" for e in errors)

        # Validate - Success
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1", payload={"name": "John"}, organization_id="org1"
        )
        assert valid
        assert cleaned["name"] == "John"


def test_calculated_fields():
    mock_form = MagicMock(id="form1", active_version_id="v1", organization_id="org1")
    mock_version = MagicMock(id="v1")
    mock_version.resolved_snapshot = mock_version.snapshot = {
        "sections": [
            {
                "questions": [
                    {"variable_name": "price", "field_type": "number"},
                    {"variable_name": "qty", "field_type": "number"},
                    {
                        "variable_name": "total",
                        "field_type": "number",
                        "logic": {"calculated_value": "price * qty"},
                    },
                ]
            }
        ]
    }

    with patch("models.Form.Form.objects") as mock_form_objs, patch(
        "models.Form.FormVersion.objects"
    ) as mock_version_objs:

        mock_form_objs.return_value.first.return_value = mock_form
        mock_version_objs.return_value.first.return_value = mock_version
        mock_version_objs.return_value.order_by.return_value.first.return_value = (
            mock_version
        )

        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1", payload={"price": 10, "qty": 5}, organization_id="org1"
        )

        assert valid
        assert calc["total"] == 50
        assert cleaned["total"] == 50


def test_cascading_selects():
    mock_form = MagicMock(id="form1", active_version_id="v1", organization_id="org1")
    mock_version = MagicMock(id="v1")
    mock_version.resolved_snapshot = mock_version.snapshot = {
        "sections": [
            {
                "questions": [
                    {
                        "variable_name": "country",
                        "field_type": "select",
                        "options": [{"option_value": "India"}, {"option_value": "USA"}],
                    },
                    {
                        "variable_name": "city",
                        "field_type": "select",
                        "logic": {"parent_variable_name": "country"},
                        "options": [
                            {"option_value": "Mumbai", "parent_option_value": "India"},
                            {"option_value": "NY", "parent_option_value": "USA"},
                        ],
                    },
                ]
            }
        ]
    }

    with patch("models.Form.Form.objects") as mock_form_objs, patch(
        "models.Form.FormVersion.objects"
    ) as mock_version_objs:

        mock_form_objs.return_value.first.return_value = mock_form
        mock_version_objs.return_value.first.return_value = mock_version
        mock_version_objs.return_value.order_by.return_value.first.return_value = (
            mock_version
        )

        # Invalid: Mumbai for USA
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1",
            payload={"country": "USA", "city": "Mumbai"},
            organization_id="org1",
        )
        assert not valid
        assert any(e["field"] == "city" for e in errors)

        # Valid: Mumbai for India
        valid, cleaned, errors, calc = FormValidationService.validate_submission(
            form_id="form1",
            payload={"country": "India", "city": "Mumbai"},
            organization_id="org1",
        )
        assert valid
        assert cleaned["city"] == "Mumbai"


def test_save_form_draft_uses_project_scoped_form_lookup(app):
    from routes.v1.form.form import save_form_draft
    from uuid import UUID

    valid_uuid_str = "12345678-1234-5678-1234-567812345678"
    mock_form = MagicMock()
    mock_form.id = UUID(valid_uuid_str)
    mock_form.organization_id = "org-1"
    mock_form.to_mongo.return_value = {"project": DBRef("projects", "project-1")}

    mock_form_version = MagicMock()
    mock_form_version.version = None
    mock_form_version.model_dump.return_value = {"version": "1.0.0"}
    # Mock to_mongo().to_dict() returning a dictionary
    mock_dict = {"form": valid_uuid_str}
    mock_form_version.to_mongo.return_value.to_dict.return_value = mock_dict

    with app.test_request_context(
        f"/mahasangraha/api/v1/projects/project-1/forms/{valid_uuid_str}/draft",
        method="PUT",
        json={"sections": []},
        headers={"X-Organization-ID": "org-1"},
    ), patch("flask_jwt_extended.view_decorators.verify_jwt_in_request") as mock_verify_jwt, patch("routes.v1.form.form.get_current_user") as mock_current_user, patch(
        "routes.v1.form.form.Form.objects"
    ) as mock_form_objects, patch(
        "routes.v1.form.form.has_form_permission", return_value=True
    ), patch(
        "routes.v1.form.form.form_service.sync_form_canvas"
    ) as mock_sync_canvas, patch(
        "routes.v1.form.form.form_service.sync_draft_version",
        return_value=mock_form_version,
    ):
        mock_current_user.return_value = MagicMock(id="user-1", organization_id="org-1")
        mock_form_objects.get.return_value = mock_form

        response, status = save_form_draft(valid_uuid_str)

        assert status == 200
        assert response.get_json()["success"] is True
        mock_sync_canvas.assert_called_once()
