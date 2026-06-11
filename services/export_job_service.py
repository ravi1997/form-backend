from datetime import datetime, timedelta, timezone
from typing import Optional

from models.AnalysisRun import AnalysisExport
from models.ExportJob import ExportJob
from utils.exceptions import ValidationError


class ExportJobService:
    allowed_statuses = {
        "pending",
        "queued",
        "processing",
        "completed",
        "ready",
        "failed",
        "expired",
    }

    def create_job(
        self,
        analysis_run_id: str,
        export_format: str,
        organization_id: str,
        *,
        analysis_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        status: str = "pending",
        node_ids: Optional[list[str]] = None,
        file_path: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        retry_count: int = 0,
        last_error: Optional[str] = None,
        expires_in_days: int = 7,
    ) -> ExportJob:
        export_format = (export_format or "").lower()
        if export_format not in {"csv", "json", "excel", "pdf"}:
            raise ValidationError("Unsupported analysis export format.")
        if status not in self.allowed_statuses:
            raise ValidationError(f"Unsupported export job status: {status}")

        existing = None
        if idempotency_key:
            existing = ExportJob.objects(
                organization_id=organization_id, idempotency_key=idempotency_key
            ).first()
        if existing:
            return existing

        job = ExportJob(
            organization_id=organization_id,
            analysis_run_id=str(analysis_run_id),
            analysis_id=str(analysis_id) if analysis_id else None,
            format=export_format,
            status=status,
            node_ids=node_ids or [],
            file_path=file_path,
            file_size_bytes=file_size_bytes,
            retry_count=retry_count,
            idempotency_key=idempotency_key,
            last_error=last_error,
            expired_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days),
        )
        job.save()
        self._sync_legacy_export(job)
        return job

    def get_job(self, export_job_id: str, organization_id: str) -> Optional[ExportJob]:
        query = {"id": export_job_id}
        if organization_id:
            query["organization_id"] = organization_id
        job = ExportJob.objects(**query).first()
        if job:
            return job
        legacy_query = {"id": export_job_id}
        if organization_id:
            legacy_query["organization_id"] = organization_id
        legacy = AnalysisExport.objects(**legacy_query).first()
        if legacy:
            return self._from_legacy_export(legacy)
        return None

    def get_job_for_run(
        self, analysis_run_id: str, export_format: str, organization_id: str
    ) -> Optional[ExportJob]:
        job = ExportJob.objects(
            analysis_run_id=str(analysis_run_id),
            format=(export_format or "").lower(),
            organization_id=organization_id,
        ).order_by("-created_at").first()
        if job:
            return job
        legacy = AnalysisExport.objects(
            run_id=str(analysis_run_id),
            format=(export_format or "").lower(),
            organization_id=organization_id,
        ).order_by("-created_at").first()
        if legacy:
            return self._from_legacy_export(legacy)
        return None

    def transition_status(
        self,
        job: ExportJob,
        status: str,
        *,
        file_path: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        last_error: Optional[str] = None,
    ) -> ExportJob:
        if status not in self.allowed_statuses:
            raise ValidationError(f"Unsupported export job status: {status}")
        current_status = str(job.status or "").lower()
        if (
            status == "completed"
            and current_status == "completed"
            and job.file_path
            and (file_path is None or file_path == job.file_path)
            and (
                file_size_bytes is None
                or job.file_size_bytes == file_size_bytes
            )
        ):
            return job
        job.status = status
        if file_path is not None:
            job.file_path = file_path
        if file_size_bytes is not None:
            job.file_size_bytes = file_size_bytes
        if last_error is not None:
            job.last_error = last_error
        job.save()
        self._sync_legacy_export(job)
        return job

    def record_failure(self, job: ExportJob, error: str) -> ExportJob:
        job.retry_count = int(job.retry_count or 0) + 1
        job.last_error = error
        return self.transition_status(job, "failed", last_error=error)

    def attach_file_path(
        self, job: ExportJob, file_path: str, file_size_bytes: Optional[int] = None
    ) -> ExportJob:
        return self.transition_status(
            job,
            "completed",
            file_path=file_path,
            file_size_bytes=file_size_bytes,
            last_error=None,
        )

    def expire_job(self, job: ExportJob) -> ExportJob:
        return self.transition_status(job, "expired")

    def _sync_legacy_export(self, job: ExportJob) -> None:
        legacy = AnalysisExport.objects(
            analysis_id=str(job.analysis_id or job.analysis_run_id),
            run_id=str(job.analysis_run_id),
            format=job.format,
            organization_id=job.organization_id,
        ).first()
        if not legacy:
            legacy = AnalysisExport(
                analysis_id=str(job.analysis_id or job.analysis_run_id),
                run_id=str(job.analysis_run_id),
                organization_id=job.organization_id,
                format=job.format,
            )
        legacy.status = job.status
        legacy.node_ids = job.node_ids
        legacy.file_path = job.file_path
        legacy.file_size_bytes = job.file_size_bytes
        legacy.retry_count = job.retry_count
        legacy.last_error = job.last_error
        legacy.idempotency_key = job.idempotency_key
        legacy.expires_at = job.expired_at
        legacy.save()

    def _from_legacy_export(self, legacy: AnalysisExport) -> ExportJob:
        job = ExportJob.objects(
            analysis_run_id=str(legacy.run_id),
            format=legacy.format,
            organization_id=legacy.organization_id,
        ).first()
        if job:
            return job
        job = ExportJob(
            id=legacy.id,
            organization_id=legacy.organization_id,
            analysis_run_id=str(legacy.run_id),
            analysis_id=str(legacy.analysis_id),
            format=legacy.format,
            status=legacy.status or "pending",
            node_ids=legacy.node_ids or [],
            file_path=legacy.file_path,
            file_size_bytes=legacy.file_size_bytes,
            retry_count=legacy.retry_count or 0,
            idempotency_key=legacy.idempotency_key,
            last_error=legacy.last_error,
            expired_at=legacy.expires_at,
            created_at=legacy.created_at,
            updated_at=legacy.updated_at,
        )
        job.save()
        return job


export_job_service = ExportJobService()
