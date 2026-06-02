"""
routes/v1/admin/tenant_compliance_route.py
Routes for tenant quota settings, usage tracking, legal holds, and retention policies.
"""

from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt
from logger.unified_logger import app_logger, audit_logger
from services.tenant_service import TenantService
from services.compliance_service import ComplianceService
from models.EvidenceLog import EvidenceLog
from utils.response_helper import success_response, error_response
from utils.security import require_roles
from models.User import Role

tenant_compliance_bp = Blueprint("tenant_compliance", __name__)
tenant_service = TenantService()
compliance_service = ComplianceService()

# ── Tenant settings & Quotas ──

@tenant_compliance_bp.route("/settings", methods=["GET"])
@jwt_required()
def get_tenant_settings():
    """Retrieve tenant quota settings and current usage."""
    claims = get_jwt()
    org_id = claims.get("organization_id")
    if not org_id:
        return error_response("Organization ID not found in token context", 400)
    
    settings = tenant_service.get_settings(org_id)
    return success_response(data=settings.to_dict(), message="Tenant settings retrieved")


@tenant_compliance_bp.route("/settings", methods=["PUT"])
@jwt_required()
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def update_tenant_settings():
    """Update tenant quotas."""
    claims = get_jwt()
    org_id = claims.get("organization_id")
    if not org_id:
        return error_response("Organization ID not found in token context", 400)
        
    data = request.get_json(silent=True) or {}
    max_forms = data.get("max_forms")
    max_submissions = data.get("max_submissions")
    storage_limit_mb = data.get("storage_limit_mb")
    retention_days = data.get("retention_days")
    
    settings = tenant_service.update_quotas(
        organization_id=org_id,
        max_forms=max_forms,
        max_submissions=max_submissions,
        storage_limit_mb=storage_limit_mb,
        retention_days=retention_days
    )
    return success_response(data=settings.to_dict(), message="Tenant settings updated")


@tenant_compliance_bp.route("/recalculate", methods=["POST"])
@jwt_required()
def recalculate_tenant_usage():
    """Manually trigger recalculation of tenant usage metrics."""
    claims = get_jwt()
    org_id = claims.get("organization_id")
    if not org_id:
        return error_response("Organization ID not found in token context", 400)
        
    settings = tenant_service.recalculate_usage(org_id)
    return success_response(data=settings.to_dict(), message="Tenant usage metrics recalculated")


# ── Legal holds ──

@tenant_compliance_bp.route("/legal-hold", methods=["POST"])
@jwt_required()
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def apply_legal_hold():
    """Applies a legal hold to a form or response."""
    claims = get_jwt()
    org_id = claims.get("organization_id")
    actor = claims.get("sub") or "compliance_officer"
    
    data = request.get_json(silent=True) or {}
    target_type = data.get("target_type")
    target_id = data.get("target_id")
    reason = data.get("reason", "Legal investigation hold")
    
    if target_type not in ("form", "response") or not target_id:
        return error_response("Invalid target_type or target_id", 400)
        
    hold = compliance_service.apply_legal_hold(
        organization_id=org_id,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        held_by=actor
    )
    return success_response(data=hold.to_dict(), message=f"Legal hold applied on {target_type}")


@tenant_compliance_bp.route("/legal-hold", methods=["DELETE"])
@jwt_required()
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def release_legal_hold():
    """Releases active legal holds from a form or response."""
    claims = get_jwt()
    org_id = claims.get("organization_id")
    actor = claims.get("sub") or "compliance_officer"
    
    data = request.get_json(silent=True) or {}
    target_type = data.get("target_type")
    target_id = data.get("target_id")
    
    if target_type not in ("form", "response") or not target_id:
        return error_response("Invalid target_type or target_id", 400)
        
    released = compliance_service.release_legal_hold(
        organization_id=org_id,
        target_type=target_type,
        target_id=target_id,
        released_by=actor
    )
    if released:
        return success_response(message=f"Legal hold released on {target_type}")
    return error_response("No active legal hold found to release", 404)


# ── Retention & Evidence ──

@tenant_compliance_bp.route("/retention/prune", methods=["POST"])
@jwt_required()
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def prune_expired_responses():
    """Trigger manual execution of response retention policies."""
    claims = get_jwt()
    org_id = claims.get("organization_id")
    actor = claims.get("sub") or "admin"
    
    result = compliance_service.execute_retention_policy(org_id, actor)
    return success_response(data=result, message="Retention policy executed successfully")


@tenant_compliance_bp.route("/evidence", methods=["GET"])
@jwt_required()
def get_evidence_logs():
    """Retrieves compliance evidence logs."""
    claims = get_jwt()
    org_id = claims.get("organization_id")
    if not org_id:
        return error_response("Organization ID not found in token context", 400)
        
    logs = EvidenceLog.objects(organization_id=org_id).order_by("-timestamp")
    serialized = [log.to_dict() for log in logs]
    return success_response(data=serialized, message="Evidence logs retrieved")
