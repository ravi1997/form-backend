"""
routes/v1/admin/compliance_route.py
Admin routes for compliance management.
"""

from flask import Blueprint, request, jsonify
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.security import require_roles
from utils.response_helper import success_response, error_response
from services.compliance_registry_service import compliance_registry_service
from logger.unified_logger import app_logger, error_logger, audit_logger

compliance_bp = Blueprint("compliance_bp", __name__)


@compliance_bp.route("/standards", methods=["GET"])
@swag_from({
    "tags": ["Compliance"],
    "responses": {"200": {"description": "List of compliance standards"}}
})
@jwt_required()
@require_roles("admin", "superadmin")
def list_compliance_standards():
    """Get all compliance standards."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} requesting compliance standards list")
    
    try:
        include_system = request.args.get('include_system', 'true').lower() == 'true'
        standards = compliance_registry_service.get_compliance_standards(include_system=include_system)
        
        standards_data = []
        for standard in standards:
            standards_data.append({
                "id": str(standard.id),
                "code": standard.code,
                "name": standard.name,
                "description": standard.description,
                "region": standard.region,
                "version": standard.version,
                "is_system": standard.is_system,
                "behavioral_constraints": standard.behavioral_constraints,
                "requirements": standard.requirements,
                "created_at": standard.created_at.isoformat() if standard.created_at else None,
                "updated_at": standard.updated_at.isoformat() if standard.updated_at else None
            })
        
        return success_response(data=standards_data)
    except Exception as e:
        error_logger.error(f"Failed to list compliance standards: {e}", exc_info=True)
        return error_response(message="Failed to list compliance standards", status_code=500)


@compliance_bp.route("/standards", methods=["POST"])
@swag_from({
    "tags": ["Compliance"],
    "responses": {"201": {"description": "Compliance standard created"}}
})
@jwt_required()
@require_roles("superadmin")
def create_compliance_standard():
    """Create a new compliance standard."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} creating compliance standard")
    
    try:
        data = request.get_json()
        if not data:
            return error_response(message="Request data is required", status_code=400)
        
        data['created_by'] = admin_id
        standard = compliance_registry_service.create_compliance_standard(**data)
        
        return success_response(
            data={
                "id": str(standard.id),
                "code": standard.code,
                "name": standard.name,
                "description": standard.description,
                "region": standard.region,
                "version": standard.version,
                "is_system": standard.is_system,
                "created_at": standard.created_at.isoformat()
            },
            message="Compliance standard created successfully",
            status_code=201
        )
    except Exception as e:
        error_logger.error(f"Failed to create compliance standard: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@compliance_bp.route("/standards/<standard_id>", methods=["GET"])
@swag_from({
    "tags": ["Compliance"],
    "parameters": [{"name": "standard_id", "in": "path", "type": "string", "required": True}],
    "responses": {"200": {"description": "Compliance standard details"}}
})
@jwt_required()
@require_roles("admin", "superadmin")
def get_compliance_standard(standard_id):
    """Get a specific compliance standard."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} requesting compliance standard {standard_id}")
    
    try:
        standard = compliance_registry_service.get_compliance_standard(standard_id)
        
        return success_response(data={
            "id": str(standard.id),
            "code": standard.code,
            "name": standard.name,
            "description": standard.description,
            "region": standard.region,
            "version": standard.version,
            "is_system": standard.is_system,
            "behavioral_constraints": standard.behavioral_constraints,
            "requirements": standard.requirements,
            "created_at": standard.created_at.isoformat() if standard.created_at else None,
            "updated_at": standard.updated_at.isoformat() if standard.updated_at else None
        })
    except Exception as e:
        error_logger.error(f"Failed to get compliance standard: {e}", exc_info=True)
        return error_response(message=str(e), status_code=404)


@compliance_bp.route("/standards/<standard_id>", methods=["PUT"])
@swag_from({
    "tags": ["Compliance"],
    "parameters": [{"name": "standard_id", "in": "path", "type": "string", "required": True}],
    "responses": {"200": {"description": "Compliance standard updated"}}
})
@jwt_required()
@require_roles("superadmin")
def update_compliance_standard(standard_id):
    """Update a compliance standard."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} updating compliance standard {standard_id}")
    
    try:
        data = request.get_json()
        if not data:
            return error_response(message="Request data is required", status_code=400)
        
        standard = compliance_registry_service.update_compliance_standard(standard_id, **data)
        
        return success_response(data={
            "id": str(standard.id),
            "code": standard.code,
            "name": standard.name,
            "description": standard.description,
            "region": standard.region,
            "version": standard.version,
            "is_system": standard.is_system,
            "updated_at": standard.updated_at.isoformat()
        })
    except Exception as e:
        error_logger.error(f"Failed to update compliance standard: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@compliance_bp.route("/standards/<standard_id>", methods=["DELETE"])
@swag_from({
    "tags": ["Compliance"],
    "parameters": [{"name": "standard_id", "in": "path", "type": "string", "required": True}],
    "responses": {"200": {"description": "Compliance standard deleted"}}
})
@jwt_required()
@require_roles("superadmin")
def delete_compliance_standard(standard_id):
    """Delete a compliance standard."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} deleting compliance standard {standard_id}")
    
    try:
        compliance_registry_service.delete_compliance_standard(standard_id)
        return success_response(message="Compliance standard deleted successfully")
    except Exception as e:
        error_logger.error(f"Failed to delete compliance standard: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@compliance_bp.route("/organizations/<org_id>/compliance", methods=["GET"])
@swag_from({
    "tags": ["Compliance"],
    "parameters": [{"name": "org_id", "in": "path", "type": "string", "required": True}],
    "responses": {"200": {"description": "Organization compliance status"}}
})
@jwt_required()
@require_roles("admin", "superadmin")
def get_org_compliance(org_id):
    """Get compliance status for an organization."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} requesting compliance for org {org_id}")
    
    try:
        compliance_list = compliance_registry_service.get_org_compliance(org_id)
        
        compliance_data = []
        for compliance in compliance_list:
            compliance_data.append({
                "id": str(compliance.id),
                "org_id": compliance.org_id,
                "compliance_id": str(compliance.compliance_id.id),
                "compliance_code": compliance.compliance_id.code,
                "compliance_name": compliance.compliance_id.name,
                "status": compliance.status,
                "adopted_at": compliance.adopted_at.isoformat() if compliance.adopted_at else None,
                "adopted_by": str(compliance.adopted_by) if compliance.adopted_by else None,
                "effective_from": compliance.effective_from.isoformat() if compliance.effective_from else None,
                "expires_at": compliance.expires_at.isoformat() if compliance.expires_at else None,
                "audit_frequency": compliance.audit_frequency,
                "notes": compliance.notes
            })
        
        return success_response(data=compliance_data)
    except Exception as e:
        error_logger.error(f"Failed to get organization compliance: {e}", exc_info=True)
        return error_response(message="Failed to get organization compliance", status_code=500)


