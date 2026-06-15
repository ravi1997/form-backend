from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from logger.unified_logger import app_logger, error_logger
from models.AuditLog import AuditLog


class AuditArchiveService:
    """Archive older audit logs to local cold storage."""

    archive_dir = Path("/app/logs/cold_storage")

    @classmethod
    def archive_older_than(cls, days: int = 90, format: str = "json") -> dict[str, int | str]:
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 24 * 60 * 60)
        logs = AuditLog.objects(is_deleted=False).order_by("timestamp")
        eligible = [log for log in logs if log.timestamp and log.timestamp.timestamp() < cutoff]
        cls.archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        filename = f"audit_logs_archive_{stamp}.{format}"
        file_path = cls.archive_dir / filename

        try:
            if format.lower() == "csv":
                with file_path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(["id", "timestamp", "actor_id", "action", "resource_type", "resource_id", "metadata"])
                    for log in eligible:
                        writer.writerow([
                            str(log.id),
                            log.timestamp.isoformat() if log.timestamp else "",
                            log.actor_id,
                            log.action,
                            log.resource_type or "",
                            log.resource_id or "",
                            json.dumps(log.metadata or {}, default=str),
                        ])
            else:
                payload = [
                    {
                        "id": str(log.id),
                        "timestamp": log.timestamp.isoformat() if log.timestamp else "",
                        "actor_id": log.actor_id,
                        "action": log.action,
                        "resource_type": log.resource_type,
                        "resource_id": log.resource_id,
                        "metadata": log.metadata,
                    }
                    for log in eligible
                ]
                with file_path.open("w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2)

            for log in eligible:
                log.delete()

            app_logger.info("Archived %s audit logs to %s", len(eligible), file_path)
            return {"count": len(eligible), "filename": filename}
        except Exception as exc:
            error_logger.error("Audit archive failed: %s", exc, exc_info=True)
            raise
