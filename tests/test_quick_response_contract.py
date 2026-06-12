from models.Form import Form, FormVersion
from services.form_service import FormService


def test_sync_form_canvas_persists_quick_responses_round_trip(db_connection):
    service = FormService()
    form = Form(
        title="Quick Responses",
        slug="quick-responses",
        organization_id="org-1",
        created_by="user-1",
    ).save()

    updated = service.sync_form_canvas(
        str(form.id),
        "org-1",
        {
            "quickResponses": [
                {
                    "name": "OPD Intake",
                    "description": "Starter preset for intake",
                    "tags": ["opd", "intake", "opd"],
                    "visibility": "project",
                    "ownerId": "user-1",
                    "fieldValues": {
                        "department": "Cardiology",
                        "priority": "High",
                    },
                    "isArchived": False,
                }
            ]
        },
    )

    reloaded_form = Form.objects.get(id=updated.id)
    assert len(reloaded_form.quick_responses) == 1

    quick_response = reloaded_form.quick_responses[0]
    assert quick_response.name == "OPD Intake"
    assert quick_response.description == "Starter preset for intake"
    assert quick_response.tags == ["opd", "intake"]
    assert quick_response.visibility == "project"
    assert quick_response.owner_id == "user-1"
    assert quick_response.field_values == {
        "department": "Cardiology",
        "priority": "High",
    }
    assert quick_response.is_archived is False

    form_version = FormVersion.objects(form=reloaded_form.id).first()
    assert form_version is not None
    assert len(form_version.quick_responses) == 1
    assert form_version.quick_responses[0].name == "OPD Intake"

    resolved_snapshot = form_version.resolved_snapshot
    assert resolved_snapshot["quick_responses"][0]["name"] == "OPD Intake"
    assert resolved_snapshot["quick_responses"][0]["field_values"] == {
        "department": "Cardiology",
        "priority": "High",
    }
    assert resolved_snapshot["quick_responses"][0]["id"]
