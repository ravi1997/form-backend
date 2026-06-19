"""
services/org_service.py
Service layer for Organization management.
"""

from typing import List, Dict, Any
from logger.unified_logger import app_logger, audit_logger
from services.base import BaseService
from models.identity import Organization as _Organization
Organization = _Organization
from models.identity import TenantSettings
from models import User
from models.form import Form
from models.response import FormResponse
from models.workflow import WorkflowInstance
from schemas.org import OrgCreateSchema, OrgSchema
from utils.exceptions import ValidationError, NotFoundError

class OrgService(BaseService):
    def __init__(self):
        super().__init__(model=Organization, schema=OrgSchema)

    def create_org(self, schema: OrgCreateSchema) -> OrgSchema:
        """
        Creates an organization and atomically ensures linked TenantSettings exist.
        """
        app_logger.info(f"Creating organization: {schema.organization_id}")
        
        # Check if organization already exists
        existing = Organization.objects(organization_id=schema.organization_id).first()
        if existing:
            raise ValidationError(f"Organization with ID {schema.organization_id} already exists.")

        org = Organization(
            organization_id=schema.organization_id,
            name=schema.name,
            display_name=schema.display_name,
            status="active",
            contact_email=schema.contact_email,
            description=schema.description,
            metadata=schema.metadata
        )
        org.save()

        # Atomically / immediately ensure tenant settings exist
        TenantSettings.get_or_create(schema.organization_id)

        audit_logger.info(f"AUDIT: Organization {schema.organization_id} created successfully.")
        return self._to_schema(org)

    def get_all_orgs(self) -> List[OrgSchema]:
        """Returns all registered organizations."""
        orgs = Organization.objects()
        return [self._to_schema(org) for org in orgs]

    def update_status(self, organization_id: str, status: str) -> OrgSchema:
        """Updates organization status (active or suspended)."""
        if status not in ["active", "suspended"]:
            raise ValidationError("Invalid status. Must be 'active' or 'suspended'.")

        org = Organization.objects(organization_id=organization_id).first()
        if not org:
            raise NotFoundError(f"Organization {organization_id} not found.")

        old_status = org.status
        org.status = status
        org.save()

        # Update TenantSettings active status as well to match suspension state
        tenant_settings = TenantSettings.get_or_create(organization_id)
        tenant_settings.is_active = (status == "active")
        tenant_settings.save()

        audit_logger.info(
            f"AUDIT: Organization {organization_id} status updated from {old_status} to {status}."
        )
        return self._to_schema(org)

    def assign_admin(self, organization_id: str, admin_user_id: str) -> OrgSchema:
        """Assigns an administrative user to the organization and grants them the 'admin' role."""
        org = Organization.objects(organization_id=organization_id).first()
        if not org:
            raise NotFoundError(f"Organization {organization_id} not found.")

        # Verify the user exists
        user = User.objects(id=admin_user_id).first()
        if not user:
            raise NotFoundError(f"User {admin_user_id} not found.")

        # Update organization admin reference
        org.admin_user_id = admin_user_id
        org.save()

        # Ensure the user's role includes 'admin'
        if not getattr(user, "roles", None):
            user.roles = []
        if "admin" not in user.roles:
            user.roles.append("admin")
            user.save()

        audit_logger.info(
            f"AUDIT: Designated user {admin_user_id} as admin for organization {organization_id}."
        )
        return self._to_schema(org)

    def get_stats(self, organization_id: str) -> Dict[str, Any]:
        """
        Calculates and returns standard tenant metrics.
        Metrics:
        - total_forms
        - total_submissions
        - active_users
        - storage_mb
        - forms_last_30_days
        - submissions_last_30_days
        - pending_workflow_instances
        - last_activity
        """
        org = Organization.objects(organization_id=organization_id).first()
        if not org:
            raise NotFoundError(f"Organization {organization_id} not found.")

        tenant_settings = TenantSettings.get_or_create(organization_id)
        from datetime import datetime, timedelta, timezone

        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

        total_forms = Form.objects(organization_id=organization_id, is_deleted=False).count()
        total_submissions = FormResponse.objects(organization_id=organization_id, is_deleted=False).count()
        
        # In this platform, active_users can be found by users belonging to organization_id
        active_users = User.objects(organization_id=organization_id, is_deleted=False).count()
        
        # Calculate storage in MB from bytes stored in tenant_settings
        storage_mb = round(tenant_settings.usage_storage_bytes / (1024 * 1024), 2) if tenant_settings.usage_storage_bytes else 0.0

        forms_last_30_days = Form.objects(
            organization_id=organization_id, 
            is_deleted=False, 
            created_at__gte=thirty_days_ago
        ).count()

        submissions_last_30_days = FormResponse.objects(
            organization_id=organization_id,
            is_deleted=False,
            created_at__gte=thirty_days_ago
        ).count()

        # Pending workflow instances
        pending_workflow_instances = WorkflowInstance.objects(
            organization_id=organization_id,
            status="pending"
        ).count()

        # Find the last activity timestamp (latest updated_at across forms, responses, workflows)
        last_activity = None
        
        latest_form = Form.objects(organization_id=organization_id).order_by("-updated_at").first()
        latest_response = FormResponse.objects(organization_id=organization_id).order_by("-updated_at").first()
        latest_workflow = WorkflowInstance.objects(organization_id=organization_id).order_by("-updated_at").first()

        dates = []
        if latest_form:
            dates.append(latest_form.updated_at)
        if latest_response:
            dates.append(latest_response.updated_at)
        if latest_workflow:
            dates.append(latest_workflow.updated_at)

        if dates:
            last_activity = max(dates).isoformat()

        return {
            "organization_id": organization_id,
            "total_forms": total_forms,
            "total_submissions": total_submissions,
            "active_users": active_users,
            "storage_mb": storage_mb,
            "forms_last_30_days": forms_last_30_days,
            "submissions_last_30_days": submissions_last_30_days,
            "pending_workflow_instances": pending_workflow_instances,
            "last_activity": last_activity
        }
