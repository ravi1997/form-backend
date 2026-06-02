"""
services/tenant_service.py
Handles tenant quota settings, usage tracking, and quota validation logic.
"""

from logger.unified_logger import app_logger, audit_logger
from services.base import BaseService
from models.TenantSettings import TenantSettings
from models.Form import Form
from models.Response import FormResponse
from utils.exceptions import ValidationError

class TenantService(BaseService):
    def __init__(self):
        super().__init__(model=TenantSettings, schema=None)

    def get_settings(self, organization_id: str) -> TenantSettings:
        """Retrieves or creates TenantSettings for the organization."""
        return TenantSettings.get_or_create(organization_id)

    def update_quotas(self, organization_id: str, max_forms: int = None, max_submissions: int = None, storage_limit_mb: int = None, retention_days: int = None) -> TenantSettings:
        """Updates the resource quotas for a specific tenant."""
        settings = TenantSettings.get_or_create(organization_id)
        if max_forms is not None:
            settings.max_forms = max_forms
        if max_submissions is not None:
            settings.max_submissions = max_submissions
        if storage_limit_mb is not None:
            settings.storage_limit_mb = storage_limit_mb
        if retention_days is not None:
            settings.retention_days = retention_days
        settings.save()
        audit_logger.info(f"AUDIT: Quotas updated for organization {organization_id}")
        return settings

    def recalculate_usage(self, organization_id: str) -> TenantSettings:
        """Recalculates the usage metrics for a specific tenant."""
        settings = TenantSettings.get_or_create(organization_id)
        
        # Count active forms and responses
        forms_count = Form.objects(organization_id=organization_id, is_deleted=False).count()
        submissions_count = FormResponse.objects(organization_id=organization_id, is_deleted=False).count()
        
        settings.usage_forms_count = forms_count
        settings.usage_submissions_count = submissions_count
        settings.save()
        
        app_logger.info(f"Recalculated usage for organization {organization_id}: forms={forms_count}, submissions={submissions_count}")
        return settings

    def check_form_quota(self, organization_id: str) -> None:
        """Validates if the tenant is allowed to create another form."""
        settings = TenantSettings.get_or_create(organization_id)
        current_forms = Form.objects(organization_id=organization_id, is_deleted=False).count()
        if current_forms >= settings.max_forms:
            raise ValidationError(f"Form limit quota exceeded ({settings.max_forms} max).")

    def check_submission_quota(self, organization_id: str) -> None:
        """Validates if the tenant is allowed to receive another submission."""
        settings = TenantSettings.get_or_create(organization_id)
        current_submissions = FormResponse.objects(organization_id=organization_id, is_deleted=False).count()
        if current_submissions >= settings.max_submissions:
            raise ValidationError(f"Submissions limit quota exceeded ({settings.max_submissions} max).")
