from unittest.mock import MagicMock, patch

from models.form import Form, FormVersion
from schemas.form import FormSchema
from services.form_service import FormCreateSchema, FormService


def test_form_schema_normalizes_quick_responses():
    form = FormSchema(
        title="Quick Responses Contract",
        slug="quick-responses-contract",
        organization_id="org-1",
        created_by="user-1",
        quickResponses=[
            {
                "name": "Follow-up intake",
                "description": "Prefill the intake fields.",
                "tags": ["patient", "follow-up"],
                "visibility": "project",
                "ownerId": "user-9",
                "fieldValues": {
                    "patient_id": "P-1001",
                    "email": "patient@example.com",
                },
                "isArchived": False,
            }
        ],
    )

    quick_response = form.quick_responses[0]
    assert quick_response.name == "Follow-up intake"
    assert quick_response.description == "Prefill the intake fields."
    assert quick_response.tags == ["patient", "follow-up"]
    assert quick_response.visibility == "project"
    assert quick_response.owner_id == "user-9"
    assert quick_response.field_values == {
        "patient_id": "P-1001",
        "email": "patient@example.com",
    }
    assert quick_response.is_archived is False


def test_form_service_persists_quick_responses_in_snapshot(db_connection):
    service = FormService()
    tenant_service_mock = MagicMock()
    tenant_service_mock.check_form_quota.return_value = None
    tenant_service_mock.recalculate_usage.return_value = None

    with patch(
        "services.tenant_service.TenantService", return_value=tenant_service_mock
    ), patch("services.form_service.event_bus.publish"):
        created = service.create(
            FormCreateSchema(
                title="Quick Responses Save",
                slug="quick-responses-save",
                organization_id="org-1",
                created_by="user-1",
                quickResponses=[
                    {
                        "name": "Patient ID preset",
                        "tags": ["patient", "id"],
                        "fieldValues": {"patient_id": "P-2002"},
                    }
                ],
            )
        )

    stored_form = Form.objects.get(id=created.id)
    assert len(stored_form.quick_responses) == 1
    assert stored_form.quick_responses[0].name == "Patient ID preset"
    assert stored_form.quick_responses[0].field_values == {"patient_id": "P-2002"}

    form_version = FormVersion.objects(form=stored_form.id).first()
    assert form_version is not None
    assert form_version.quick_responses[0].name == "Patient ID preset"
    assert form_version.resolved_snapshot["quick_responses"][0]["name"] == (
        "Patient ID preset"
    )


def test_sync_form_canvas_persists_quick_responses(db_connection):
    service = FormService()
    form = Form(
        title="Canvas Quick Responses",
        slug="canvas-quick-responses",
        organization_id="org-1",
        created_by="user-1",
    ).save()

    updated = service.sync_form_canvas(
        str(form.id),
        "org-1",
        {
            "sections": [],
            "quickResponses": [
                {
                    "name": "Shared draft preset",
                    "visibility": "personal",
                    "fieldValues": {"patient_id": "P-3003"},
                }
            ],
        },
    )

    reloaded = Form.objects.get(id=updated.id)
    assert len(reloaded.quick_responses) == 1
    assert reloaded.quick_responses[0].name == "Shared draft preset"
    assert reloaded.quick_responses[0].field_values == {"patient_id": "P-3003"}

    version_doc = FormVersion.objects(form=reloaded.id).first()
    assert version_doc is not None
    assert version_doc.resolved_snapshot["quick_responses"][0]["name"] == (
        "Shared draft preset"
    )
