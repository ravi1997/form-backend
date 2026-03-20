from types import SimpleNamespace

from routes.v1.form.helper import has_form_permission
from services.event_bus import EventBus
from utils.script_engine import execute_safe_script


def test_has_form_permission_blocks_cross_tenant_access():
    user = SimpleNamespace(
        id="user-1",
        roles=["manager"],
        department="ops",
        organization_id="org-a",
        is_superadmin_check=lambda: False,
    )
    form = SimpleNamespace(
        id="form-1",
        organization_id="org-b",
        created_by="creator-1",
        viewers=[],
        editors=[],
        submitters=[],
        is_public=True,
        access_policy=None,
    )

    assert has_form_permission(user, form, "view") is False
    assert has_form_permission(user, form, "submit") is False


def test_event_bus_message_get_supports_decoded_redis_payloads():
    message = {"payload": '{"ok": true}', "organization_id": "org-1"}

    assert EventBus._message_get(message, "payload") == '{"ok": true}'
    assert EventBus._message_get(message, "organization_id") == "org-1"


def test_execute_safe_script_evaluates_boolean_expression_only():
    result = execute_safe_script(
        "result = answers['score'] > 5 and data['score'] < 10",
        input_data={"score": 7},
        additional_globals={"answers": {"score": 7}, "data": {"score": 7}},
    )

    assert result == {"result": True}


def test_execute_safe_script_rejects_function_calls():
    result = execute_safe_script(
        "result = __import__('os').system('echo unsafe')",
        additional_globals={},
    )

    assert result == {"result": False}
