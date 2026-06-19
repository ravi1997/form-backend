from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from flasgger import swag_from
from datetime import datetime, timezone
from typing import Optional, List

from models import Form, Project, Dashboard
from models.utility import Tombstone
from services.tombstone_service import TombstoneService
from routes.v1.form.helper import get_current_user
from utils.response_helper import success_response, error_response
from logger.unified_logger import app_logger, audit_logger

sync_bp = Blueprint("sync", __name__)


@sync_bp.route("/sync", methods=["GET"])
@jwt_required()
def get_delta_sync():
    """
    Delta synchronization endpoint for offline clients.
    Returns forms, projects, dashboards updated since last_sync timestamp,
    plus tombstones for deleted entities.
    
    Query Parameters:
    - last_synced_at: ISO8601 timestamp (optional)
    - entity_types: Comma-separated list of entity types (optional)
    """
    try:
        current_user = get_current_user()
        last_synced_at_str = request.args.get("last_synced_at")
        entity_types_str = request.args.get("entity_types")
        
        # Parse timestamp
        last_synced_at: Optional[datetime] = None
        if last_synced_at_str:
            try:
                # Handle various ISO8601 formats
                if last_synced_at_str.endswith('Z'):
                    last_synced_at_str = last_synced_at_str[:-1] + '+00:00'
                last_synced_at = datetime.fromisoformat(last_synced_at_str)
            except ValueError as e:
                return error_response(
                    message=f"Invalid last_synced_at format: {e}",
                    status_code=400
                )
        
        # Parse entity types
        entity_types: Optional[List[str]] = None
        if entity_types_str:
            entity_types = [t.strip() for t in entity_types_str.split(',') if t.strip()]
        
        # Initialize response
        response_data = {
            "updated": [],
            "tombstones": []
        }
        
        # Get updated forms
        if not entity_types or "forms" in entity_types:
            forms_query = Form.objects(
                organization_id=current_user.organization_id,
                is_deleted=False
            )
            
            if last_synced_at:
                forms_query = forms_query(updated_at__gt=last_synced_at)
            
            forms = forms_query.only(
                "id", "organization_id", "project_id", "title", "description", 
                "form_fields", "updated_at"
            ).limit(100)  # Prevent large responses
            
            for form in forms:
                response_data["updated"].append({
                    "id": str(form.id),
                    "orgId": str(form.organization_id),
                    "projectId": str(form.project_id) if form.project_id else "",
                    "name": form.title,
                    "description": form.description or "",
                    "schemaJson": form.form_fields or {},
                    "lastSyncedAt": form.updated_at.isoformat(),
                    "entityType": "forms"
                })
        
        # Get updated projects
        if not entity_types or "projects" in entity_types:
            projects_query = Project.objects(
                organization_id=current_user.organization_id,
                is_deleted=False
            )
            
            if last_synced_at:
                projects_query = projects_query(updated_at__gt=last_synced_at)
            
            projects = projects_query.only(
                "id", "organization_id", "name", "description", "updated_at"
            ).limit(100)
            
            for project in projects:
                response_data["updated"].append({
                    "id": str(project.id),
                    "orgId": str(project.organization_id),
                    "projectId": "",  # Projects don't have parent projects
                    "name": project.name,
                    "description": project.description or "",
                    "schemaJson": {},  # Projects don't have schema
                    "lastSyncedAt": project.updated_at.isoformat(),
                    "entityType": "projects"
                })
        
        # Get updated dashboards
        if not entity_types or "dashboards" in entity_types:
            dashboards_query = Dashboard.objects(
                organization_id=current_user.organization_id,
                is_deleted=False
            )
            
            if last_synced_at:
                dashboards_query = dashboards_query(updated_at__gt=last_synced_at)
            
            dashboards = dashboards_query.only(
                "id", "organization_id", "project_id", "name", "description",
                "canvas", "settings", "linked_analysis_ids", "updated_at"
            ).limit(100)
            
            for dashboard in dashboards:
                response_data["updated"].append({
                    "id": str(dashboard.id),
                    "orgId": str(dashboard.organization_id),
                    "projectId": str(dashboard.project_id) if dashboard.project_id else "",
                    "name": dashboard.name,
                    "description": dashboard.description or "",
                    "schemaJson": {
                        "canvas": dashboard.canvas or {},
                        "settings": dashboard.settings or {},
                        "linkedAnalysisIds": dashboard.linked_analysis_ids or []
                    },
                    "lastSyncedAt": dashboard.updated_at.isoformat(),
                    "entityType": "dashboards"
                })
        
        # Get tombstones
        tombstone_service = TombstoneService()
        tombstones = tombstone_service.list_since(
            organization_id=str(current_user.organization_id),
            since=last_synced_at,
            entity_types=entity_types
        )
        
        response_data["tombstones"] = tombstones
        
        # Add server timestamp for client to use as next watermark
        response_data["server_timestamp"] = datetime.now(timezone.utc).isoformat()
        
        audit_logger.info(
            f"Delta sync completed for user {current_user.id}, "
            f"org {current_user.organization_id}, "
            f"returned {len(response_data['updated'])} updates, "
            f"{len(response_data['tombstones'])} tombstones"
        )
        
        return success_response(data=response_data)
        
    except Exception as e:
        app_logger.error(f"Error in delta sync: {e}", exc_info=True)
        return error_response(message=str(e), status_code=500)


@sync_bp.route("/sync/status", methods=["GET"])
@jwt_required()
def get_sync_status():
    """
    Get sync status information for the current user.
    Returns counts of pending items and last sync timestamp.
    """
    try:
        current_user = get_current_user()
        
        # This would typically query the database for actual pending items
        # For now, we'll return a basic status
        status_data = {
            "user_id": str(current_user.id),
            "organization_id": str(current_user.organization_id),
            "last_sync": None,  # Would come from user's last sync record
            "pending_responses": 0,  # Would count pending responses
            "pending_uploads": 0,  # Would count pending file uploads
            "has_conflicts": False,  # Would check for unresolved conflicts
            "server_time": datetime.now(timezone.utc).isoformat()
        }
        
        return success_response(data=status_data)
        
    except Exception as e:
        app_logger.error(f"Error getting sync status: {e}", exc_info=True)
        return error_response(message=str(e), status_code=500)