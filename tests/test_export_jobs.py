import importlib
import uuid

from models.AnalysisBoard import AnalysisBoard
from models.AnalysisRun import AnalysisRun, AnalysisExport
from models.ExportJob import ExportJob
from services.export_job_service import export_job_service
from tasks.export_tasks import generate_analysis_export_task


def _seed_run():
    board = AnalysisBoard(
        title="Job Board",
        project_id=str(uuid.uuid4()),
        organization_id="org-1",
        created_by="user-1",
        nodes=[],
    ).save()
    run = AnalysisRun(
        analysis_id=str(board.id),
        organization_id="org-1",
        trigger="on_demand",
        triggered_by="user-1",
        status="completed",
    ).save()
    return board, run


def test_export_job_creation(db_connection):
    _, run = _seed_run()
    job = export_job_service.create_job(
        analysis_run_id=str(run.id),
        export_format="json",
        organization_id="org-1",
        idempotency_key="idem-1",
    )
    assert job.analysis_run_id == str(run.id)
    assert job.format == "json"
    assert job.status == "pending"
    assert job.idempotency_key == "idem-1"


def test_export_job_state_transitions(db_connection):
    _, run = _seed_run()
    job = export_job_service.create_job(
        analysis_run_id=str(run.id),
        export_format="csv",
        organization_id="org-1",
    )
    export_job_service.transition_status(job, "processing")
    assert job.status == "processing"
    export_job_service.attach_file_path(job, "/tmp/export.csv", 12)
    assert job.status == "completed"
    assert job.file_path == "/tmp/export.csv"
    export_job_service.record_failure(job, "boom")
    assert job.status == "failed"
    assert job.retry_count >= 1
    assert job.last_error == "boom"


def test_export_job_duplicate_completion_is_short_circuited(db_connection):
    _, run = _seed_run()
    job = export_job_service.create_job(
        analysis_run_id=str(run.id),
        export_format="csv",
        organization_id="org-1",
    )
    export_job_service.attach_file_path(job, "/tmp/export.csv", 12)

    export_job_service.attach_file_path(job, "/tmp/export.csv", 12)

    refreshed = ExportJob.objects(id=job.id).first()
    assert refreshed is not None
    assert refreshed.status == "completed"
    assert refreshed.file_path == "/tmp/export.csv"


def test_export_job_celery_execution(db_connection, tmp_path, monkeypatch):
    board, run = _seed_run()
    job = export_job_service.create_job(
        analysis_run_id=str(run.id),
        export_format="json",
        organization_id="org-1",
    )
    monkeypatch.setattr(
        importlib.import_module("config.settings").settings,
        "EXPORT_STORAGE_ROOT",
        str(tmp_path),
    )
    result = generate_analysis_export_task.run(str(job.id), "json")
    assert result["status"] == "completed"


def test_export_job_idempotency(db_connection):
    _, run = _seed_run()
    first = export_job_service.create_job(
        analysis_run_id=str(run.id),
        export_format="csv",
        organization_id="org-1",
        idempotency_key="same-key",
    )
    second = export_job_service.create_job(
        analysis_run_id=str(run.id),
        export_format="csv",
        organization_id="org-1",
        idempotency_key="same-key",
    )
    assert str(first.id) == str(second.id)


def test_backward_compatibility_mapping(db_connection):
    _, run = _seed_run()
    legacy = AnalysisExport(
        analysis_id=str(run.analysis_id),
        run_id=str(run.id),
        organization_id="org-1",
        format="excel",
        status="ready",
        file_path="/tmp/legacy.xlsx",
    ).save()
    job = export_job_service.get_job(str(legacy.id), organization_id="org-1")
    assert job is not None
    assert job.analysis_run_id == str(run.id)
    assert job.file_path == "/tmp/legacy.xlsx"
    assert ExportJob.objects(analysis_run_id=str(run.id), organization_id="org-1").first()
