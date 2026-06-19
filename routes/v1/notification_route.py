"""
routes/v1/notification_route.py
Notification management routes.
"""

from flask import Blueprint, request, jsonify
from flasgger import swag_from
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.security import require_roles
from utils.response_helper import success_response, error_response
from services.notification_engine_service import notification_engine_service
from logger.unified_logger import app_logger, error_logger, audit_logger

notification_bp = Blueprint("notification_bp", __name__)


@notification_bp.route("/templates", methods=["GET"])
@swag_from({
    "tags": ["Notifications"],
    "parameters": [
        {"name": "event_type", "in": "query", "type": "string", "required": False}
    ],
    "responses": {"200": {"description": "List of notification templates"}}
})
@jwt_required()
@require_roles("admin", "editor")
def list_notification_templates():
    """Get notification templates for the current organization."""
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} requesting notification templates")
    
    try:
        # Get user's organization
        from services.auth_service import auth_service
        user_orgs = auth_service.get_user_organizations(user_id)
        if not user_orgs:
            return error_response(message="User not associated with any organization", status_code=400)
        
        org_id = str(user_orgs[0].id)
        event_type = request.args.get('event_type')
        
        templates = notification_engine_service.get_notification_templates(org_id, event_type)
        
        templates_data = []
        for template in templates:
            templates_data.append({
                "id": str(template.id),
                "organization_id": template.organization_id,
                "name": template.name,
                "description": template.description,
                "event_type": template.event_type,
                "channels": template.channels,
                "variables": template.variables,
                "is_system": template.is_system,
                "is_active": template.is_active,
                "created_at": template.created_at.isoformat() if template.created_at else None,
                "updated_at": template.updated_at.isoformat() if template.updated_at else None
            })
        
        return success_response(data=templates_data)
    except Exception as e:
        error_logger.error(f"Failed to list notification templates: {e}", exc_info=True)
        return error_response(message="Failed to list notification templates", status_code=500)


@notification_bp.route("/templates", methods=["POST"])
@swag_from({
    "tags": ["Notifications"],
    "responses": {"201": {"description": "Notification template created"}}
})
@jwt_required()
@require_roles("admin")
def create_notification_template():
    """Create a new notification template."""
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} creating notification template")
    
    try:
        data = request.get_json()
        if not data:
            return error_response(message="Request data is required", status_code=400)
        
        # Get user's organization
        from services.auth_service import auth_service
        user_orgs = auth_service.get_user_organizations(user_id)
        if not user_orgs:
            return error_response(message="User not associated with any organization", status_code=400)
        
        data['organization_id'] = str(user_orgs[0].id)
        data['created_by'] = user_id
        
        template = notification_engine_service.create_notification_template(**data)
        
        return success_response(
            data={
                "id": str(template.id),
                "organization_id": template.organization_id,
                "name": template.name,
                "description": template.description,
                "event_type": template.event_type,
                "is_system": template.is_system,
                "is_active": template.is_active,
                "created_at": template.created_at.isoformat()
            },
            message="Notification template created successfully",
            status_code=201
        )
    except Exception as e:
        error_logger.error(f"Failed to create notification template: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@notification_bp.route("/rules", methods=["GET"])
@swag_from({
    "tags": ["Notifications"],
    "parameters": [
        {"name": "event_type", "in": "query", "type": "string", "required": False},
        {"name": "form_id", "in": "query", "type": "string", "required": False}
    ],
    "responses": {"200": {"description": "List of notification rules"}}
})
@jwt_required()
@require_roles("admin", "editor")
def list_notification_rules():
    """Get notification rules for the current organization."""
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} requesting notification rules")
    
    try:
        # Get user's organization
        from services.auth_service import auth_service
        user_orgs = auth_service.get_user_organizations(user_id)
        if not user_orgs:
            return error_response(message="User not associated with any organization", status_code=400)
        
        org_id = str(user_orgs[0].id)
        event_type = request.args.get('event_type')
        form_id = request.args.get('form_id')
        
        rules = notification_engine_service.get_notification_rules(org_id, event_type, form_id)
        
        rules_data = []
        for rule in rules:
            rules_data.append({
                "id": str(rule.id),
                "organization_id": rule.organization_id,
                "name": rule.name,
                "description": rule.description,
                "event_type": rule.event_type,
                "trigger_conditions": rule.trigger_conditions,
                "channels": rule.channels,
                "recipient_type": rule.recipient_type,
                "template_id": str(rule.template_id.id) if rule.template_id else None,
                "template_name": rule.template_id.name if rule.template_id else None,
                "form_id": str(rule.form_id) if rule.form_id else None,
                "is_active": rule.is_active,
                "created_at": rule.created_at.isoformat() if rule.created_at else None
            })
        
        return success_response(data=rules_data)
    except Exception as e:
        error_logger.error(f"Failed to list notification rules: {e}", exc_info=True)
        return error_response(message="Failed to list notification rules", status_code=500)


