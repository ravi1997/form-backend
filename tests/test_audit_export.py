import pytest
import uuid
import json
import os
from datetime import datetime, timezone
from flask_jwt_extended import create_access_token
from models.User import User
from models.AuditLog import AuditLog
from tasks.compliance_tasks import export_tenant_audit_logs_task
from routes.v1.admin.tenant_compliance_route import tenant_compliance_bp

def test_audit_log_export_task(db_connection, monkeypatch, tmp_path):
    # Setup test audit logs
    org_1 = "org-export-1"
    org_2 = "org-export-2"

    AuditLog.objects.delete()
    monkeypatch.setenv("AUDIT_EXPORT_DIR", str(tmp_path))
    
    # Logs for org_1
    AuditLog(
        organization_id=org_1,
        actor_id="actor-1",
        action="create",
        resource_type="form",
        resource_id="form-1",
        timestamp=datetime.now(timezone.utc)
    ).save()
    
    # Log for org_2 (should not be in org_1 export)
    AuditLog(
        organization_id=org_2,
        actor_id="actor-2",
        action="delete",
        resource_type="form",
        resource_id="form-2",
        timestamp=datetime.now(timezone.utc)
    ).save()

    # Run export task directly
    res = export_tenant_audit_logs_task.run(org_1, "csv")
    assert res["status"] == "SUCCESS"
    assert res["count"] == 1
    
    export_dir = str(tmp_path)
    file_path = os.path.join(export_dir, res["filename"])
    assert os.path.exists(file_path)
    
    # Read file and verify content
    with open(file_path, "r") as f:
        content = f.read()
        assert "create" in content
        assert "form-1" in content
        assert "delete" not in content
        assert "form-2" not in content
        
    # Clean up file
    try:
        os.remove(file_path)
    except Exception:
        pass


def test_audit_export_api(app, db_connection):
    try:
        app.register_blueprint(tenant_compliance_bp, url_prefix="/mahasangraha/api/v1/compliance")
    except AssertionError:
        pass

    client = app.test_client()
    monkeypatch = pytest.MonkeyPatch()
    export_dir = "/tmp/form-backend-exports"
    monkeypatch.setenv("AUDIT_EXPORT_DIR", export_dir)

    with app.app_context():
        # Setup Admin User
        admin_user = User(
            id=uuid.uuid4(),
            username="admin_exp",
            email="admin_exp@test.com",
            user_type="employee",
            is_active=True,
            roles=["admin"],
            organization_id="org-api-exp",
        ).save()
        
        admin_token = create_access_token(
            identity=str(admin_user.id),
            additional_claims={"roles": ["admin"], "organization_id": "org-api-exp"},
        )
        
        # Setup Standard User (Should be blocked by require_roles)
        standard_user = User(
            id=uuid.uuid4(),
            username="user_exp",
            email="user_exp@test.com",
            user_type="employee",
            is_active=True,
            roles=["user"],
            organization_id="org-api-exp",
        ).save()
        
        user_token = create_access_token(
            identity=str(standard_user.id),
            additional_claims={"roles": ["user"], "organization_id": "org-api-exp"},
        )

        headers_admin = {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"
        }
        
        headers_user = {
            "Authorization": f"Bearer {user_token}",
            "Content-Type": "application/json"
        }

        # 1. Trigger export with user token -> should fail with 403
        resp = client.post("/mahasangraha/api/v1/compliance/audit/export", headers=headers_user, json={"format": "csv"})
        assert resp.status_code == 403

        # 2. Trigger export with admin token -> should succeed (202)
        class _FakeTask:
            id = "export-task-123"

        def _fake_delay(*args, **kwargs):
            return _FakeTask()

        from tasks import compliance_tasks as _compliance_tasks

        monkeypatch.setattr(_compliance_tasks.export_tenant_audit_logs_task, "delay", _fake_delay)

        resp = client.post("/mahasangraha/api/v1/compliance/audit/export", headers=headers_admin, json={"format": "csv"})
        assert resp.status_code == 202
        data = resp.get_json()["data"]
        assert data["task_id"] == "export-task-123"
        assert data["status"] == "PENDING"
        monkeypatch.undo()
        
        # 3. Test download endpoint boundaries
        export_uuid = str(uuid.uuid4())

        # Create dummy file for org-api-exp
        os.makedirs(export_dir, exist_ok=True)
        filename = f"audit_export_org-api-exp_{export_uuid}.csv"
        file_path = os.path.join(export_dir, filename)
        with open(file_path, "w") as f:
            f.write("dummy audit data")
        monkeypatch.setattr(
            "routes.v1.admin.tenant_compliance_route.get_audit_export_dir",
            lambda: export_dir,
        )
            
        # Try to download using admin of SAME tenant -> should succeed
        resp = client.get(f"/mahasangraha/api/v1/compliance/audit/export/download/{export_uuid}.csv", headers=headers_admin)
        assert resp.status_code == 200
        assert resp.get_data(as_text=True) == "dummy audit data"
        
        # Try to download using user of DIFFERENT tenant
        other_user = User(
            id=uuid.uuid4(),
            username="other_exp",
            email="other_exp@test.com",
            user_type="employee",
            is_active=True,
            roles=["admin"],
            organization_id="org-other",
        ).save()
        
        other_token = create_access_token(
            identity=str(other_user.id),
            additional_claims={"roles": ["admin"], "organization_id": "org-other"},
        )
        headers_other = {"Authorization": f"Bearer {other_token}"}
        
        resp = client.get(f"/mahasangraha/api/v1/compliance/audit/export/download/{export_uuid}.csv", headers=headers_other)
        print("FAIL DEBUG STATUS:", resp.status_code)
        print("FAIL DEBUG BODY:", resp.get_data(as_text=True))
        # Should fail with 404 (due to tenant boundary check matching org_id)
        assert resp.status_code == 404

        # Cleanup dummy file
        try:
            os.remove(file_path)
        except Exception:
            pass
        monkeypatch.undo()


def test_audit_archive_api_triggers_task(app, db_connection, monkeypatch):
    try:
        app.register_blueprint(tenant_compliance_bp, url_prefix="/mahasangraha/api/v1/compliance")
    except AssertionError:
        pass

    class _FakeTask:
        id = "archive-task-123"

    recorded = {}

    def _fake_delay(*, days, format):
        recorded["days"] = days
        recorded["format"] = format
        return _FakeTask()

    monkeypatch.setattr(
        "tasks.compliance_tasks.archive_old_audit_logs_task.delay",
        _fake_delay,
    )

    client = app.test_client()
    with app.app_context():
        admin_user = User(
            id=uuid.uuid4(),
            username="admin_archive",
            email="admin_archive@test.com",
            user_type="employee",
            is_active=True,
            roles=["admin"],
            organization_id="org-archive-api",
        ).save()
        admin_token = create_access_token(
            identity=str(admin_user.id),
            additional_claims={"roles": ["admin"], "organization_id": "org-archive-api"},
        )

    headers_admin = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }

    resp = client.post(
        "/mahasangraha/api/v1/compliance/audit/archive",
        headers=headers_admin,
        json={"days": 45, "format": "json"},
    )
    assert resp.status_code == 202
    payload = resp.get_json()["data"]
    assert payload["task_id"] == "archive-task-123"
    assert payload["status"] == "PENDING"
    assert payload["days"] == 45
    assert payload["format"] == "json"
    assert recorded == {"days": 45, "format": "json"}
