from flask import Blueprint, request, current_app
from flasgger import swag_from
from flask_jwt_extended import get_jwt_identity, jwt_required, get_jwt
from models import Form, FormResponse
from services.dashboard_service import (
    DashboardService,
    DashboardCreateSchema,
    DashboardUpdateSchema,
    WidgetSchema,
)
from utils.response_helper import success_response, error_response
from utils.security_helpers import require_permission
from utils.exceptions import NotFoundError, ForbiddenError, ValidationError
import uuid
from logger.unified_logger import app_logger, error_logger, audit_logger

dashboard_bp = Blueprint("dashboard", __name__)
dashboard_service = DashboardService()


def _docs_widget(widget):
    return {
        "id": str(getattr(widget, "id", "") or uuid.uuid4()),
        "type": getattr(widget, "type", ""),
        "position": {
            "x": getattr(widget, "position_x", 0),
            "y": getattr(widget, "position_y", 0),
        },
        "size": {
            "width": getattr(widget, "width", 2),
            "height": getattr(widget, "height", 2),
        },
        "z_index": getattr(widget, "z_index", 0),
        "is_locked": getattr(widget, "is_locked", False),
        "properties": {
            "title": getattr(widget, "title", ""),
            "group_by_field": getattr(widget, "group_by_field", None),
            "aggregate_field": getattr(widget, "aggregate_field", None),
            "calculation_type": getattr(widget, "calculation_type", "count"),
            "filters": getattr(widget, "filters", {}) or {},
            "size": getattr(widget, "size", "medium"),
            "color_scheme": getattr(widget, "color_scheme", None),
            "display_columns": getattr(widget, "display_columns", []) or [],
            "config": getattr(widget, "config", {}) or {},
        },
        "data_binding": {
            "analysis_id": getattr(widget, "analysis_id", None),
            "node_id": getattr(widget, "node_id", None),
            "refresh_mode": getattr(widget, "refresh_mode", "with_dashboard"),
        },
        "filters": [],
    }


def _docs_dashboard(dashboard):
    widgets = [_docs_widget(widget) for widget in (dashboard.widgets or [])]
    return {
        "_id": str(dashboard.id),
        "org_id": str(getattr(dashboard, "organization_id", "")),
        "project_id": getattr(dashboard, "project_id", None),
        "name": dashboard.title,
        "description": dashboard.description or "",
        "is_public": getattr(dashboard, "is_shared", False),
        "public_token": getattr(dashboard, "share_token", None),
        "canvas": {
            "width": getattr(dashboard, "canvas_width", 1920),
            "height": getattr(dashboard, "canvas_height", 1080),
            "background_color": getattr(dashboard, "background_color", "#F5F5F5"),
            "widgets": widgets,
        },
        "settings": {
            "auto_refresh": getattr(dashboard, "auto_refresh", False),
            "refresh_interval_seconds": getattr(
                dashboard, "refresh_interval_seconds", 60
            ),
            "theme": getattr(dashboard, "theme", {}) or {},
        },
        "linked_analysis_ids": getattr(dashboard, "linked_analysis_ids", []) or [],
        "created_at": getattr(dashboard, "created_at", None),
        "updated_at": getattr(dashboard, "updated_at", None),
        "created_by": str(getattr(dashboard, "created_by", "")),
    }


# --- CRUD Operations ---