@notification_bp.route("/rules", methods=["POST"])
@swag_from({
    "tags": ["Notifications"],
    "responses": {"201": {"description": "Notification rule created"}}
})
@jwt_required()
@require_roles("admin")
def create_notification_rule():
    """Create a new notification rule."""
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} creating notification rule")
    
    try:
        data = request.get_json()
        if not data:
            return error_response(message="Request data is required", status_code=400)
        
        # Get user's organization
        from services.auth_service import auth_service
        user_orgs = auth_service.get_user_organizations(user_id)
        if not user_orgs:
            return error_response(message="User not associated with any organization", status_code=400)
        
        data['organization_id'] = str(user_orgs[0].id)
        data['created_by'] = user_id
        
        rule = notification_engine_service.create_notification_rule(**data)
        
        return success_response(
            data={
                "id": str(rule.id),
                "organization_id": rule.organization_id,
                "name": rule.name,
                "description": rule.description,
                "event_type": rule.event_type,
                "channels": rule.channels,
                "recipient_type": rule.recipient_type,
                "template_id": str(rule.template_id.id) if rule.template_id else None,
                "is_active": rule.is_active,
                "created_at": rule.created_at.isoformat()
            },
            message="Notification rule created successfully",
            status_code=201
        )
    except Exception as e:
        error_logger.error(f"Failed to create notification rule: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@notification_bp.route("/my-notifications", methods=["GET"])
@swag_from({
    "tags": ["Notifications"],
    "parameters": [
        {"name": "status", "in": "query", "type": "string", "required": False},
        {"name": "limit", "in": "query", "type": "integer", "required": False}
    ],
    "responses": {"200": {"description": "User notifications"}}
})
@jwt_required()
def get_my_notifications():
    """Get notifications for the current user."""
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} requesting their notifications")
    
    try:
        status = request.args.get('status')
        limit = int(request.args.get('limit', 50))
        
        notifications = notification_engine_service.get_user_notifications(user_id, status, limit)
        
        notifications_data = []
        for notification in notifications:
            notifications_data.append({
                "id": str(notification.id),
                "title": notification.title,
                "message": notification.message,
                "channel": notification.channel,
                "status": notification.status,
                "created_at": notification.created_at.isoformat(),
                "sent_at": notification.sent_at.isoformat() if notification.sent_at else None,
                "read_at": notification.read_at.isoformat() if notification.read_at else None,
                "data": notification.data
            })
        
        return success_response(data=notifications_data)
    except Exception as e:
        error_logger.error(f"Failed to get user notifications: {e}", exc_info=True)
        return error_response(message="Failed to get notifications", status_code=500)


