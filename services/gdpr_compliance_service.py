from typing import Dict, Any, List, Optional
from mongoengine import QuerySet
from models.form import Form, Project
from models.response import FormResponse
from datetime import datetime, timedelta, timezone
from logger.unified_logger import app_logger
from config.redis import RedisConfig
import redis
import json


class GDPRComplianceService:
    """
    Service for GDPR compliance including data retention and hard deletion.
    Implements automated cleanup of soft-deleted records after retention period.
    """

    def __init__(self):
        redis_config = RedisConfig()
        self.redis_client = redis.Redis(
            host=redis_config.host,
            port=redis_config.port,
            db=0,  # Use DB 0 for GDPR operations
            password=redis_config.password,
            decode_responses=True,
            socket_timeout=redis_config.socket_timeout,
        )

    def get_soft_deleted_counts(
        self, collection: str, retention_days: int = 30
    ) -> Dict[str, Any]:
        """
        Count soft-deleted records by collection type.

        Args:
            collection: "forms" or "responses"
            retention_days: Days to keep soft-deleted records before hard deletion

        Returns:
            Dict with counts and metadata
        """
        app_logger.info(
            f"Counting soft-deleted {collection} with retention_days={retention_days}"
        )

        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

            if collection == "forms":
                from models.form import Form

                count = Form.objects(
                    is_deleted=True, deleted_at__lt=cutoff_date
                ).count()
            elif collection == "responses":
                from models.response import FormResponse

                count = FormResponse.objects(
                    is_deleted=True, deleted_at__lt=cutoff_date
                ).count()
            elif collection == "bulk_exports":
                count = BulkExport.objects(
                    status__in=["failed", "completed"], created_at__lt=cutoff_date
                ).count()
            elif collection == "snapshots":
                count = SummarySnapshot.objects(created_at__lt=cutoff_date).count()
            else:
                count = 0

            result = {
                "collection": collection,
                "retention_days": retention_days,
                "cutoff_date": cutoff_date.isoformat(),
                "count": count,
            }

            app_logger.info(f"Soft-deleted count for {collection}: {count}")
            return result

        except Exception as e:
            app_logger.error(f"Failed to count soft-deleted {collection}: {e}")
            return {
                "collection": collection,
                "retention_days": retention_days,
                "cutoff_date": cutoff_date.isoformat(),
                "count": 0,
                "error": str(e),
            }

    def prune_soft_deleted_records(
        self,
        collections: List[str] = None,
        retention_days: int = 30,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Permanently delete soft-deleted records older than retention period.

        Args:
            collections: List of collection types to process (default: ["forms", "responses"])
            retention_days: Number of days to keep soft-deleted records
            dry_run: If True, only count without deleting (for safety testing)

        Returns:
            Dict with deletion results and audit information
        """
        from models.form import Form
        from models.response import FormResponse
        from models.response import BulkExport, SummarySnapshot
        from logger.unified_logger import audit_logger
        from services.form_service import FormService
        from services.response_service import ResponseService

        app_logger.info(
            f"Starting GDPR prune: retention_days={retention_days}, dry_run={dry_run}, collections={collections}"
        )

        if collections is None:
            collections = ["forms", "responses", "bulk_exports", "snapshots"]

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        form_service = FormService()
        response_service = ResponseService()

        results = {
            "retention_days": retention_days,
            "cutoff_date": cutoff_date.isoformat(),
            "dry_run": dry_run,
            "deleted": {},
        }

        try:
            total_deleted = 0

            for collection in collections:
                collection_result = {
                    "collection": collection,
                    "count": 0,
                    "error": None,
                }

                if collection == "forms":
                    forms = Form.objects(is_deleted=True, deleted_at__lt=cutoff_date)
                    if not dry_run:
                        for form in forms:
                            form_service.delete(
                                str(form.id),
                                organization_id=form.organization_id,
                                hard_delete=True,
                            )
                            audit_logger.info(
                                f"GDPR: Hard deleted form {form.id} from org {form.organization_id}. "
                                f"Originally deleted at {form.deleted_at if hasattr(form, 'deleted_at') else 'unknown'}"
                            )
                    collection_result["count"] = forms.count()
                    total_deleted += forms.count()

                elif collection == "responses":
                    responses = FormResponse.objects(
                        is_deleted=True, deleted_at__lt=cutoff_date
                    )
                    if not dry_run:
                        for response in responses:
                            response_service.delete(
                                str(response.id),
                                organization_id=response.organization_id,
                                hard_delete=True,
                            )
                            audit_logger.info(
                                f"GDPR: Hard deleted response {response.id} from org {response.organization_id}. "
                                f"Originally deleted at {response.deleted_at if hasattr(response, 'deleted_at') else 'unknown'}"
                            )
                    collection_result["count"] = responses.count()
                    total_deleted += responses.count()

                elif collection == "bulk_exports":
                    exports = BulkExport.objects(
                        status__in=["failed", "completed"], created_at__lt=cutoff_date
                    )
                    if not dry_run:
                        for export in exports:
                            export.delete()
                            audit_logger.info(
                                f"GDPR: Hard deleted bulk export {export.id} from org {export.organization_id}. "
                                f"Created at {export.created_at if hasattr(export, 'created_at') else 'unknown'}"
                            )
                    collection_result["count"] = exports.count()
                    total_deleted += exports.count()

                elif collection == "snapshots":
                    snapshots = SummarySnapshot.objects(created_at__lt=cutoff_date)
                    if not dry_run:
                        for snapshot in snapshots:
                            snapshot.delete()
                            audit_logger.info(
                                f"GDPR: Hard deleted snapshot {snapshot.id} from form {snapshot.form_id if hasattr(snapshot, 'form_id') else 'unknown'}. "
                                f"Created at {snapshot.created_at if hasattr(snapshot, 'created_at') else 'unknown'}"
                            )
                    collection_result["count"] = snapshots.count()
                    total_deleted += snapshots.count()

                results["deleted"][collection] = collection_result

            results["total_deleted"] = total_deleted

            audit_logger.info(
                f"GDPR prune completed: {total_deleted} records {'would be ' if dry_run else ''}permanently deleted. "
                f"Collections: {collections}"
            )

            app_logger.info(
                f"GDPR prune completed: {total_deleted} records {'would be ' if dry_run else ''}permanently deleted"
            )

            return results

        except Exception as e:
            app_logger.error(f"GDPR prune failed: {e}", exc_info=True)
            return {
                "retention_days": retention_days,
                "cutoff_date": cutoff_date.isoformat(),
                "dry_run": dry_run,
                "total_deleted": total_deleted if "total_deleted" in locals() else 0,
                "error": str(e),
                "deleted": results.get("deleted", {}) if "deleted" in results else {},
            }


gdpr_compliance_service = GDPRComplianceService()
