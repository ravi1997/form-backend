import json
from typing import Any, Dict, Iterable, Iterator, List, Optional

from models.analysis import AnalysisRun, AnalysisResult


def _result_to_dict(result: AnalysisResult) -> Dict[str, Any]:
    return {
        "id": str(result.id),
        "run_id": str(result.run_id),
        "analysis_id": str(result.analysis_id),
        "node_id": str(result.node_id),
        "organization_id": str(result.organization_id),
        "output_type": result.output_type,
        "data": result.data or {},
        "row_count": result.row_count,
        "column_definitions": result.column_definitions or [],
        "cached_until": result.cached_until.isoformat() if result.cached_until else None,
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }


def build_analysis_export_payload(
    run: AnalysisRun, results: Optional[List[AnalysisResult]] = None
) -> Dict[str, Any]:
    serialized_results = [_result_to_dict(result) for result in (results or [])]
    return {
        "run": {
            "id": str(run.id),
            "analysis_id": str(run.analysis_id),
            "organization_id": str(run.organization_id),
            "trigger": run.trigger,
            "triggered_by": run.triggered_by,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "celery_task_id": run.celery_task_id,
            "node_statuses": run.node_statuses or {},
            "error_summary": run.error_summary,
            "result_ids": run.result_ids or {},
            "created_at": run.created_at.isoformat() if run.created_at else None,
        },
        "results": serialized_results,
    }


def serialize_analysis_run(run: AnalysisRun) -> Dict[str, Any]:
    return {
        "id": str(run.id),
        "analysis_id": str(run.analysis_id),
        "organization_id": str(run.organization_id),
        "trigger": run.trigger,
        "triggered_by": run.triggered_by,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "celery_task_id": run.celery_task_id,
        "node_statuses": run.node_statuses or {},
        "error_summary": run.error_summary,
        "result_ids": run.result_ids or {},
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def iter_analysis_export_rows(
    run: AnalysisRun, results: Iterable[AnalysisResult]
) -> Iterator[Dict[str, Any]]:
    for result in results:
        yield _result_to_dict(result)


def dump_payload_to_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