@compliance_bp.route("/organizations/<org_id>/compliance", methods=["POST"])
@swag_from({
    "tags": ["Compliance"],
    "parameters": [{"name": "org_id", "in": "path", "type": "string", "required": True}],
    "responses": {"201": {"description": "Compliance standard adopted"}}
})
@jwt_required()
@require_roles("admin", "superadmin")
def adopt_compliance_standard(org_id):
    """Adopt a compliance standard for an organization."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} adopting compliance standard for org {org_id}")
    
    try:
        data = request.get_json()
        if not data or not data.get('compliance_id'):
            return error_response(message="compliance_id is required", status_code=400)
        
        org_compliance = compliance_registry_service.adopt_compliance_standard(
            org_id=org_id,
            compliance_id=data['compliance_id'],
            adopted_by=admin_id,
            **data
        )
        
        return success_response(
            data={
                "id": str(org_compliance.id),
                "org_id": org_compliance.org_id,
                "compliance_id": str(org_compliance.compliance_id.id),
                "compliance_code": org_compliance.compliance_id.code,
                "status": org_compliance.status,
                "adopted_at": org_compliance.adopted_at.isoformat()
            },
            message="Compliance standard adopted successfully",
            status_code=201
        )
    except Exception as e:
        error_logger.error(f"Failed to adopt compliance standard: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@compliance_bp.route("/organizations/<org_id>/compliance/<compliance_id>", methods=["PUT"])
@swag_from({
    "tags": ["Compliance"],
    "parameters": [
        {"name": "org_id", "in": "path", "type": "string", "required": True},
        {"name": "compliance_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {"200": {"description": "Organization compliance updated"}}
})
@jwt_required()
@require_roles("admin", "superadmin")
def update_org_compliance(org_id, compliance_id):
    """Update organization compliance record."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} updating compliance for org {org_id}")
    
    try:
        data = request.get_json()
        if not data:
            return error_response(message="Request data is required", status_code=400)
        
        org_compliance = compliance_registry_service.update_org_compliance(compliance_id, **data)
        
        return success_response(data={
            "id": str(org_compliance.id),
            "org_id": org_compliance.org_id,
            "compliance_id": str(org_compliance.compliance_id.id),
            "compliance_code": org_compliance.compliance_id.code,
            "status": org_compliance.status,
            "updated_at": org_compliance.updated_at.isoformat() if org_compliance.updated_at else None
        })
    except Exception as e:
        error_logger.error(f"Failed to update organization compliance: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@compliance_bp.route("/organizations/<org_id>/compliance/<compliance_id>/suspend", methods=["POST"])
@swag_from({
    "tags": ["Compliance"],
    "parameters": [
        {"name": "org_id", "in": "path", "type": "string", "required": True},
        {"name": "compliance_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {"200": {"description": "Organization compliance suspended"}}
})
@jwt_required()
@require_roles("superadmin")
def suspend_org_compliance(org_id, compliance_id):
    """Suspend an organization's compliance."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} suspending compliance for org {org_id}")
    
    try:
        data = request.get_json()
        reason = data.get('reason', 'Administrative suspension')
        
        org_compliance = compliance_registry_service.suspend_org_compliance(compliance_id, reason)
        
        return success_response(data={
            "id": str(org_compliance.id),
            "org_id": org_compliance.org_id,
            "compliance_id": str(org_compliance.compliance_id.id),
            "compliance_code": org_compliance.compliance_id.code,
            "status": org_compliance.status
        })
    except Exception as e:
        error_logger.error(f"Failed to suspend organization compliance: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@compliance_bp.route("/organizations/<org_id>/compliance/summary", methods=["GET"])
@swag_from({
    "tags": ["Compliance"],
    "parameters": [{"name": "org_id", "in": "path", "type": "string", "required": True}],
    "responses": {"200": {"description": "Compliance summary"}}
})
@jwt_required()
@require_roles("admin", "superadmin")
def get_compliance_summary(org_id):
    """Get compliance summary for an organization."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} requesting compliance summary for org {org_id}")
    
    try:
        summary = compliance_registry_service.get_compliance_summary(org_id)
        return success_response(data=summary)
    except Exception as e:
        error_logger.error(f"Failed to get compliance summary: {e}", exc_info=True)
        return error_response(message="Failed to get compliance summary", status_code=500)


@compliance_bp.route("/organizations/<org_id>/evidence", methods=["GET"])
@swag_from({
    "tags": ["Compliance"],
    "parameters": [{"name": "org_id", "in": "path", "type": "string", "required": True}],
    "responses": {"200": {"description": "Compliance evidence list"}}
})
@jwt_required()
@require_roles("admin", "superadmin")
def get_compliance_evidence(org_id):
    """Get compliance evidence for an organization."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} requesting compliance evidence for org {org_id}")
    
    try:
        compliance_id = request.args.get('compliance_id')
        evidence_list = compliance_registry_service.get_compliance_evidence(org_id, compliance_id)
        
        evidence_data = []
        for evidence in evidence_list:
            evidence_data.append({
                "id": str(evidence.id),
                "org_id": evidence.org_id,
                "compliance_id": str(evidence.compliance_id.id),
                "compliance_code": evidence.compliance_id.code,
                "evidence_type": evidence.evidence_type,
                "title": evidence.title,
                "description": evidence.description,
                "file_url": evidence.file_url,
                "file_name": evidence.file_name,
                "file_size": evidence.file_size,
                "is_verified": evidence.is_verified,
                "verified_by": str(evidence.verified_by) if evidence.verified_by else None,
                "verified_at": evidence.verified_at.isoformat() if evidence.verified_at else None,
                "created_at": evidence.created_at.isoformat()
            })
        
        return success_response(data=evidence_data)
    except Exception as e:
        error_logger.error(f"Failed to get compliance evidence: {e}", exc_info=True)
        return error_response(message="Failed to get compliance evidence", status_code=500)


@compliance_bp.route("/organizations/<org_id>/audits", methods=["GET"])
@swag_from({
    "tags": ["Compliance"],
    "parameters": [{"name": "org_id", "in": "path", "type": "string", "required": True}],
    "responses": {"200": {"description": "Compliance audits list"}}
})
@jwt_required()
@require_roles("admin", "superadmin")
def get_compliance_audits(org_id):
    """Get compliance audits for an organization."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} requesting compliance audits for org {org_id}")
    
    try:
        status = request.args.get('status')
        audits = compliance_registry_service.get_compliance_audits(org_id, status)
        
        audits_data = []
        for audit in audits:
            audits_data.append({
                "id": str(audit.id),
                "org_id": audit.org_id,
                "compliance_id": str(audit.compliance_id.id),
                "compliance_code": audit.compliance_id.code,
                "audit_type": audit.audit_type,
                "title": audit.title,
                "description": audit.description,
                "status": audit.status,
                "scheduled_date": audit.scheduled_date.isoformat() if audit.scheduled_date else None,
                "started_date": audit.started_date.isoformat() if audit.started_date else None,
                "completed_date": audit.completed_date.isoformat() if audit.completed_date else None,
                "auditor_name": audit.auditor_name,
                "created_at": audit.created_at.isoformat()
            })
        
        return success_response(data=audits_data)
    except Exception as e:
        error_logger.error(f"Failed to get compliance audits: {e}", exc_info=True)
        return error_response(message="Failed to get compliance audits", status_code=500)


@compliance_bp.route("/organizations/<org_id>/data-processing-records", methods=["GET"])
@swag_from({
    "tags": ["Compliance"],
    "parameters": [{"name": "org_id", "in": "path", "type": "string", "required": True}],
    "responses": {"200": {"description": "Data processing records"}}
})
@jwt_required()
@require_roles("admin", "superadmin")
def get_data_processing_records(org_id):
    """Get GDPR data processing records for an organization."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} requesting data processing records for org {org_id}")
    
    try:
        records = compliance_registry_service.get_data_processing_records(org_id)
        
        records_data = []
        for record in records:
            records_data.append({
                "id": str(record.id),
                "org_id": record.org_id,
                "data_category": record.data_category,
                "data_subject": record.data_subject,
                "purpose": record.purpose,
                "legal_basis": record.legal_basis,
                "data_source": record.data_source,
                "data_recipients": record.data_recipients,
                "international_transfer": record.international_transfer,
                "transfer_countries": record.transfer_countries,
                "retention_period": record.retention_period,
                "retention_basis": record.retention_basis,
                "security_measures": record.security_measures,
                "created_at": record.created_at.isoformat()
            })
        
        return success_response(data=records_data)
    except Exception as e:
        error_logger.error(f"Failed to get data processing records: {e}", exc_info=True)
        return error_response(message="Failed to get data processing records", status_code=500)


@compliance_bp.route("/seed-default-standards", methods=["POST"])
@swag_from({
    "tags": ["Compliance"],
    "responses": {"200": {"description": "Default compliance standards seeded"}}
})
@jwt_required()
@require_roles("superadmin")
def seed_default_standards():
    """Seed default compliance standards (GDPR, HIPAA, ISO 27001)."""
    admin_id = get_jwt_identity()
    app_logger.info(f"Admin {admin_id} seeding default compliance standards")
    
    try:
        compliance_registry_service.seed_default_compliance_standards()
        return success_response(message="Default compliance standards seeded successfully")
    except Exception as e:
        error_logger.error(f"Failed to seed default compliance standards: {e}", exc_info=True)
        return error_response(message="Failed to seed default compliance standards", status_code=500)