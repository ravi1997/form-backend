import pytest
import uuid
from models.Form import Project
from models.ReportJobLog import ReportJobLog

def test_report_config_embedded_crud(app, db_connection):
    org_id = "test-org-456"
    user_id = "test-user-789"
    
    # 1. Create a Project
    project = Project(
        title="Operations Report Tracker",
        organization_id=org_id,
        status="published",
    ).save()

    # 2. Add an embedded ReportConfig
    report_data = {
        "name": "Weekly Submission Peak Report",
        "trigger_type": "schedule",
        "cron_expression": "0 9 * * 1",
        "blocks": [
            {"type": "header", "config": {"title": "Ops Banner"}},
            {"type": "metric", "config": {"metric_id": "total_count"}}
        ],
        "recipients": ["manager@test.com"],
        "channels": ["storage", "email"]
    }
    
    from models.Form import ReportConfig
    config = ReportConfig(
        id=uuid.uuid4(),
        name=report_data["name"],
        trigger_type=report_data["trigger_type"],
        cron_expression=report_data["cron_expression"],
        blocks=report_data["blocks"],
        recipients=report_data["recipients"],
        channels=report_data["channels"]
    )
    project.report_configs.append(config)
    project.save()

    # Verify Config Exists
    project.reload()
    assert len(project.report_configs) == 1
    assert project.report_configs[0].name == "Weekly Submission Peak Report"
    assert project.report_configs[0].blocks[0]["type"] == "header"

    # 3. Create a Job Audit Log for this execution
    log = ReportJobLog(
        project_id=str(project.id),
        config_id=str(config.id),
        status="success",
        trigger_reason="Cron Schedule",
        file_url="https://secure-storage/reports/operations_week1.pdf"
    ).save()

    assert ReportJobLog.objects(config_id=str(config.id)).count() == 1
    assert ReportJobLog.objects(config_id=str(config.id)).first().status == "success"

def test_report_compiler_execution(app, db_connection):
    org_id = "test-org-111"
    
    project = Project(
        title="Finance Performance Metrics",
        organization_id=org_id,
        status="published",
    ).save()

    from models.Form import ReportConfig
    config = ReportConfig(
        id=uuid.uuid4(),
        name="Quarterly Revenue Summary",
        trigger_type="threshold",
        threshold_limit=50,
        blocks=[
            {"type": "header", "config": {"title": "Q3 Rev Summary"}},
            {"type": "metric", "config": {"metric_id": "rev_count"}},
            {"type": "rich_text", "config": {"text": "Draft report detailing targets"}},
            {"type": "chart", "config": {}},
            {"type": "table", "config": {}}
        ]
    )
    project.report_configs.append(config)
    project.save()

    from services.report_compiler_service import ReportCompilerService
    compiler = ReportCompilerService()
    file_url = compiler.compile_report(str(project.id), str(config.id), "Threshold Hit (50)")

    assert file_url.startswith("https://")
    assert "reports" in file_url
    assert ReportJobLog.objects(config_id=str(config.id)).count() == 1
    
    run_log = ReportJobLog.objects(config_id=str(config.id)).first()
    assert run_log.status == "success"
    assert run_log.trigger_reason == "Threshold Hit (50)"
    assert run_log.duration_ms > 0
    assert run_log.file_url == file_url
