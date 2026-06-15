"""
routes/v1/admin/tenant_compliance_route.py
Routes for tenant quota settings, usage tracking, legal holds, and retention policies.
"""

from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt
from logger.unified_logger import app_logger, audit_logger
from services.tenant_service import TenantService
from services.compliance_service import ComplianceService
from tasks.compliance_tasks import get_audit_export_dir
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
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
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
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
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


@tenant_compliance_bp.route("/audit/archive", methods=["POST"])
@jwt_required()
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def trigger_audit_archive():
    """Trigger archival of older audit logs to cold storage."""
    claims = get_jwt()
    org_id = claims.get("organization_id")
    if not org_id:
        return error_response(message="Organization ID not found in token context", status_code=400)

    data = request.get_json(silent=True) or {}
    days = data.get("days", 90)
    export_format = data.get("format", "json")
    if export_format not in ("csv", "json"):
        return error_response(message="Format must be csv or json", status_code=400)

    try:
        days = int(days)
    except (TypeError, ValueError):
        return error_response(message="days must be an integer", status_code=400)
    if days < 1:
        return error_response(message="days must be at least 1", status_code=400)

    from tasks.compliance_tasks import archive_old_audit_logs_task

    task = archive_old_audit_logs_task.delay(days=days, format=export_format)
    audit_logger.info(
        "Audit archive task triggered for org=%s days=%s format=%s task_id=%s",
        org_id,
        days,
        export_format,
        task.id,
    )
    return success_response(
        data={
            "task_id": task.id,
            "status": "PENDING",
            "days": days,
            "format": export_format,
        },
        message="Audit archive task triggered",
        status_code=202,
    )


@tenant_compliance_bp.route("/evidence", methods=["GET"])
@jwt_required()
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def get_evidence_logs():
    """Retrieves compliance evidence logs."""
    claims = get_jwt()
    org_id = claims.get("organization_id")
    if not org_id:
        return error_response("Organization ID not found in token context", 400)
        
    logs = EvidenceLog.objects(organization_id=org_id).order_by("-timestamp")
    serialized = [log.to_dict() for log in logs]
    return success_response(data=serialized, message="Evidence logs retrieved")


@tenant_compliance_bp.route("/audit/export", methods=["POST"])
@jwt_required()
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def trigger_audit_export():
    """Trigger background execution of tenant audit log export."""
    claims = get_jwt()
    org_id = claims.get("organization_id")
    if not org_id:
        return error_response(message="Organization ID not found in token context", status_code=400)
        
    data = request.get_json(silent=True) or {}
    export_format = data.get("format", "csv")
    if export_format not in ("csv", "json"):
        return error_response(message="Format must be csv or json", status_code=400)
        
    from tasks.compliance_tasks import export_tenant_audit_logs_task
    task = export_tenant_audit_logs_task.delay(org_id, export_format)
    
    return success_response(
        data={
            "task_id": task.id,
            "status": "PENDING"
        },
        message="Audit log export task triggered",
        status_code=202
    )


@tenant_compliance_bp.route("/audit/export/status/<task_id>", methods=["GET"])
@jwt_required()
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def get_audit_export_status(task_id):
    """Retrieve Celery background task status for audit exports."""
    from celery.result import AsyncResult
    res = AsyncResult(task_id)
    
    download_url = None
    if res.status == "SUCCESS":
        result_val = res.result
        if isinstance(result_val, dict) and "export_uuid" in result_val:
            format_ext = result_val.get("filename", "").split(".")[-1] or "csv"
            download_url = (
                f"/api/internal/v1/compliance/audit/export/download/"
                f"{result_val['export_uuid']}.{format_ext}"
            )
            
    return success_response(
        data={
            "task_id": task_id,
            "status": res.status,
            "result": res.result if res.status == "SUCCESS" else None,
            "download_url": download_url
        },
        message="Export status retrieved"
    )


@tenant_compliance_bp.route("/audit/export/download/<export_uuid>.<format_ext>", methods=["GET"])
@jwt_required()
@require_roles(Role.ADMIN.value, Role.SUPERADMIN.value)
def download_audit_export(export_uuid, format_ext):
    """Downloads a tenant-isolated audit export file."""
    import os
    claims = get_jwt()
    org_id = claims.get("organization_id")
    if not org_id:
        return error_response(message="Organization ID not found in token context", status_code=400)
    
    if format_ext not in ("csv", "json"):
        return error_response(message="Invalid file format", status_code=400)
        
    filename = f"audit_export_{org_id}_{export_uuid}.{format_ext}"
    
    from flask import send_from_directory
    export_dir = get_audit_export_dir()
    
    if not os.path.exists(os.path.join(export_dir, filename)):
        return error_response(message="Export file not found or unauthorized access", status_code=404)
        
    return send_from_directory(export_dir, filename, as_attachment=True)
