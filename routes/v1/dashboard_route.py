from flask import Blueprint, request, current_app
from flasgger import swag_from
from flask_jwt_extended import get_jwt_identity, jwt_required, get_jwt
from models import Form, FormResponse
from services.dashboard_service import DashboardService, DashboardCreateSchema, DashboardUpdateSchema, WidgetSchema
from utils.response_helper import success_response, error_response
from utils.security_helpers import require_permission
from utils.exceptions import NotFoundError, ForbiddenError, ValidationError
import uuid
from logger.unified_logger import app_logger, error_logger, audit_logger

dashboard_bp = Blueprint("dashboard", __name__)
dashboard_service = DashboardService()


# --- CRUD Operations ---


@dashboard_bp.route("/", methods=["POST"])
@swag_from({
    "tags": [
        "Dashboard"
    ],
    "responses": {
        "200": {
            "description": "Create a new Dashboard configuration."
        }
    },
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "schema": {
                "$ref": "#/definitions/DashboardCreateSchema"
            }
        }
    ]
})
@jwt_required()
@require_permission("dashboard", "create")
def create_dashboard():
    """Create a new Dashboard configuration."""
    current_user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(f"User {current_user_id} is creating a new dashboard for org {org_id}")
    
    data = request.get_json() or {}
    
    try:
        data["created_by"] = current_user_id
        data["organization_id"] = org_id
        schema = DashboardCreateSchema(**data)
        result = dashboard_service.create(schema)
        
        audit_logger.info(
            f"Dashboard created: ID={result.id}, Title='{result.title}', CreatedBy={current_user_id}, OrgID={org_id}"
        )
        app_logger.info(f"Dashboard {result.id} created successfully")
        return success_response(data=result.model_dump(), message="Dashboard created", status_code=201)
    except Exception as e:
        error_logger.error(f"Create Dashboard error for user {current_user_id}: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)


def resolve_widget_data(widget: WidgetSchema, org_id: str):
    """
    Resolves widget data using high-performance MongoDB Aggregation pipelines.
    """
    app_logger.debug(f"Resolving data for widget: {widget.title} (type: {widget.type}) for org {org_id}")
    
    if not widget.form_id:
        return {**widget.model_dump(), "data": None}

    # Base Match: Form + Non-deleted + Organization Isolation
    match_query = {
        "form": widget.form_id,
        "is_deleted": False,
        "organization_id": org_id
    }
    
    # Add optional filters from widget config
    if widget.filters:
        for key, val in widget.filters.items():
            match_query[f"data.{key}"] = val

    pipeline = [{"$match": match_query}]

    try:
        if widget.type in ["chart_bar", "chart_pie", "chart_line"]:
            group_by = widget.group_by_field
            agg_field = widget.aggregate_field
            calc_type = widget.calculation_type

            if not group_by:
                return {**widget.model_dump(), "data": {"error": "Missing group_by_field"}}

            # Flatten/Unwind may be needed if data is nested, 
            # but assume standard data.{field} access for now.
            group_id = f"$data.{group_by}"
            
            if agg_field:
                agg_val = f"$data.{agg_field}"
                if calc_type == "sum":
                    op = {"$sum": agg_val}
                elif calc_type == "average":
                    op = {"$avg": agg_val}
                elif calc_type == "max":
                    op = {"$max": agg_val}
                elif calc_type == "min":
                    op = {"$min": agg_val}
                else:
                    op = {"$count": {}}
            else:
                op = {"$count": {}}

            pipeline.append({"$group": {"_id": group_id, "value": op}})
            pipeline.append({"$sort": {"_id": 1}})

            results = list(FormResponse.objects.aggregate(*pipeline))
            labels = [str(r["_id"]) for r in results]
            values = [r["value"] for r in results]
            res_data = {"labels": labels, "values": values}

        elif widget.type in ["counter", "kpi"]:
            res_data = FormResponse.objects(**match_query).count()

        elif widget.type in ["table", "list_view"]:
            # Efficient Projection and Limit
            limit = widget.config.get("limit", 10)
            results = (
                FormResponse.objects(**match_query)
                .order_by("-submitted_at")
                .limit(limit)
                .only("id", "data", "submitted_at")
            )
            res_data = []
            for r in results:
                res_data.append({
                    "id": str(r.id),
                    "submitted_at": r.submitted_at.isoformat(),
                    "data": r.data
                })
        else:
            res_data = None

    except Exception as w_err:
        error_logger.error(f"Aggregation failed for widget {widget.title}: {w_err}", exc_info=True)
        res_data = {"error": "Aggregation failure"}

    return {**widget.model_dump(), "data": res_data}


@dashboard_bp.route("/<slug>", methods=["GET"])
@swag_from({
    "tags": [
        "Dashboard"
    ],
    "responses": {
        "200": {
            "description": "Get dashboard details AND fetch data for widgets."
        }
    },
    "parameters": [
        {
            "name": "slug",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
@require_permission("dashboard", "view")
def get_dashboard(slug):
    """Get dashboard details AND fetch data for widgets."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(f"User {user_id} fetching dashboard {slug} for org {org_id}")
        
    try:
        dashboard = dashboard_service.get_by_slug(slug, organization_id=org_id)
        
        # Resolve Widget Data
        widgets_data = [resolve_widget_data(w, org_id) for w in dashboard.widgets]
        
        result = dashboard.model_dump()
        result["widgets"] = widgets_data
        
        app_logger.info(f"Dashboard {slug} data retrieved successfully for user {user_id}")
        return success_response(data=result)
    except NotFoundError:
        app_logger.warning(f"Dashboard {slug} not found for org {org_id} (requested by user {user_id})")
        return error_response(message="Dashboard not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Get Dashboard error for user {user_id}, slug {slug}: {str(e)}", exc_info=True)
        return error_response(message="Failed to load dashboard data", status_code=500)


@dashboard_bp.route("/<dashboard_id>", methods=["PUT"])
@swag_from({
    "tags": [
        "Dashboard"
    ],
    "responses": {
        "200": {
            "description": "Update Dashboard configuration."
        }
    },
    "parameters": [
        {
            "name": "dashboard_id",
            "in": "path",
            "type": "string",
            "required": True
        },
        {
            "name": "body",
            "in": "body",
            "schema": {
                "$ref": "#/definitions/DashboardUpdateSchema"
            }
        }
    ]
})
@jwt_required()
@require_permission("dashboard", "edit")
def update_dashboard(dashboard_id):
    """Update Dashboard configuration."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(f"User {user_id} updating dashboard {dashboard_id} for org {org_id}")

    if not org_id:
        error_logger.warning(f"Update dashboard failed for user {user_id}: Organization context missing")
        return error_response(message="Organization context missing", status_code=400)

    try:
        data = request.get_json() or {}
        schema = DashboardUpdateSchema(**data)
        result = dashboard_service.update(dashboard_id, schema, organization_id=org_id)
        
        audit_logger.info(
            f"Dashboard updated: ID={dashboard_id}, Title='{result.title}', UpdatedBy={user_id}, OrgID={org_id}"
        )
        app_logger.info(f"Dashboard {dashboard_id} updated successfully")
        return success_response(data=result.model_dump(), message="Dashboard updated")
    except Exception as e:
        error_logger.error(f"Update Dashboard error for user {user_id}, ID {dashboard_id}: {str(e)}", exc_info=True)
        return error_response(message=str(e), status_code=400)
