import importlib
import uuid
from pathlib import Path

from models.AnalysisBoard import AnalysisBoard
from models.AnalysisRun import AnalysisRun, AnalysisResult
from services.analysis_run_service import analysis_run_service


def test_large_csv_export_streaming_smoke(db_connection, tmp_path, monkeypatch):
    monkeypatch.setattr(
        importlib.import_module("config.settings").settings,
        "EXPORT_STORAGE_ROOT",
        str(tmp_path),
    )

    board = AnalysisBoard(
        title="Stress Board",
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

    for index in range(2500):
        AnalysisResult(
            run_id=str(run.id),
            analysis_id=str(board.id),
            node_id=f"node-{index}",
            organization_id="org-1",
            output_type="value",
            data={"value": index},
        ).save()

    export = analysis_run_service.create_export(
        analysis_id=str(board.id),
        run_id=str(run.id),
        organization_id="org-1",
        created_by="user-1",
        export_format="csv",
        node_ids=None,
        file_path=None,
        file_size_bytes=None,
    )

    assert export.status == "completed"
    assert export.file_path and Path(export.file_path).exists()
    content = Path(export.file_path).read_text(encoding="utf-8")
    assert "node-0" in content
    assert "node-2499" in content
