from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import uuid

from models.Form import Form, FormVersion
from models.Response import FormResponse
from models.TenantSettings import TenantSettings
from routes.v1.form.export import stream_form_csv
from schemas.form import FormSchema
from services.compliance_service import ComplianceService
from services.form_service import FormCreateSchema, FormService


def test_form_schema_applies_data_export_defaults():
    form = FormSchema(
        title="Export Contract",
        slug="export-contract",
        organization_id="org-1",
        created_by="user-1",
        dataExportSettings={
            "csvDefaults": {"delimiter": ";", "headerMode": "keys"},
            "retentionDays": 14,
            "fieldMapping": {"ssn": "Government ID"},
            "anonymization": {"mode": "hash", "fields": ["ssn"]},
        },
    )

    assert form.data_export_settings.retention_days == 14
    assert form.data_export_settings.csv_defaults.delimiter == ";"
    assert form.data_export_settings.csv_defaults.header_mode == "keys"
    assert form.data_export_settings.csv_defaults.empty_field_value == ""
    assert form.data_export_settings.field_mapping == {"ssn": "Government ID"}
    assert form.data_export_settings.anonymization.mode == "hash"
    assert form.data_export_settings.anonymization.fields == ["ssn"]


def test_form_service_create_persists_data_export_settings(db_connection):
    service = FormService()
    tenant_service_mock = MagicMock()
    tenant_service_mock.check_form_quota.return_value = None
    tenant_service_mock.recalculate_usage.return_value = None

    with patch(
        "services.tenant_service.TenantService", return_value=tenant_service_mock
    ), patch("services.form_service.event_bus.publish"):
        created = service.create(
            FormCreateSchema(
                title="Create Export Form",
                slug="create-export-form",
                organization_id="org-1",
                created_by="user-1",
                dataExportSettings={
                    "retentionDays": 21,
                    "fieldMapping": {"email": "Email Address"},
                    "anonymization": {"mode": "remove", "fields": ["email"]},
                },
            )
        )

    stored_form = Form.objects.get(id=created.id)
    assert stored_form.data_export_settings["csv_defaults"]["delimiter"] == ","
    assert stored_form.data_export_settings["csv_defaults"]["header_mode"] == "labels"
    assert stored_form.data_export_settings["retention_days"] == 21
    assert stored_form.data_export_settings["field_mapping"] == {
        "email": "Email Address"
    }
    assert stored_form.data_export_settings["anonymization"]["mode"] == "remove"
    assert stored_form.active_version_id is not None

    form_version = FormVersion.objects(form=stored_form.id).first()
    assert form_version is not None
    assert form_version.data_export_settings["retention_days"] == 21
    assert form_version.resolved_snapshot["data_export_settings"]["retention_days"] == 21


def test_sync_form_canvas_and_csv_export_honor_data_export_settings(db_connection):
    service = FormService()
    form = Form(
        title="Canvas Export Form",
        slug="canvas-export-form",
        organization_id="org-1",
        created_by="user-1",
    ).save()

    updated = service.sync_form_canvas(
        str(form.id),
        "org-1",
        {
            "sections": [
                {
                    "title": "Contact",
                    "questions": [
                        {
                            "label": "Participant Name",
                            "field_type": "short_text",
                            "variable_name": "full_name",
                        },
                        {
                            "label": "Government ID",
                            "field_type": "short_text",
                            "variable_name": "ssn",
                        },
                    ],
                }
            ],
            "dataExportSettings": {
                "csvDefaults": {"delimiter": ";", "headerMode": "labels"},
                "fieldMapping": {"ssn": "Government ID"},
                "anonymization": {"mode": "mask", "fields": ["ssn"]},
            },
        },
    )

    reloaded_form = Form.objects.get(id=updated.id)
    assert reloaded_form.data_export_settings["csv_defaults"]["delimiter"] == ";"
    assert reloaded_form.data_export_settings["csv_defaults"]["header_mode"] == "labels"
    assert reloaded_form.data_export_settings["field_mapping"] == {
        "ssn": "Government ID"
    }

    version_doc = FormVersion.objects(form=reloaded_form.id).first()
    assert version_doc is not None
    assert version_doc.resolved_snapshot["data_export_settings"]["csv_defaults"][
        "delimiter"
    ] == ";"

    response = FormResponse(
        id=uuid.uuid4(),
        organization_id="org-1",
        form=str(uuid.uuid4()),
        submitted_by="user-2",
        idempotency_key=str(uuid.uuid4()),
        submitted_at=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        data={
            "full_name": "Ada Lovelace",
            "ssn": "123-45-6789",
        },
    ).save()

    csv_output = "".join(stream_form_csv(reloaded_form, [response]))
    lines = csv_output.splitlines()

    assert lines[0] == (
        "response_id;submitted_by;submitted_at;status;Participant Name;Government ID"
    )
    assert "[REDACTED]" in lines[1]


