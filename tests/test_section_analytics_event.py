from unittest.mock import MagicMock, patch

from services.response_service import FormResponseService, FormResponseCreateSchema


def test_create_submission_publishes_section_analytics_metadata():
    service = FormResponseService()

    form_doc = MagicMock()
    form_doc._data = {}
    form_doc.sections = [
        {
            "id": "section-1",
            "title": "Vitals",
            "metadata": {
                "analyticsEvent": "vitals_view",
                "trackView": True,
                "trackCompletion": True,
                "trackDwellTime": False,
            },
            "sections": [],
        }
    ]

    response_doc = MagicMock()
    response_doc.id = "response-1"

    with patch("services.tenant_service.TenantService") as tenant_service, patch(
        "services.response_service.Form.objects"
    ) as form_objects, patch.object(service, "validate_payload", return_value=(True, {}, {}, {})), patch(
        "services.response_service.FormResponseService.create", return_value=response_doc
    ) as create_response, patch("services.event_bus.event_bus.publish") as publish, patch(
        "tasks.ai_tasks.async_index_response_vector.delay"
    ), patch(
        "tasks.ai_tasks.async_classify_response_tags.delay"
    ):
        tenant_service.return_value.check_submission_quota.return_value = None
        tenant_service.return_value.recalculate_usage.return_value = None
        form_objects.return_value.first.return_value = form_doc

        service.create_submission(
            FormResponseCreateSchema(
                form="form-1",
                organization_id="org-1",
                submitted_by="user-1",
                data={"status": "completed"},
            )
        )

    create_response.assert_called_once()
    publish.assert_called_once()
    payload = publish.call_args.args[1]
    assert payload["analytics"]["section_events"][0]["event_name"] == "vitals_view"
    assert payload["analytics"]["section_events"][0]["track_completion"] is True
