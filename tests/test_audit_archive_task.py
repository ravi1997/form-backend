from datetime import datetime, timezone, timedelta

from models.AuditLog import AuditLog
from models.user import User
from services.audit_archive_service import AuditArchiveService


def _make_user():
    user = User(
        username="archive-user",
        email="archive-user@example.com",
        user_type="employee",
        organization_id="org-archive",
        roles=["admin"],
        is_admin=True,
        is_active=True,
        is_deleted=False,
    )
    user.set_password("password123")
    user.save()
    return user


def test_archive_old_audit_logs_moves_only_stale_records(db_connection, monkeypatch, tmp_path):
    monkeypatch.setattr(AuditArchiveService, "archive_dir", tmp_path)
    user = _make_user()
    old_log = AuditLog(
        organization_id="org-archive",
        actor_id=str(user.id),
        action="update",
        resource_type="form",
        resource_id="form-1",
        timestamp=datetime.now(timezone.utc) - timedelta(days=120),
    )
    old_log.save()
    fresh_log = AuditLog(
        organization_id="org-archive",
        actor_id=str(user.id),
        action="update",
        resource_type="form",
        resource_id="form-2",
        timestamp=datetime.now(timezone.utc),
    )
    fresh_log.save()

    result = AuditArchiveService.archive_older_than(days=90, format="json")

    assert result["count"] == 1
    assert list(tmp_path.glob("audit_logs_archive_*.json"))
    assert AuditLog.objects(id=old_log.id).first() is None
    assert AuditLog.objects(id=fresh_log.id).first() is not None
