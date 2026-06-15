from datetime import timedelta

from config.celery import celery_app


def test_archive_old_audit_logs_is_in_beat_schedule():
    schedule = celery_app.conf.beat_schedule["archive-old-audit-logs"]
    assert schedule["task"] == "tasks.compliance_tasks.archive_old_audit_logs_task"
    assert schedule["schedule"] == timedelta(days=1)
    assert schedule["kwargs"] == {"days": 90, "format": "json"}