@notification_bp.route("/notifications/<notification_id>/read", methods=["POST"])
@swag_from({
    "tags": ["Notifications"],
    "parameters": [
        {"name": "notification_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {"200": {"description": "Notification marked as read"}}
})
@jwt_required()
def mark_notification_read():
    """Mark a notification as read."""
    user_id = get_jwt_identity()
    notification_id = request.view_args['notification_id']
    app_logger.info(f"User {user_id} marking notification {notification_id} as read")
    
    try:
        success = notification_engine_service.mark_notification_read(notification_id, user_id)
        if success:
            return success_response(message="Notification marked as read")
        else:
            return error_response(message="Notification not found or access denied", status_code=404)
    except Exception as e:
        error_logger.error(f"Failed to mark notification as read: {e}", exc_info=True)
        return error_response(message="Failed to mark notification as read", status_code=500)


@notification_bp.route("/preferences", methods=["GET"])
@swag_from({
    "tags": ["Notifications"],
    "responses": {"200": {"description": "User notification preferences"}}
})
@jwt_required()
def get_notification_preferences():
    """Get user notification preferences."""
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} requesting notification preferences")
    
    try:
        preferences = notification_engine_service.get_notification_preferences(user_id)
        
        return success_response(data={
            "user_id": str(preferences.user_id),
            "email_notifications": preferences.email_notifications,
            "sms_notifications": preferences.sms_notifications,
            "in_app_notifications": preferences.in_app_notifications,
            "push_notifications": preferences.push_notifications,
            "event_preferences": preferences.event_preferences,
            "quiet_hours": preferences.quiet_hours
        })
    except Exception as e:
        error_logger.error(f"Failed to get notification preferences: {e}", exc_info=True)
        return error_response(message="Failed to get notification preferences", status_code=500)


@notification_bp.route("/preferences", methods=["PUT"])
@swag_from({
    "tags": ["Notifications"],
    "responses": {"200": {"description": "Notification preferences updated"}}
})
@jwt_required()
def update_notification_preferences():
    """Update user notification preferences."""
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} updating notification preferences")
    
    try:
        data = request.get_json()
        if not data:
            return error_response(message="Request data is required", status_code=400)
        
        preferences = notification_engine_service.update_notification_preferences(user_id, **data)
        
        return success_response(data={
            "user_id": str(preferences.user_id),
            "email_notifications": preferences.email_notifications,
            "sms_notifications": preferences.sms_notifications,
            "in_app_notifications": preferences.in_app_notifications,
            "push_notifications": preferences.push_notifications,
            "event_preferences": preferences.event_preferences,
            "quiet_hours": preferences.quiet_hours
        }, message="Notification preferences updated successfully")
    except Exception as e:
        error_logger.error(f"Failed to update notification preferences: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@notification_bp.route("/events", methods=["POST"])
@swag_from({
    "tags": ["Notifications"],
    "responses": {"202": {"description": "Notification event processed"}}
})
@jwt_required()
@require_roles("admin", "editor")
def trigger_notification_event():
    """Trigger a notification event manually."""
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} triggering notification event")
    
    try:
        data = request.get_json()
        if not data:
            return error_response(message="Request data is required", status_code=400)
        
        # Get user's organization
        from services.auth_service import auth_service
        user_orgs = auth_service.get_user_organizations(user_id)
        if not user_orgs:
            return error_response(message="User not associated with any organization", status_code=400)
        
        org_id = str(user_orgs[0].id)
        event_type = data.get('event_type')
        context = data.get('context', {})
        
        if not event_type:
            return error_response(message="event_type is required", status_code=400)
        
        # Add user info to context
        context['triggered_by'] = user_id
        context['triggered_at'] = datetime.utcnow().isoformat()
        
        # Process the event
        from tasks.notification_tasks import process_notification_event
        task = process_notification_event.delay(org_id=org_id, event_type=event_type, context=context)
        
        return success_response(
            data={
                "task_id": task.id,
                "event_type": event_type,
                "organization_id": org_id
            },
            message="Notification event triggered successfully",
            status_code=202
        )
    except Exception as e:
        error_logger.error(f"Failed to trigger notification event: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@notification_bp.route("/metrics", methods=["GET"])
@swag_from({
    "tags": ["Notifications"],
    "responses": {"200": {"description": "Notification metrics"}}
})
@jwt_required()
@require_roles("admin")
def get_notification_metrics():
    """Get notification delivery metrics."""
    user_id = get_jwt_identity()
    app_logger.info(f"User {user_id} requesting notification metrics")
    
    try:
        # Get user's organization
        from services.auth_service import auth_service
        user_orgs = auth_service.get_user_organizations(user_id)
        if not user_orgs:
            return error_response(message="User not associated with any organization", status_code=400)
        
        org_id = str(user_orgs[0].id)
        
        # Get metrics from Redis
        from services.redis_service import redis_service
        metrics = {}
        if redis_service.cache:
            metrics = redis_service.cache.get("notification_metrics:current_hour") or {}
        
        # Get organization-specific metrics
        from models.notification import NotificationLog
        org_metrics = {}
        
        # Count notifications by status and channel for the last 24 hours
        from datetime import datetime, timedelta
        day_ago = datetime.utcnow() - timedelta(days=1)
        
        pipeline = [
            {"$match": {
                "organization_id": org_id,
                "created_at": {"$gte": day_ago}
            }},
            {"$group": {
                "_id": {"status": "$status", "channel": "$channel"},
                "count": {"$sum": 1}
            }}
        ]
        
        for doc in NotificationLog.objects.aggregate(pipeline):
            key = f"{doc['_id']['channel']}_{doc['_id']['status']}"
            org_metrics[key] = doc['count']
        
        return success_response(data={
            "global_metrics": metrics,
            "organization_metrics": org_metrics
        })
    except Exception as e:
        error_logger.error(f"Failed to get notification metrics: {e}", exc_info=True)
        return error_response(message="Failed to get notification metrics", status_code=500)