@dashboard_bp.route("/", methods=["POST"])
@swag_from(
    {
        "tags": ["Dashboard"],
        "responses": {"200": {"description": "Create a new Dashboard configuration."}},
        "parameters": [
            {
                "name": "body",
                "in": "body",
                "schema": {"$ref": "#/definitions/DashboardCreateSchema"},
            }
        ],
    }
)
@jwt_required()
@require_permission("dashboard", "create")
def create_dashboard():
    """Create a new Dashboard configuration."""
    current_user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(
        f"User {current_user_id} is creating a new dashboard for org {org_id}"
    )

    data = request.get_json() or {}
    if "name" in data and "title" not in data:
        data["title"] = data["name"]
    if isinstance(data.get("canvas"), dict):
        canvas = data["canvas"]
        data.setdefault("layout", "freeform")
        data.setdefault("canvas_width", canvas.get("width", 1920))
        data.setdefault("canvas_height", canvas.get("height", 1080))
        data.setdefault("background_color", canvas.get("background_color", "#F5F5F5"))
        data.setdefault("widgets", canvas.get("widgets", []))

    try:
        data["created_by"] = current_user_id
        data["organization_id"] = org_id
        schema = DashboardCreateSchema(**data)
        result = dashboard_service.create(schema)

        audit_logger.info(
            f"Dashboard created: ID={result.id}, Title='{result.title}', CreatedBy={current_user_id}, OrgID={org_id}"
        )
        app_logger.info(f"Dashboard {result.id} created successfully")
        return success_response(
            data={"dashboard": _docs_dashboard(result)},
            message="Dashboard created",
            status_code=201,
        )
    except Exception as e:
        error_logger.error(
            f"Create Dashboard error for user {current_user_id}: {str(e)}",
            exc_info=True,
        )
        return error_response(message=str(e), status_code=400)


def resolve_widget_data(widget: WidgetSchema, org_id: str, runtime_filters=None):
    """
    Resolves widget data using high-performance MongoDB Aggregation pipelines.
    """
    app_logger.debug(
        f"Resolving data for widget: {widget.title} (type: {widget.type}) for org {org_id}"
    )

    if not widget.form_id:
        return {**widget.model_dump(), "data": None}

    import uuid
    from bson import DBRef
    form_ref_val = widget.form_id
    try:
        val_uuid = uuid.UUID(widget.form_id)
        form_ref_val = DBRef("forms", val_uuid)
    except (ValueError, TypeError):
        pass

    # MongoEngine query uses __ for nested dict fields
    mongo_query = {
        "form": form_ref_val,
        "is_deleted": False,
        "organization_id": org_id,
    }

    # Raw PyMongo query for aggregations uses dot notation for nested dict fields
    raw_query = {
        "form": form_ref_val,
        "is_deleted": False,
        "organization_id": org_id,
    }

    # Add optional filters from widget config
    if widget.filters:
        for key, val in widget.filters.items():
            mongo_query[f"data__{key}"] = val
            raw_query[f"data.{key}"] = val

    # Merge runtime filters (e.g., from request query parameters)
    if runtime_filters:
        for key, val in runtime_filters.items():
            mongo_query[f"data__{key}"] = val
            raw_query[f"data.{key}"] = val

    pipeline = [{"$match": raw_query}]

    try:
        if widget.type in ["chart_bar", "chart_pie", "chart_line"]:
            group_by = widget.group_by_field
            agg_field = widget.aggregate_field
            calc_type = widget.calculation_type

            if not group_by:
                return {
                    **widget.model_dump(),
                    "data": {"error": "Missing group_by_field"},
                }

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
            res_data = FormResponse.objects(**mongo_query).count()

        elif widget.type in ["table", "list_view"]:
            limit = widget.config.get("limit", 10)
            results = (
                FormResponse.objects(**mongo_query)
                .order_by("-submitted_at")
                .limit(limit)
                .only("id", "data", "submitted_at")
            )
            res_data = []
            for r in results:
                res_data.append(
                    {
                        "id": str(r.id),
                        "submitted_at": r.submitted_at.isoformat(),
                        "data": r.data,
                    }
                )
        else:
            res_data = None

    except Exception as w_err:
        error_logger.error(
            f"Aggregation failed for widget {widget.title}: {w_err}", exc_info=True
        )
        res_data = {"error": "Aggregation failure"}

    return {**widget.model_dump(), "data": res_data}


