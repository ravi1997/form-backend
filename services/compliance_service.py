"""
services/compliance_service.py
Handles compliance requirements including legal holds, retention policy execution, and evidence tracking.
"""

from datetime import datetime, timedelta, timezone
from mongoengine import Q
from logger.unified_logger import app_logger, error_logger, audit_logger
from services.base import BaseService
from models.LegalHold import LegalHold
from models.EvidenceLog import EvidenceLog
from models.Response import FormResponse
from models.Form import Form
from models.TenantSettings import TenantSettings
from utils.exceptions import ValidationError

class ComplianceService(BaseService):
    def __init__(self):
        super().__init__(model=LegalHold, schema=None)

    def is_held(self, target_type: str, target_id: str) -> bool:
        """
        Check if a form or response is currently under an active legal hold.
        """
        hold = LegalHold.objects(
            target_type=target_type,
            target_id=str(target_id),
            is_active=True,
            is_deleted=False
        ).first()
        return hold is not None

    def apply_legal_hold(self, organization_id: str, target_type: str, target_id: str, reason: str, held_by: str) -> LegalHold:
        """
        Applies a legal hold to a form or a response.
        """
        # Check if already held
        existing = LegalHold.objects(
            organization_id=organization_id,
            target_type=target_type,
            target_id=str(target_id),
            is_active=True
        ).first()
        if existing:
            return existing

        hold = LegalHold(
            organization_id=organization_id,
            target_type=target_type,
            target_id=str(target_id),
            reason=reason,
            held_by=held_by,
            is_active=True
        )
        hold.save()

        # Write evidence log
        EvidenceLog(
            organization_id=organization_id,
            event_type="legal_hold_created",
            actor_id=held_by,
            details={
                "target_type": target_type,
                "target_id": str(target_id),
                "reason": reason,
                "hold_id": str(hold.id)
            }
        ).save()

        audit_logger.info(f"AUDIT: Legal hold applied on {target_type} {target_id} by {held_by}")
        return hold

    def release_legal_hold(self, organization_id: str, target_type: str, target_id: str, released_by: str) -> bool:
        """
        Releases an active legal hold on a form or response.
        """
        holds = LegalHold.objects(
            organization_id=organization_id,
            target_type=target_type,
            target_id=str(target_id),
            is_active=True
        )
        if not holds:
            return False

        for hold in holds:
            hold.is_active = False
            hold.save()

            # Write evidence log
            EvidenceLog(
                organization_id=organization_id,
                event_type="legal_hold_released",
                actor_id=released_by,
                details={
                    "target_type": target_type,
                    "target_id": str(target_id),
                    "hold_id": str(hold.id)
                }
            ).save()

        audit_logger.info(f"AUDIT: Legal holds released on {target_type} {target_id} by {released_by}")
        return True

    def execute_retention_policy(self, organization_id: str, actor_id: str) -> dict:
        """
        Finds and deletes expired responses based on tenant's retention policy.
        Bypasses soft delete and deletes permanently, but strictly blocks if legal hold is active.
        """
        tenant_settings = TenantSettings.get_or_create(organization_id)
        default_retention_days = tenant_settings.retention_days
        if not default_retention_days or default_retention_days <= 0:
            default_retention_days = None

        # Evaluate each response against its form-specific retention setting when present.
        expired_responses = FormResponse.objects(
            organization_id=organization_id,
            is_deleted=False,
        )

        pruned_count = 0
        held_count = 0
        pruned_ids = []
        form_retention_cache = {}
        now = datetime.now(timezone.utc)

        for resp in expired_responses:
            if not resp.submitted_at:
                continue

            # Check legal hold on the response itself or its form
            form_ref = getattr(resp, "form", None)
            if form_ref is None and hasattr(resp, "_data"):
                form_ref = resp._data.get("form")
            form_id_str = (
                str(form_ref.id)
                if hasattr(form_ref, "id")
                else str(form_ref)
                if form_ref
                else None
            )

            retention_days = default_retention_days
            if form_id_str:
                if form_id_str not in form_retention_cache:
                    form_doc = Form.objects(id=form_id_str, organization_id=organization_id).only(
                        "data_export_settings"
                    ).first()
                    form_settings = dict(getattr(form_doc, "data_export_settings", None) or {})
                    form_retention_cache[form_id_str] = form_settings.get("retention_days")
                form_retention_days = form_retention_cache.get(form_id_str)
                if form_retention_days is not None:
                    retention_days = form_retention_days

            if not retention_days or retention_days <= 0:
                continue
            threshold_date = now - timedelta(days=retention_days)
            if resp.submitted_at >= threshold_date:
                continue

            if self.is_held("response", resp.id) or (form_id_str and self.is_held("form", form_id_str)):
                held_count += 1
                app_logger.info(f"Skipping expired response {resp.id} due to active legal hold")
                continue

            resp_id_str = str(resp.id)

            # Hard delete the response
            resp.delete()
            pruned_count += 1
            pruned_ids.append(resp_id_str)

            # Log evidence
            EvidenceLog(
                organization_id=organization_id,
                event_type="retention_prune",
                actor_id=actor_id,
                details={
                    "response_id": resp_id_str,
                    "form_id": form_id_str or "",
                    "submitted_at": resp.submitted_at.isoformat()
                }
            ).save()

        # Update tenant usage submissions count
        if pruned_count > 0:
            total_active_submissions = FormResponse.objects(organization_id=organization_id, is_deleted=False).count()
            settings.usage_submissions_count = total_active_submissions
            settings.save()

        audit_logger.info(f"AUDIT: Executed retention policy for tenant {organization_id}. Pruned: {pruned_count}, Held: {held_count}")
        return {"pruned_count": pruned_count, "held_count": held_count, "pruned_ids": pruned_ids}