def test_csv_export_can_hide_or_include_attachment_fields(db_connection):
    service = FormService()
    form = Form(
        title="Attachment Export Form",
        slug="attachment-export-form",
        organization_id="org-1",
        created_by="user-1",
    ).save()

    updated = service.sync_form_canvas(
        str(form.id),
        "org-1",
        {
            "sections": [
                {
                    "title": "Uploads",
                    "questions": [
                        {
                            "label": "Profile Photo",
                            "field_type": "file_upload",
                            "variable_name": "profile_photo",
                        }
                    ],
                }
            ],
            "dataExportSettings": {
                "csvDefaults": {
                    "delimiter": ",",
                    "headerMode": "labels",
                    "emptyFieldValue": "[EMPTY]",
                    "includeAttachments": False,
                },
                "fieldMapping": {"profile_photo": "Profile Photo"},
                "anonymization": {"mode": "none", "fields": []},
            },
        },
    )

    version_doc = FormVersion.objects(form=updated.id).first()
    assert version_doc is not None

    response = FormResponse(
        id=uuid.uuid4(),
        organization_id="org-1",
        form=str(uuid.uuid4()),
        submitted_by="user-2",
        idempotency_key=str(uuid.uuid4()),
        submitted_at=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        data={"profile_photo": "https://cdn.example.test/file.png"},
    ).save()

    hidden_output = "".join(stream_form_csv(updated, [response]))
    hidden_lines = hidden_output.splitlines()
    assert hidden_lines[0] == "response_id,submitted_by,submitted_at,status,Profile Photo"
    assert "[EMPTY]" in hidden_lines[1]
    assert "https://cdn.example.test/file.png" not in hidden_lines[1]

    form.data_export_settings["csv_defaults"]["include_attachments"] = True
    form.save()
    visible_output = "".join(stream_form_csv(form, [response], version_id=str(version_doc.id)))
    visible_lines = visible_output.splitlines()
    assert "https://cdn.example.test/file.png" in visible_lines[1]
    assert "[EMPTY]" not in visible_lines[1]


def test_execute_retention_policy_prefers_form_level_retention_days(db_connection):
    tenant_settings = TenantSettings.get_or_create("org-1")
    tenant_settings.retention_days = 30
    tenant_settings.save()

    short_retention_form = Form(
        title="Short Retention",
        slug="short-retention",
        organization_id="org-1",
        created_by="user-1",
        data_export_settings={
            "retention_days": 7,
            "csv_defaults": {"delimiter": ",", "header_mode": "labels"},
            "field_mapping": {},
            "anonymization": {"mode": "none", "fields": []},
        },
    ).save()
    long_retention_form = Form(
        title="Default Retention",
        slug="default-retention",
        organization_id="org-1",
        created_by="user-1",
    ).save()

    expired_at = datetime.now(timezone.utc) - timedelta(days=10)
    pruned_response = FormResponse(
        id=uuid.uuid4(),
        organization_id="org-1",
        form=str(short_retention_form.id),
        submitted_by="user-2",
        idempotency_key=str(uuid.uuid4()),
        submitted_at=expired_at,
        data={"value": "short"},
    ).save()
    kept_response = FormResponse(
        id=uuid.uuid4(),
        organization_id="org-1",
        form=str(long_retention_form.id),
        submitted_by="user-3",
        idempotency_key=str(uuid.uuid4()),
        submitted_at=expired_at,
        data={"value": "default"},
    ).save()

    result = ComplianceService().execute_retention_policy("org-1", "actor-1")

    assert result["pruned_count"] == 1
    assert FormResponse.objects(id=pruned_response.id).first() is None
    assert FormResponse.objects(id=kept_response.id).first() is not None
