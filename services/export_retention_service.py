from datetime import datetime, timezone, timedelta

from logger.unified_logger import app_logger, error_logger
from models.ExportJob import ExportJob
from config.settings import settings
from services.storage_backend import export_storage_backend


class ExportRetentionService:
    def prune_expired_exports(self) -> dict:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.EXPORT_TTL_HOURS)
        expired_exports = []
        for export in ExportJob.objects():
            expiry_point = export.expired_at or export.created_at
            if expiry_point:
                if expiry_point.tzinfo is None:
                    expiry_point = expiry_point.replace(tzinfo=timezone.utc)
                if expiry_point < cutoff:
                    expired_exports.append(export)
        deleted = 0
        missing = 0
        for export in expired_exports:
            file_path = export.file_path
            try:
                if file_path and export_storage_backend.exists(file_path):
                    export_storage_backend.delete(file_path)
                    deleted += 1
                else:
                    missing += 1
                export.status = "expired"
                export.file_path = None
                export.save()
            except Exception as exc:
                error_logger.error(
                    f"Failed to prune export {export.id}: {exc}", exc_info=True
                )
        app_logger.info(
            f"Export retention pruning completed. deleted={deleted}, missing={missing}"
        )
        return {"deleted": deleted, "missing": missing}


export_retention_service = ExportRetentionService()
