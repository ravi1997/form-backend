"""
routes/v1/admin/system_route.py
Admin system management routes.
"""

from flask import Blueprint, request, jsonify
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.security import require_roles
from utils.response_helper import success_response, error_response
from services.storage_quota_service import storage_quota_service
from services.update_service import update_service
from services.notification_service import notification_service
from services.compliance_registry_service import compliance_registry_service
from services.oauth_service import oauth_service
from logger.unified_logger import app_logger, error_logger, audit_logger

system_bp = Blueprint("system_bp", __name__)


@system_bp.route("/status", methods=["GET"])
@swag_from({
    "tags": ["Admin System"],
    "responses": {"200": {"description": "System status"}}
})
@jwt_required()
@require_roles("super_admin")
def system_status():
    """Get overall system status."""
    try:
        # Get system information
        import platform
        import psutil
        
        status = {
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor()
            },
            "resources": {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory": {
                    "total": psutil.virtual_memory().total,
                    "available": psutil.virtual_memory().available,
                    "percent": psutil.virtual_memory().percent
                },
                "disk": {
                    "total": psutil.disk_usage('/').total,
                    "used": psutil.disk_usage('/').used,
                    "free": psutil.disk_usage('/').free,
                    "percent": psutil.disk_usage('/').percent
                }
            },
            "services": {
                "database": "connected",  # Would check actual DB connection
                "redis": "connected",    # Would check actual Redis connection
                "celery": "running"      # Would check actual Celery status
            },
            "version": update_service.get_current_version(),
            "timestamp": audit_logger.get_current_timestamp()
        }
        
        return success_response(data=status)
        
    except Exception as e:
        error_logger.error(f"Error getting system status: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@system_bp.route("/storage", methods=["GET"])
@swag_from({
    "tags": ["Admin System"],
    "parameters": [
        {"name": "org_id", "in": "query", "type": "string", "required": False}
    ],
    "responses": {"200": {"description": "Storage quota information"}}
})
@jwt_required()
@require_roles("admin", "super_admin")
def storage_management():
    """Get storage quota information."""
    try:
        org_id = request.args.get('org_id')
        
        if org_id:
            # Get specific organization's storage info
            storage_info = storage_quota_service.get_quota_statistics(org_id)
        else:
            # Get all organizations' storage info
            storage_info = storage_quota_service.get_quota_statistics()
        
        return success_response(data=storage_info)
        
    except Exception as e:
        error_logger.error(f"Error getting storage info: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@system_bp.route("/storage", methods=["POST"])
@swag_from({
    "tags": ["Admin System"],
    "parameters": [
        {"name": "body", "in": "body", "required": True,
         "schema": {"type": "object",
                   "properties": {
                       "org_id": {"type": "string"},
                       "quota_bytes": {"type": "integer"},
                       "warning_threshold": {"type": "number"}
                   }}}
    ],
    "responses": {"200": {"description": "Storage quota updated"}}
})
@jwt_required()
@require_roles("admin", "super_admin")
def update_storage_quota():
    """Update organization storage quota."""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request data is required", status_code=400)
        
        org_id = data.get('org_id')
        quota_bytes = data.get('quota_bytes')
        warning_threshold = data.get('warning_threshold')
        
        if not org_id or not quota_bytes:
            return error_response("org_id and quota_bytes are required", status_code=400)
        
        # Update quota
        quota = storage_quota_service.update_quota(org_id, quota_bytes, user_id)
        
        # Update warning threshold if provided
        if warning_threshold:
            quota.warning_threshold = warning_threshold
            quota.save()
        
        audit_logger.info(f"Storage quota updated for org {org_id} to {quota_bytes} bytes by {user_id}")
        
        return success_response(
            data=quota.to_dict() if hasattr(quota, 'to_dict') else str(quota),
            message="Storage quota updated successfully"
        )
        
    except Exception as e:
        error_logger.error(f"Error updating storage quota: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@system_bp.route("/storage/calculate", methods=["POST"])
@swag_from({
    "tags": ["Admin System"],
    "parameters": [
        {"name": "body", "in": "body", "required": True,
         "schema": {"type": "object",
                   "properties": {
                       "org_id": {"type": "string"},
                       "force": {"type": "boolean"}
                   }}}
    ],
    "responses": {"200": {"description": "Storage usage calculated"}}
})
@jwt_required()
@require_roles("admin", "super_admin")
def calculate_storage_usage():
    """Calculate storage usage for organization."""
    try:
        data = request.get_json()
        org_id = data.get('org_id')
        force = data.get('force', False)
        
        if not org_id:
            return error_response("org_id is required", status_code=400)
        
        # Calculate usage
        usage = storage_quota_service.calculate_storage_usage(org_id, force)
        
        return success_response(
            data=usage,
            message="Storage usage calculated successfully"
        )
        
    except Exception as e:
        error_logger.error(f"Error calculating storage usage: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@system_bp.route("/updates", methods=["GET"])
@swag_from({
    "tags": ["Admin System"],
    "responses": {"200": {"description": "Update information"}}
})
@jwt_required()
@require_roles("super_admin")
def get_update_info():
    """Get platform update information."""
    try:
        # Get current version
        current_version = update_service.get_current_version()
        
        # Check for updates
        updates = update_service.check_for_updates()
        
        # Get update history
        history = update_service.get_update_history()
        
        return success_response(data={
            "current_version": current_version,
            "updates": updates,
            "history": history
        })
        
    except Exception as e:
        error_logger.error(f"Error getting update info: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@system_bp.route("/updates/prepare", methods=["POST"])
@swag_from({
    "tags": ["Admin System"],
    "parameters": [
        {"name": "body", "in": "body", "required": True,
         "schema": {"type": "object",
                   "properties": {
                       "version": {"type": "string"},
                       "download_url": {"type": "string"}
                   }}}
    ],
    "responses": {"200": {"description": "Update prepared"}}
})
@jwt_required()
@require_roles("super_admin")
def prepare_update():
    """Prepare platform update."""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request data is required", status_code=400)
        
        version = data.get('version')
        download_url = data.get('download_url')
        
        if not version or not download_url:
            return error_response("version and download_url are required", status_code=400)
        
        # Prepare update
        result = update_service.prepare_update(version, download_url)
        if result.get("error"):
            return error_response(result["error"], status_code=503)
        
        audit_logger.info(f"Update to version {version} prepared by {user_id}")
        
        return success_response(
            data=result,
            message="Update prepared successfully"
        )
        
    except Exception as e:
        error_logger.error(f"Error preparing update: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@system_bp.route("/updates/perform", methods=["POST"])
@swag_from({
    "tags": ["Admin System"],
    "parameters": [
        {"name": "body", "in": "body", "required": True,
         "schema": {"type": "object",
                   "properties": {
                       "version": {"type": "string"},
                       "strategy": {"type": "string", "enum": ["rolling", "blue_green", "maintenance"]}
                   }}}
    ],
    "responses": {"200": {"description": "Update performed"}}
})
@jwt_required()
@require_roles("super_admin")
def perform_update():
    """Perform platform update."""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request data is required", status_code=400)
        
        version = data.get('version')
        strategy = data.get('strategy', 'rolling')
        
        if not version:
            return error_response("version is required", status_code=400)
        
        # Perform update
        result = update_service.perform_update(version, strategy)
        if result.get("error"):
            return error_response(result["error"], status_code=503)
        
        audit_logger.info(f"Update to version {version} performed by {user_id} with strategy {strategy}")
        
        return success_response(
            data=result,
            message="Update performed successfully"
        )
        
    except Exception as e:
        error_logger.error(f"Error performing update: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@system_bp.route("/updates/rollback", methods=["POST"])
@swag_from({
    "tags": ["Admin System"],
    "parameters": [
        {"name": "body", "in": "body", "required": True,
         "schema": {"type": "object",
                   "properties": {
                       "target_version": {"type": "string"}
                   }}}
    ],
    "responses": {"200": {"description": "Update rolled back"}}
})
@jwt_required()
@require_roles("super_admin")
def rollback_update():
    """Rollback platform update."""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request data is required", status_code=400)
        
        target_version = data.get('target_version')
        
        if not target_version:
            return error_response("target_version is required", status_code=400)
        
        # Perform rollback
        result = update_service.rollback_update(target_version)
        if result.get("error"):
            return error_response(result["error"], status_code=503)
        
        audit_logger.info(f"Rollback to version {target_version} performed by {user_id}")
        
        return success_response(
            data=result,
            message="Rollback performed successfully"
        )
        
    except Exception as e:
        error_logger.error(f"Error rolling back update: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@system_bp.route("/maintenance", methods=["POST"])
@swag_from({
    "tags": ["Admin System"],
    "parameters": [
        {"name": "body", "in": "body", "required": True,
         "schema": {"type": "object",
                   "properties": {
                       "enabled": {"type": "boolean"},
                       "message": {"type": "string"}
                   }}}
    ],
    "responses": {"200": {"description": "Maintenance mode updated"}}
})
@jwt_required()
@require_roles("super_admin")
def toggle_maintenance_mode():
    """Toggle maintenance mode."""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request data is required", status_code=400)
        
        enabled = data.get('enabled')
        message = data.get('message', 'System maintenance in progress')
        
        if enabled is None:
            return error_response("enabled is required", status_code=400)
        
        # Update maintenance mode
        from models.oauth import SystemConfig
        maintenance_config = SystemConfig.objects(key="maintenance_mode").first()
        
        if not maintenance_config:
            maintenance_config = SystemConfig(
                key="maintenance_mode",
                value=enabled,
                updated_by=user_id
            )
        else:
            maintenance_config.value = enabled
            maintenance_config.updated_by = user_id
        
        maintenance_config.save()
        
        # Update maintenance message
        message_config = SystemConfig.objects(key="maintenance_message").first()
        if not message_config:
            message_config = SystemConfig(
                key="maintenance_message",
                value=message,
                updated_by=user_id
            )
        else:
            message_config.value = message
            message_config.updated_by = user_id
        
        message_config.save()
        
        audit_logger.info(f"Maintenance mode {'enabled' if enabled else 'disabled'} by {user_id}")
        
        return success_response(
            data={"maintenance_mode": enabled, "message": message},
            message=f"Maintenance mode {'enabled' if enabled else 'disabled'} successfully"
        )
        
    except Exception as e:
        error_logger.error(f"Error toggling maintenance mode: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@system_bp.route("/compliance", methods=["GET"])
@swag_from({
    "tags": ["Admin System"],
    "responses": {"200": {"description": "Compliance standards"}}
})
@jwt_required()
@require_roles("admin", "super_admin")
def get_compliance_standards():
    """Get all compliance standards."""
    try:
        standards = compliance_registry_service.get_all_standards()
        
        return success_response(data=standards)
        
    except Exception as e:
        error_logger.error(f"Error getting compliance standards: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@system_bp.route("/compliance", methods=["POST"])
@swag_from({
    "tags": ["Admin System"],
    "parameters": [
        {"name": "body", "in": "body", "required": True,
         "schema": {"type": "object",
                   "properties": {
                       "code": {"type": "string"},
                       "name": {"type": "string"},
                       "description": {"type": "string"},
                       "region": {"type": "string"},
                       "behavioral_constraints": {"type": "array"}
                   }}}
    ],
    "responses": {"201": {"description": "Compliance standard created"}}
})
@jwt_required()
@require_roles("super_admin")
def create_compliance_standard():
    """Create a new compliance standard."""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request data is required", status_code=400)
        
        # Create compliance standard
        standard = compliance_registry_service.create_standard(**data)
        
        audit_logger.info(f"Compliance standard {standard.code} created by {user_id}")
        
        return success_response(
            data=standard.to_dict() if hasattr(standard, 'to_dict') else str(standard),
            message="Compliance standard created successfully",
            status_code=201
        )
        
    except Exception as e:
        error_logger.error(f"Error creating compliance standard: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@system_bp.route("/notifications", methods=["GET"])
@swag_from({
    "tags": ["Admin System"],
    "responses": {"200": {"description": "Notification templates"}}
})
@jwt_required()
@require_roles("admin", "super_admin")
def get_notification_templates():
    """Get all notification templates."""
    try:
        templates = notification_service.get_all_templates()
        
        return success_response(data=templates)
        
    except Exception as e:
        error_logger.error(f"Error getting notification templates: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@system_bp.route("/notifications", methods=["POST"])
@swag_from({
    "tags": ["Admin System"],
    "parameters": [
        {"name": "body", "in": "body", "required": True,
         "schema": {"type": "object",
                   "properties": {
                       "name": {"type": "string"},
                       "event_type": {"type": "string"},
                       "channels": {"type": "object"},
                       "variables": {"type": "array"}
                   }}}
    ],
    "responses": {"201": {"description": "Notification template created"}}
})
@jwt_required()
@require_roles("admin", "super_admin")
def create_notification_template():
    """Create a new notification template."""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return error_response("Request data is required", status_code=400)
        
        # Create notification template
        template = notification_service.create_template(**data)
        
        audit_logger.info(f"Notification template {template.name} created by {user_id}")
        
        return success_response(
            data=template.to_dict() if hasattr(template, 'to_dict') else str(template),
            message="Notification template created successfully",
            status_code=201
        )
        
    except Exception as e:
        error_logger.error(f"Error creating notification template: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@system_bp.route("/api-keys", methods=["GET"])
@swag_from({
    "tags": ["Admin System"],
    "parameters": [
        {"name": "org_id", "in": "query", "type": "string", "required": False}
    ],
    "responses": {"200": {"description": "API keys"}}
})
@jwt_required()
@require_roles("admin", "super_admin")
def get_api_keys():
    """Get API keys (admin view)."""
    try:
        org_id = request.args.get('org_id')
        
        # Get API keys
        api_keys = oauth_service.get_all_api_keys(org_id)
        
        return success_response(data=api_keys)
        
    except Exception as e:
        error_logger.error(f"Error getting API keys: {e}", exc_info=True)
        return error_response(str(e), status_code=500)


@system_bp.route("/audit-logs", methods=["GET"])
@swag_from({
    "tags": ["Admin System"],
    "parameters": [
        {"name": "org_id", "in": "query", "type": "string", "required": False},
        {"name": "entity_type", "in": "query", "type": "string", "required": False},
        {"name": "action", "in": "query", "type": "string", "required": False},
        {"name": "start_date", "in": "query", "type": "string", "required": False},
        {"name": "end_date", "in": "query", "type": "string", "required": False},
        {"name": "page", "in": "query", "type": "integer", "required": False},
        {"name": "limit", "in": "query", "type": "integer", "required": False}
    ],
    "responses": {"200": {"description": "Audit logs"}}
})
@jwt_required()
@require_roles("admin", "super_admin")
def get_audit_logs():
    """Get audit logs."""
    try:
        # Parse query parameters
        org_id = request.args.get('org_id')
        entity_type = request.args.get('entity_type')
        action = request.args.get('action')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        
        # Build query
        from models.oauth import AuditLog
        query = AuditLog.objects()
        
        if org_id:
            query = query.filter(organization_id=org_id)
        
        if entity_type:
            query = query.filter(entity_type=entity_type)
        
        if action:
            query = query.filter(action=action)
        
        if start_date:
            from datetime import datetime
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            query = query.filter(timestamp__gte=start_dt)
        
        if end_date:
            from datetime import datetime
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            query = query.filter(timestamp__lte=end_dt)
        
        # Paginate
        offset = (page - 1) * limit
        logs = query.order_by('-timestamp').skip(offset).limit(limit)
        
        # Convert to dict
        logs_data = []
        for log in logs:
            logs_data.append({
                "id": str(log.id),
                "organization_id": log.organization_id,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "action": log.action,
                "actor_id": log.actor_id,
                "actor_role": log.actor_role,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "timestamp": log.timestamp.isoformat(),
                "metadata": log.metadata
            })
        
        return success_response(data={
            "logs": logs_data,
            "page": page,
            "limit": limit,
            "total": query.count()
        })
        
    except Exception as e:
        error_logger.error(f"Error getting audit logs: {e}", exc_info=True)
        return error_response(str(e), status_code=500)