@dashboard_bp.route("/<slug>", methods=["GET"])
@swag_from(
    {
        "tags": ["Dashboard"],
        "responses": {
            "200": {"description": "Get dashboard details AND fetch data for widgets."}
        },
        "parameters": [
            {"name": "slug", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
@require_permission("dashboard", "view")
def get_dashboard(slug):
    """Get dashboard details AND fetch data for widgets."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(f"User {user_id} fetching dashboard {slug} for org {org_id}")

    try:
        dashboard = dashboard_service.get_by_slug(slug, organization_id=org_id)

        # Extract runtime filters from query parameters (starting with filter_)
        runtime_filters = {}
        for key, val in request.args.items():
            if key.startswith("filter_"):
                real_key = key[7:]
                runtime_filters[real_key] = val

        # Resolve Widget Data
        widgets_data = [resolve_widget_data(w, org_id, runtime_filters) for w in dashboard.widgets]

        result = dashboard.model_dump()
        result["widgets"] = widgets_data

        app_logger.info(
            f"Dashboard {slug} data retrieved successfully for user {user_id}"
        )
        return success_response(data={"dashboard": _docs_dashboard(dashboard)})
    except NotFoundError:
        app_logger.warning(
            f"Dashboard {slug} not found for org {org_id} (requested by user {user_id})"
        )
        return error_response(message="Dashboard not found", status_code=404)
    except Exception as e:
        error_logger.error(
            f"Get Dashboard error for user {user_id}, slug {slug}: {str(e)}",
            exc_info=True,
        )
        return error_response(message="Failed to load dashboard data", status_code=500)


@dashboard_bp.route("/<dashboard_id>/canvas", methods=["GET"])
@jwt_required()
@require_permission("dashboard", "view")
def get_dashboard_canvas(dashboard_id):
    """Get the canonical dashboard canvas payload."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(
        f"User {user_id} fetching dashboard canvas {dashboard_id} for org {org_id}"
    )

    if not org_id:
        return error_response(message="Organization context missing", status_code=400)

    try:
        canvas = dashboard_service.get_canvas(dashboard_id, organization_id=org_id)
        return success_response(data=canvas)
    except NotFoundError:
        return error_response(message="Dashboard not found", status_code=404)
    except Exception as e:
        error_logger.error(
            f"Get dashboard canvas error for user {user_id}, ID {dashboard_id}: {str(e)}",
            exc_info=True,
        )
        return error_response(message="Failed to load dashboard canvas", status_code=500)


@dashboard_bp.route("/<dashboard_id>/canvas", methods=["PUT"])
@swag_from(
    {
        "tags": ["Dashboard"],
        "responses": {"200": {"description": "Update dashboard canvas."}},
        "parameters": [
            {"name": "dashboard_id", "in": "path", "type": "string", "required": True},
            {
                "name": "body",
                "in": "body",
                "schema": {"type": "object"},
            },
        ],
    }
)
@jwt_required()
@require_permission("dashboard", "edit")
def update_dashboard_canvas(dashboard_id):
    """Update the canonical dashboard canvas payload."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(
        f"User {user_id} updating dashboard canvas {dashboard_id} for org {org_id}"
    )

    if not org_id:
        return error_response(message="Organization context missing", status_code=400)

    try:
        data = request.get_json(silent=True) or {}
        result = dashboard_service.update_canvas(
            dashboard_id, organization_id=org_id, canvas_data=data
        )
        audit_logger.info(
            f"Dashboard canvas updated: ID={dashboard_id}, UpdatedBy={user_id}, OrgID={org_id}"
        )
        return success_response(data=result, message="Dashboard canvas updated")
    except NotFoundError:
        return error_response(message="Dashboard not found", status_code=404)
    except Exception as e:
        error_logger.error(
            f"Update dashboard canvas error for user {user_id}, ID {dashboard_id}: {str(e)}",
            exc_info=True,
        )
        return error_response(message=str(e), status_code=400)


@dashboard_bp.route("/<dashboard_id>/snapshots", methods=["GET"])
@jwt_required()
@require_permission("dashboard", "view")
def list_dashboard_snapshots(dashboard_id):
    """Return the available dashboard snapshots."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(
        f"User {user_id} listing dashboard snapshots {dashboard_id} for org {org_id}"
    )

    if not org_id:
        return error_response(message="Organization context missing", status_code=400)

    try:
        snapshots = dashboard_service.list_snapshots(
            dashboard_id, organization_id=org_id
        )
        return success_response(
            data={"dashboard_id": dashboard_id, "snapshots": snapshots}
        )
    except NotFoundError:
        return error_response(message="Dashboard not found", status_code=404)
    except Exception as e:
        error_logger.error(
            f"List dashboard snapshots error for user {user_id}, ID {dashboard_id}: {str(e)}",
            exc_info=True,
        )
        return error_response(
            message="Failed to load dashboard snapshots", status_code=500
        )



@dashboard_bp.route("/<dashboard_id>", methods=["PUT"])
@swag_from(
    {
        "tags": ["Dashboard"],
        "responses": {"200": {"description": "Update Dashboard configuration."}},
        "parameters": [
            {"name": "dashboard_id", "in": "path", "type": "string", "required": True},
            {
                "name": "body",
                "in": "body",
                "schema": {"$ref": "#/definitions/DashboardUpdateSchema"},
            },
        ],
    }
)
@jwt_required()
@require_permission("dashboard", "edit")
def update_dashboard(dashboard_id):
    """Update Dashboard configuration."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(
        f"User {user_id} updating dashboard {dashboard_id} for org {org_id}"
    )

    if not org_id:
        error_logger.warning(
            f"Update dashboard failed for user {user_id}: Organization context missing"
        )
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
        error_logger.error(
            f"Update Dashboard error for user {user_id}, ID {dashboard_id}: {str(e)}",
            exc_info=True,
        )
        return error_response(message=str(e), status_code=400)


@dashboard_bp.route("/<dashboard_id>/share", methods=["POST"])
@jwt_required()
@require_permission("dashboard", "edit")
def share_dashboard(dashboard_id):
    """Generate a public share token for a dashboard."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    try:
        from models.Dashboard import Dashboard
        dashboard = Dashboard.objects.get(
            id=dashboard_id, organization_id=org_id, is_deleted=False
        )
        if not dashboard.share_token:
            dashboard.share_token = str(uuid.uuid4())
        dashboard.is_shared = True
        dashboard.save()
        audit_logger.info(f"AUDIT: Dashboard {dashboard_id} shared by user {user_id}")
        return success_response(
            data={"share_token": dashboard.share_token, "is_shared": dashboard.is_shared},
            message="Dashboard shared successfully"
        )
    except Dashboard.DoesNotExist:
        return error_response(message="Dashboard not found", status_code=404)
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@dashboard_bp.route("/<dashboard_id>/unshare", methods=["POST"])
@jwt_required()
@require_permission("dashboard", "edit")
def unshare_dashboard(dashboard_id):
    """Disable public sharing for a dashboard."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    try:
        from models.Dashboard import Dashboard
        dashboard = Dashboard.objects.get(
            id=dashboard_id, organization_id=org_id, is_deleted=False
        )
        dashboard.is_shared = False
        dashboard.save()
        audit_logger.info(f"AUDIT: Dashboard {dashboard_id} unshared by user {user_id}")
        return success_response(
            data={"is_shared": dashboard.is_shared},
            message="Dashboard unshared successfully"
        )
    except Dashboard.DoesNotExist:
        return error_response(message="Dashboard not found", status_code=404)
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@dashboard_bp.route("/shared/<share_token>", methods=["GET"])
def get_shared_dashboard(share_token):
    """Get shared dashboard details and widget data publicly."""
    try:
        from models.Dashboard import Dashboard
        dashboard = Dashboard.objects.get(
            share_token=share_token, is_shared=True, is_deleted=False
        )
        runtime_filters = {}
        for key, val in request.args.items():
            if key.startswith("filter_"):
                real_key = key[7:]
                runtime_filters[real_key] = val

        widgets_data = []
        for w in dashboard.widgets:
            from bson import DBRef
            raw_form_ref = w._data.get("form_ref") if hasattr(w, "_data") else None
            form_id_str = None
            if raw_form_ref:
                if isinstance(raw_form_ref, DBRef):
                    form_id_str = str(raw_form_ref.id)
                elif hasattr(raw_form_ref, "id"):
                    form_id_str = str(raw_form_ref.id)
                else:
                    form_id_str = str(raw_form_ref)
            widget_dict = {
                "id": str(w.id),
                "title": w.title,
                "type": w.type,
                "form_id": form_id_str,
                "group_by_field": w.group_by_field,
                "aggregate_field": w.aggregate_field,
                "calculation_type": w.calculation_type,
                "filters": w.filters or {},
                "size": w.size,
                "color_scheme": w.color_scheme,
                "position_x": w.position_x,
                "position_y": w.position_y,
                "width": w.width,
                "height": w.height,
                "display_columns": w.display_columns or [],
                "config": w.config or {},
            }
            widget_schema = WidgetSchema(**widget_dict)
            widgets_data.append(resolve_widget_data(widget_schema, dashboard.organization_id, runtime_filters))

        result = {
            "title": dashboard.title,
            "description": dashboard.description,
            "layout": dashboard.layout,
            "widgets": widgets_data
        }
        return success_response(data=result)
    except Dashboard.DoesNotExist:
        return error_response(message="Shared dashboard not found or inactive", status_code=404)
    except Exception as e:
        error_logger.error(f"Error fetching shared dashboard: {e}", exc_info=True)
        return error_response(message="Failed to load shared dashboard", status_code=500)


@dashboard_bp.route("/<dashboard_id>/export", methods=["GET"])
@jwt_required()
@require_permission("dashboard", "view")
def export_dashboard(dashboard_id):
    """Export dashboard details and aggregated widget data."""
    org_id = get_jwt().get("org_id")
    export_format = request.args.get("format", "json").lower()
    try:
        from models.Dashboard import Dashboard
        dashboard = Dashboard.objects.get(
            id=dashboard_id, organization_id=org_id, is_deleted=False
        )
        
        widgets_data = []
        for w in dashboard.widgets:
            from bson import DBRef
            raw_form_ref = w._data.get("form_ref") if hasattr(w, "_data") else None
            form_id_str = None
            if raw_form_ref:
                if isinstance(raw_form_ref, DBRef):
                    form_id_str = str(raw_form_ref.id)
                elif hasattr(raw_form_ref, "id"):
                    form_id_str = str(raw_form_ref.id)
                else:
                    form_id_str = str(raw_form_ref)
            widget_dict = {
                "id": str(w.id),
                "title": w.title,
                "type": w.type,
                "form_id": form_id_str,
                "group_by_field": w.group_by_field,
                "aggregate_field": w.aggregate_field,
                "calculation_type": w.calculation_type,
                "filters": w.filters or {},
                "size": w.size,
                "color_scheme": w.color_scheme,
                "position_x": w.position_x,
                "position_y": w.position_y,
                "width": w.width,
                "height": w.height,
                "display_columns": w.display_columns or [],
                "config": w.config or {},
            }
            widget_schema = WidgetSchema(**widget_dict)
            widgets_data.append(resolve_widget_data(widget_schema, org_id))

        if export_format == "csv":
            import io
            import csv
            from flask import Response
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            writer.writerow(["Dashboard Title", dashboard.title])
            writer.writerow(["Description", dashboard.description])
            writer.writerow([])
            
            for wd in widgets_data:
                writer.writerow(["Widget Title", wd["title"]])
                writer.writerow(["Widget Type", wd["type"]])
                data_val = wd.get("data")
                if isinstance(data_val, dict) and "labels" in data_val:
                    writer.writerow(["Label", "Value"])
                    for lbl, val in zip(data_val["labels"], data_val["values"]):
                        writer.writerow([lbl, val])
                elif isinstance(data_val, (int, float)):
                    writer.writerow(["KPI Value", data_val])
                elif isinstance(data_val, list):
                    if data_val:
                        keys = list(data_val[0].keys())
                        writer.writerow(keys)
                        for row in data_val:
                            writer.writerow([row.get(k) for k in keys])
                writer.writerow([])
            
            return Response(
                output.getvalue(),
                mimetype="text/csv",
                headers={"Content-disposition": f"attachment; filename=dashboard_export_{dashboard_id}.csv"}
            )
            
        export_data = {
            "title": dashboard.title,
            "description": dashboard.description,
            "widgets": widgets_data
        }
        return success_response(data=export_data)
    except Dashboard.DoesNotExist:
        return error_response(message="Dashboard not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Export dashboard error: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)
