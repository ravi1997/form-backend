import importlib
import json
from datetime import datetime, timezone
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from models.AnalysisBoard import AnalysisBoard
from models.AnalysisRun import AnalysisRun, AnalysisResult
from models.Form import Project
from models.User import User
from services.analysis_run_service import analysis_run_service
from services.export_retention_service import export_retention_service
from utils.exceptions import ValidationError


def _seed_analysis_run():
    board = AnalysisBoard(
        title="Export Board",
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
    AnalysisResult(
        run_id=str(run.id),
        analysis_id=str(board.id),
        node_id="node-1",
        organization_id="org-1",
        output_type="value",
        data={"value": 42},
    ).save()
    AnalysisResult(
        run_id=str(run.id),
        analysis_id=str(board.id),
        node_id="node-2",
        organization_id="org-1",
        output_type="table",
        data={"rows": [{"name": "alpha"}]},
    ).save()
    return board, run


def test_csv_json_excel_export_generation(db_connection, tmp_path, monkeypatch):
    monkeypatch.setattr(
        importlib.import_module("config.settings").settings,
        "EXPORT_STORAGE_ROOT",
        str(tmp_path),
    )
    board, run = _seed_analysis_run()

    csv_export = analysis_run_service.create_export(
        analysis_id=str(board.id),
        run_id=str(run.id),
        organization_id="org-1",
        created_by="user-1",
        export_format="csv",
        node_ids=None,
    )
    assert csv_export.status == "completed"
    assert csv_export.file_path and Path(csv_export.file_path).exists()
    csv_text = Path(csv_export.file_path).read_text(encoding="utf-8")
    assert "node-1" in csv_text
    assert "42" in csv_text

    json_export = analysis_run_service.create_export(
        analysis_id=str(board.id),
        run_id=str(run.id),
        organization_id="org-1",
        created_by="user-1",
        export_format="json",
        node_ids=None,
    )
    assert json_export.status == "completed"
    json_payload = json.loads(Path(json_export.file_path).read_text(encoding="utf-8"))
    assert json_payload["run"]["id"] == str(run.id)
    assert len(json_payload["results"]) == 2

    excel_export = analysis_run_service.create_export(
        analysis_id=str(board.id),
        run_id=str(run.id),
        organization_id="org-1",
        created_by="user-1",
        export_format="excel",
        node_ids=None,
    )
    assert excel_export.status == "completed"
    with zipfile.ZipFile(excel_export.file_path) as workbook_zip:
        assert "xl/workbook.xml" in workbook_zip.namelist()
        workbook_xml = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        sheet_names = [
            sheet.attrib["name"]
            for sheet in workbook_xml.findall("a:sheets/a:sheet", ns)
        ]
        assert sheet_names == ["Run Metadata", "Node Results"]
        metadata_xml = ET.fromstring(workbook_zip.read("xl/worksheets/sheet1.xml"))
        results_xml = ET.fromstring(workbook_zip.read("xl/worksheets/sheet2.xml"))
        assert metadata_xml.find(".//a:c[@r='A1']/a:is/a:t", ns).text == "field"
        assert results_xml.find(".//a:c[@r='A1']/a:is/a:t", ns).text == "result_id"

    pdf_export = analysis_run_service.create_export(
        analysis_id=str(board.id),
        run_id=str(run.id),
        organization_id="org-1",
        created_by="user-1",
        export_format="pdf",
        node_ids=None,
    )
    assert pdf_export.status == "completed"
    assert pdf_export.file_path and Path(pdf_export.file_path).exists()
    pdf_bytes = Path(pdf_export.file_path).read_bytes()
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"/Type /Catalog" in pdf_bytes
    assert b"xref" in pdf_bytes
    assert pdf_bytes.rstrip().endswith(b"%%EOF")


def test_async_export_pipeline_populates_file_path_and_downloads(
    app, db_connection, monkeypatch, tmp_path
):
    from flask_jwt_extended import create_access_token
    from tasks.export_tasks import generate_analysis_export_task
    from routes.v1.analysis_board_route import analysis_board_bp

    try:
        app.register_blueprint(
            analysis_board_bp,
            url_prefix="/mahasangraha/api/v1/projects/<project_id>/analysis-boards",
        )
    except AssertionError:
        pass

    monkeypatch.setattr(
        importlib.import_module("config.settings").settings,
        "EXPORT_STORAGE_ROOT",
        str(tmp_path),
    )

    with app.app_context():
        user_id = str(uuid.uuid4())
        User(
            id=user_id,
            username="async_export_user",
            email="async-export@test.com",
            user_type="employee",
            is_active=True,
            roles=["admin"],
            organization_id="org-1",
        ).save()
        token = create_access_token(
            identity=user_id,
            additional_claims={
                "org_id": "org-1",
                "organization_id": "org-1",
                "roles": ["admin"],
            },
        )
        headers = {"Authorization": f"Bearer {token}"}
        project = Project(
            id=str(uuid.uuid4()),
            title="Async Export Project",
            organization_id="org-1",
        ).save()
        board, run = _seed_analysis_run()
        board.project_id = str(project.id)
        board.save()

        def _inline_delay(export_job_id, export_format):
            return generate_analysis_export_task.run(
                export_job_id,
                export_format,
            )

        monkeypatch.setattr(
            "tasks.export_tasks.generate_analysis_export_task.delay", _inline_delay
        )

        client = app.test_client()
        create_resp = client.post(
            f"/mahasangraha/api/v1/projects/{project.id}/analysis-boards/{board.id}/export",
            json={"run_id": str(run.id), "format": "json"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        export_id = create_resp.get_json()["data"]["id"]
        export_status = create_resp.get_json()["data"]["status"]
        assert export_status in {"queued", "pending", "completed"}

        get_resp = client.get(
            f"/mahasangraha/api/v1/projects/{project.id}/analysis-boards/{board.id}/export/{export_id}",
            headers=headers,
        )
        assert get_resp.status_code == 200
        export_data = get_resp.get_json()["data"]
        assert export_data["file_path"]

        download_resp = client.get(
            f"/mahasangraha/api/v1/projects/{project.id}/analysis-boards/{board.id}/export/{export_id}/download",
            headers=headers,
        )
        assert download_resp.status_code == 200
        assert download_resp.data


def test_export_cleanup_and_failure_paths(db_connection, tmp_path, monkeypatch):
    from tasks.cleanup_tasks import cleanup_analysis_exports_task
    from tasks.export_tasks import generate_analysis_export_task

    monkeypatch.setattr(
        importlib.import_module("config.settings").settings,
        "EXPORT_STORAGE_ROOT",
        str(tmp_path),
    )
    monkeypatch.setattr(
        importlib.import_module("config.settings").settings,
        "EXPORT_TTL_HOURS",
        1,
    )

    board, run = _seed_analysis_run()
    export = analysis_run_service.create_export(
        analysis_id=str(board.id),
        run_id=str(run.id),
        organization_id="org-1",
        created_by="user-1",
        export_format="csv",
        node_ids=None,
    )

    export_path = Path(export.file_path)
    old_mtime = export_path.stat().st_mtime - (60 * 60 * 2)
    import os

    os.utime(export.file_path, (old_mtime, old_mtime))
    export.update(set__expired_at=export.expired_at.replace(year=2000))

    cleanup_result = cleanup_analysis_exports_task.run()
    assert cleanup_result["deleted"] >= 1 or cleanup_result["missing"] >= 0
    refreshed = type(export).objects(id=export.id).first()
    assert refreshed is not None
    assert refreshed.status == "expired"
    assert refreshed.file_path is None

    monkeypatch.setattr(
        analysis_run_service,
        "generate_analysis_export",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom")),
    )
    with pytest.raises(ValueError):
        generate_analysis_export_task.run(
            str(export.id),
            "csv",
        )


def test_export_retention_prunes_export_jobs_only(db_connection, tmp_path, monkeypatch):
    from models.ExportJob import ExportJob
    from services.storage_backend import export_storage_backend

    monkeypatch.setattr(
        importlib.import_module("config.settings").settings,
        "EXPORT_STORAGE_ROOT",
        str(tmp_path),
    )
    monkeypatch.setattr(
        importlib.import_module("config.settings").settings,
        "EXPORT_TTL_HOURS",
        1,
    )

    board, run = _seed_analysis_run()
    export_path = export_storage_backend.resolve(
        str(board.id), str(run.id), "job.csv"
    )
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text("job,data\n1,2\n", encoding="utf-8")

    export = ExportJob(
        organization_id="org-1",
        analysis_run_id=str(run.id),
        analysis_id=str(board.id),
        format="csv",
        status="completed",
        file_path=str(export_path),
        expired_at=datetime.now(timezone.utc).replace(year=2000),
    ).save()

    result = export_retention_service.prune_expired_exports()
    assert result["deleted"] >= 1
    refreshed = ExportJob.objects(id=export.id).first()
    assert refreshed is not None
    assert refreshed.status == "expired"
    assert refreshed.file_path is None
    assert not export_storage_backend.exists(str(export_path))


def test_export_generation_rejects_invalid_format_and_missing_run(db_connection):
    board = AnalysisBoard(
        title="Invalid Format Board",
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

    with pytest.raises(ValidationError):
        analysis_run_service.create_export(
            analysis_id=str(board.id),
            run_id=str(run.id),
            organization_id="org-1",
            created_by="user-1",
            export_format="xml",
            node_ids=None,
        )

    with pytest.raises(ValidationError):
        analysis_run_service.create_export(
            analysis_id=str(board.id),
            run_id=str(uuid.uuid4()),
            organization_id="org-1",
            created_by="user-1",
            export_format="csv",
            node_ids=None,
        )


def test_storage_backend_abstraction_and_retry_state(
    db_connection, tmp_path, monkeypatch
):
    from config.settings import settings
    from services.storage_backend import export_storage_backend
    from tasks.export_tasks import generate_analysis_export_task

    monkeypatch.setattr(settings, "EXPORT_STORAGE_ROOT", str(tmp_path))

    target = export_storage_backend.resolve("analysis-a", "run-a", "export.csv")
    target.write_text("hello", encoding="utf-8")
    assert export_storage_backend.exists(target)
    assert export_storage_backend.delete(target)
    assert not export_storage_backend.exists(target)

    board, run = _seed_analysis_run()
    export = analysis_run_service.create_export(
        analysis_id=str(board.id),
        run_id=str(run.id),
        organization_id="org-1",
        created_by="user-1",
        export_format="csv",
        node_ids=None,
        file_path=str(tmp_path / "retry.csv"),
        file_size_bytes=0,
        status="ready",
    )

    monkeypatch.setattr(
        analysis_run_service,
        "generate_analysis_export",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom")),
    )
    with pytest.raises(ValueError):
        generate_analysis_export_task.run(
            str(export.id),
            "csv",
        )

    export.reload()
    assert export.status == "failed"
    assert export.retry_count >= 1
    assert export.last_error
