from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from logger.unified_logger import app_logger
from models.AnalysisBoard import AnalysisBoard
from models.AnalysisRun import AnalysisRun, AnalysisResult, AnalysisExport


class AnalysisRunService:
    def create_run(
        self,
        analysis_id: str,
        organization_id: str,
        trigger: str = "on_demand",
        triggered_by: Optional[str] = None,
        celery_task_id: Optional[str] = None,
    ) -> AnalysisRun:
        run = AnalysisRun(
            analysis_id=str(analysis_id),
            organization_id=organization_id,
            trigger=trigger,
            triggered_by=triggered_by,
            celery_task_id=celery_task_id,
            status="running",
        )
        run.save()
        return run

    def finish_run(
        self,
        run: AnalysisRun,
        node_statuses: Dict[str, Dict[str, Any]],
        result_ids: Dict[str, str],
        error_summary: Optional[str] = None,
    ) -> AnalysisRun:
        run.node_statuses = node_statuses
        run.result_ids = result_ids
        run.error_summary = error_summary
        run.status = "failed" if error_summary else "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.save()
        return run

    def record_result(
        self,
        run: AnalysisRun,
        node_id: str,
        analysis_id: str,
        organization_id: str,
        payload: Any,
        output_type: str = "value",
    ) -> AnalysisResult:
        result = AnalysisResult(
            run_id=str(run.id),
            analysis_id=str(analysis_id),
            node_id=str(node_id),
            organization_id=organization_id,
            output_type=output_type,
            data=payload if isinstance(payload, dict) else {"value": payload},
        )
        if isinstance(payload, dict) and "row_count" in payload:
            result.row_count = payload.get("row_count")
        result.save()
        return result

    def list_runs(
        self, analysis_id: str, organization_id: str, limit: int = 20
    ) -> List[AnalysisRun]:
        return list(
            AnalysisRun.objects(
                analysis_id=str(analysis_id), organization_id=organization_id
            )
            .order_by("-created_at")
            .limit(limit)
        )

    def get_run(
        self, analysis_id: str, run_id: str, organization_id: str
    ) -> Optional[AnalysisRun]:
        return AnalysisRun.objects(
            id=run_id, analysis_id=str(analysis_id), organization_id=organization_id
        ).first()

    def get_results(self, run_id: str, organization_id: str) -> List[AnalysisResult]:
        return list(AnalysisResult.objects(run_id=str(run_id), organization_id=organization_id).order_by("created_at"))

    def create_export(
        self,
        analysis_id: str,
        run_id: str,
        organization_id: str,
        created_by: Optional[str],
        export_format: str,
        node_ids: Optional[List[str]] = None,
        file_path: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        status: str = "queued",
        expires_in_days: int = 7,
    ) -> AnalysisExport:
        export = AnalysisExport(
            analysis_id=str(analysis_id),
            run_id=str(run_id),
            organization_id=organization_id,
            created_by=created_by,
            format=export_format,
            node_ids=node_ids or [],
            file_path=file_path,
            file_size_bytes=file_size_bytes,
            status=status,
            expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
        )
        export.save()
        return export


analysis_run_service = AnalysisRunService()
