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
import re
from logger.unified_logger import app_logger, error_logger, audit_logger

dashboard_bp = Blueprint("dashboard", __name__)
dashboard_service = DashboardService()


def _docs_widget(widget):
    if isinstance(widget, dict):
        return widget
        
    pos = getattr(widget, "position", None)
    ds = getattr(widget, "data_source", None)
    cfg = getattr(widget, "config", None)
    
    properties = {
        "title": getattr(widget, "title", "") or "",
        "group_by_field": getattr(cfg, "group_by_field", None),
        "aggregate_field": getattr(cfg, "value_field", None),
        "calculation_type": getattr(cfg, "aggregation_type", "count") or "count",
        "filters": getattr(ds, "filters", {}) or {},
        "size": "medium",
        "color_scheme": getattr(cfg, "color_scheme", None),
        "display_columns": getattr(cfg, "display_columns", []) or [],
        "config": getattr(widget, "config", {}) or {},
    }
    if hasattr(cfg, "model_dump"):
        properties["config"] = cfg.model_dump()
        
    return {
        "id": str(getattr(widget, "id", "") or uuid.uuid4()),
        "type": getattr(widget, "widget_type", ""),
        "position": {
            "x": getattr(pos, "x", 0.0),
            "y": getattr(pos, "y", 0.0),
        },
        "size": {
            "width": getattr(pos, "width", 2.0),
            "height": getattr(pos, "height", 2.0),
        },
        "z_index": getattr(pos, "z_index", 0),
        "is_locked": getattr(widget, "is_locked", False),
        "properties": properties,
        "data_binding": {
            "analysis_id": str(getattr(ds, "analysis_id", "")) if getattr(ds, "analysis_id", None) else None,
            "node_id": getattr(ds, "node_id", None),
            "refresh_mode": getattr(ds, "refresh_mode", "with_dashboard"),
        },
        "form_ref": str(getattr(ds, "form_id", "")) if getattr(ds, "form_id", None) else None,
        "form_id": str(getattr(ds, "form_id", "")) if getattr(ds, "form_id", None) else None,
        "filters": [],
    }


def _backend_widget(widget):
    if not isinstance(widget, dict):
        return widget

    props = widget.get("properties", {}) or {}
    db = widget.get("data_binding", {}) or {}
    pos = widget.get("position", {}) or {}
    sz = widget.get("size", {}) or {}
    
    return {
        "id": widget.get("id") or str(uuid.uuid4()),
        "widget_type": widget.get("type") or widget.get("widget_type", ""),
        "title": props.get("title") or widget.get("title", ""),
        "description": widget.get("description", ""),
        "position": {
            "x": pos.get("x", 0.0),
            "y": pos.get("y", 0.0),
            "width": sz.get("width", 2.0),
            "height": sz.get("height", 2.0),
            "z_index": widget.get("z_index", 0),
        },
        "data_source": {
            "analysis_id": db.get("analysis_id") or widget.get("form_ref") or widget.get("form_id"),
            "node_id": db.get("node_id"),
            "form_id": widget.get("form_id") or widget.get("form_ref"),
            "refresh_mode": db.get("refresh_mode", "with_dashboard"),
            "filters": props.get("filters", {}) or {},
        },
        "config": {
            "chart_type": props.get("chart_type") or widget.get("type"),
            "aggregation_type": props.get("calculation_type", "count"),
            "group_by_field": props.get("group_by_field"),
            "value_field": props.get("aggregate_field"),
            "color_scheme": props.get("color_scheme"),
            "display_columns": props.get("display_columns", []) or [],
        },
        "is_visible": widget.get("is_visible", True),
        "is_locked": widget.get("is_locked", False),
    }


def _resolve_widget_payloads(dashboard, org_id, runtime_filters=None):
    widgets_data = []
    for w in dashboard.widgets or []:
        widget_schema = dashboard_service._widget_to_schema(w)
        if widget_schema.data_source and widget_schema.data_source.analysis_id:
            try:
                from services.widget_data_binding_service import WidgetDataBindingService
                binding_service = WidgetDataBindingService()
                bound_data = binding_service.get_widget_data(
                    widget_id=widget_schema.id,
                    organization_id=org_id,
                    filters=runtime_filters
                )
                widget_payload = _docs_widget(w)
                widget_payload["data"] = bound_data.data
                widgets_data.append(widget_payload)
            except Exception as e:
                app_logger.error(f"Failed to resolve data binding for widget {w.id}: {e}", exc_info=True)
                widget_payload = _docs_widget(w)
                widget_payload["data"] = {"error": str(e), "status": "error"}
                widgets_data.append(widget_payload)
        else:
            widgets_data.append(
                resolve_widget_data(widget_schema, org_id, runtime_filters)
            )
    return widgets_data


def _docs_dashboard(dashboard, widgets_override=None):
    widgets = (
        widgets_override
        if widgets_override is not None
        else [_docs_widget(widget) for widget in (dashboard.widgets or [])]
    )
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
    if "title" in data and "slug" not in data:
        slug_base = re.sub(r"[^a-z0-9]+", "-", str(data["title"]).lower()).strip("-")
        data["slug"] = slug_base or f"dashboard-{uuid.uuid4().hex[:8]}"
    if isinstance(data.get("canvas"), dict):
        canvas = data["canvas"]
        data.setdefault("layout", "freeform")
        data.setdefault("canvas_width", canvas.get("width", 1920))
        data.setdefault("canvas_height", canvas.get("height", 1080))
        data.setdefault("background_color", canvas.get("background_color", "#F5F5F5"))
        data.setdefault(
            "widgets", [_backend_widget(widget) for widget in canvas.get("widgets", [])]
        )

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
        f"Resolving data for widget: {widget.title} (type: {widget.widget_type}) for org {org_id}"
    )

    widget_form_id = None
    if widget.data_source:
        widget_form_id = widget.data_source.form_id or widget.data_source.analysis_id
    
    counter_types = {"counter", "kpi", "kpi_card"}
    if not widget_form_id:
        return {
            **_docs_widget(widget),
            "data": 0 if widget.widget_type in counter_types else None,
        }

    form_ref_val = str(widget_form_id)

    mongo_query = {
        "form": form_ref_val,
        "is_deleted": False,
        "organization_id": org_id,
    }

    raw_query = {
        "form": form_ref_val,
        "is_deleted": False,
        "organization_id": org_id,
    }

    def _response_filter_value(response, key):
        if isinstance(response, dict):
            response_data = response.get("data", {}) or {}
            if key in response_data:
                return response_data.get(key)
            if key in {"status", "review_status", "is_draft"}:
                return response.get(key)
            return response.get(key)
        response_data = getattr(response, "data", {}) or {}
        if key in response_data:
            return response_data.get(key)
        if key in {"status", "review_status", "is_draft"}:
            return getattr(response, key, None)
        if hasattr(response, key):
            return getattr(response, key)
        return None

    widget_filters = widget.data_source.filters if widget.data_source else {}

    def _matches_response(response) -> bool:
        response_form = getattr(response, "form", None)
        if response_form is None:
            return False
        if str(response_form) != str(form_ref_val):
            return False
        if str(getattr(response, "organization_id", "")) != str(org_id):
            return False
        if getattr(response, "is_deleted", False):
            return False

        if widget_filters:
            for key, val in widget_filters.items():
                if _response_filter_value(response, key) != val:
                    return False
        if runtime_filters:
            for key, val in runtime_filters.items():
                if _response_filter_value(response, key) != val:
                    return False
        return True

    # Add optional filters from widget config
    if widget_filters:
        for key, val in widget_filters.items():
            mongo_query[f"data__{key}"] = val
            raw_query[f"data.{key}"] = val

    # Merge runtime filters (e.g., from request query parameters)
    if runtime_filters:
        for key, val in runtime_filters.items():
            mongo_query[f"data__{key}"] = val
            raw_query[f"data.{key}"] = val

    pipeline = [{"$match": raw_query}]

    try:
        if widget.widget_type in [
            "chart_bar",
            "chart_pie",
            "chart_line",
            "bar_chart",
            "pie_chart",
            "line_chart",
        ]:
            group_by = widget.config.group_by_field if widget.config else None
            agg_field = widget.config.value_field if widget.config else None
            calc_type = widget.config.aggregation_type if widget.config else "count"

            if not group_by:
                return {
                    **_docs_widget(widget),
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

        elif widget.widget_type in counter_types:
            org_responses = list(FormResponse.objects.all_with_deleted())
            res_data = sum(1 for response in org_responses if _matches_response(response))
            if res_data == 0:
                res_data = FormResponse.objects(**mongo_query).count()
            if res_data == 0 and widget_filters:
                res_data = sum(
                    1
                    for response in org_responses
                    if all(
                        _response_filter_value(response, key) == val
                        for key, val in widget_filters.items()
                    )
                )
            if res_data == 0:
                raw_docs = list(
                    FormResponse._get_collection().find({"organization_id": org_id})
                )
                res_data = sum(
                    1
                    for doc in raw_docs
                    if all(
                        _response_filter_value(doc, key) == val
                        for key, val in {
                            **(widget_filters or {}),
                            **(runtime_filters or {}),
                        }.items()
                    )
                )

        elif widget.widget_type in ["table", "list_view", "data_table"]:
            limit = widget.config.max_items if widget.config else 10
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

    if res_data is None and widget.widget_type in counter_types:
        res_data = 0

    return {**_docs_widget(widget), "data": res_data}


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
        import bson
        if bson.ObjectId.is_valid(slug):
            dashboard = dashboard_service.get_dashboard(slug, organization_id=org_id)
        else:
            dashboard = dashboard_service.get_by_slug(slug, organization_id=org_id)

        # Extract runtime filters from query parameters (starting with filter_)
        runtime_filters = {}
        for key, val in request.args.items():
            if key.startswith("filter_"):
                real_key = key[7:]
                runtime_filters[real_key] = val

        # Resolve widget data for runtime preview.
        widgets_data = _resolve_widget_payloads(
            dashboard,
            org_id,
            runtime_filters,
        )
        payload = _docs_dashboard(dashboard, widgets_override=widgets_data)

        app_logger.info(
            f"Dashboard {slug} data retrieved successfully for user {user_id}"
        )
        return success_response(
            data={**payload, "widgets": widgets_data, "dashboard": payload}
        )
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
        include_data = str(request.args.get("include_data", "")).lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if include_data:
            from models.dashboard import Dashboard

            dashboard = Dashboard.objects.get(
                id=dashboard_id, organization_id=org_id, is_deleted=False
            )
            runtime_filters = {}
            for key, val in request.args.items():
                if key.startswith("filter_"):
                    runtime_filters[key[7:]] = val
            canvas["widgets"] = _resolve_widget_payloads(
                dashboard,
                org_id,
                runtime_filters,
            )
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
    if not org_id:
        return error_response(message="Organization context missing", status_code=400)
    try:
        from models.dashboard import Dashboard
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
    if not org_id:
        return error_response(message="Organization context missing", status_code=400)
    try:
        from models.dashboard import Dashboard
        dashboard = Dashboard.objects.get(
            id=dashboard_id, organization_id=org_id, is_deleted=False
        )
        dashboard.is_shared = False
        dashboard.share_token = None
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
        from models.dashboard import Dashboard
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
                "form_ref": form_id_str,
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
    if not org_id:
        return error_response(message="Organization context missing", status_code=400)
    try:
        from models.dashboard import Dashboard
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
                "form_ref": form_id_str,
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


# --- Remaining Phase 4 Dashboard Endpoints ---

from middleware.rate_limiter import rate_limit
from datetime import datetime, timezone
import bson

public_dashboard_bp = Blueprint("public_dashboard", __name__)


@dashboard_bp.route("/", methods=["GET"])
@jwt_required()
def list_dashboards():
    """List dashboards by project_id."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    project_id = request.args.get("project_id")
    app_logger.info(f"User {user_id} listing dashboards for org {org_id}, project {project_id}")
    try:
        dashboards = dashboard_service.list_dashboards(organization_id=org_id, project_id=project_id)
        docs_dashboards = [_docs_dashboard(d) for d in dashboards]
        return success_response(data={"dashboards": docs_dashboards})
    except Exception as e:
        error_logger.error(f"List dashboards error: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@dashboard_bp.route("/<dashboard_id>", methods=["PATCH"])
@jwt_required()
@require_permission("dashboard", "edit")
def patch_dashboard(dashboard_id):
    """Partial update of Dashboard metadata."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(f"User {user_id} patching dashboard {dashboard_id} for org {org_id}")
    if not org_id:
        return error_response(message="Organization context missing", status_code=400)
    try:
        data = request.get_json() or {}
        if "name" in data and "title" not in data:
            data["title"] = data["name"]
        schema = DashboardUpdateSchema(**data)
        result = dashboard_service.update_dashboard(dashboard_id, organization_id=org_id, update_data=schema, user_id=user_id)
        audit_logger.info(f"Dashboard patched: ID={dashboard_id}, Title='{result.title}', UpdatedBy={user_id}, OrgID={org_id}")
        return success_response(data=_docs_dashboard(result), message="Dashboard updated")
    except Exception as e:
        error_logger.error(f"Patch Dashboard error: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@dashboard_bp.route("/<dashboard_id>", methods=["DELETE"])
@jwt_required()
@require_permission("dashboard", "delete")
def delete_dashboard(dashboard_id):
    """Soft delete a dashboard."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(f"User {user_id} deleting dashboard {dashboard_id} for org {org_id}")
    if not org_id:
        return error_response(message="Organization context missing", status_code=400)
    try:
        dashboard_service.delete_dashboard(dashboard_id, organization_id=org_id, user_id=user_id)
        return success_response(message="Dashboard deleted successfully")
    except Exception as e:
        error_logger.error(f"Delete Dashboard error: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@dashboard_bp.route("/<dashboard_id>/canvas/data", methods=["GET"])
@jwt_required()
@require_permission("dashboard", "view")
def get_dashboard_canvas_data(dashboard_id):
    """Get the dashboard canvas with resolved widget data."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    app_logger.info(f"User {user_id} fetching dashboard canvas data {dashboard_id} for org {org_id}")
    if not org_id:
        return error_response(message="Organization context missing", status_code=400)
    try:
        from models.dashboard import Dashboard
        dashboard = Dashboard.objects.get(
            id=dashboard_id, organization_id=org_id, is_deleted=False
        )
        runtime_filters = {}
        for key, val in request.args.items():
            if key.startswith("filter_"):
                runtime_filters[key[7:]] = val

        widgets_data = _resolve_widget_payloads(
            dashboard,
            org_id,
            runtime_filters,
        )
        canvas = dashboard_service.get_canvas(dashboard_id, organization_id=org_id)
        canvas["widgets"] = widgets_data
        return success_response(data=canvas)
    except NotFoundError:
        return error_response(message="Dashboard not found", status_code=404)
    except Exception as e:
        error_logger.error(f"Get dashboard canvas data error: {e}", exc_info=True)
        return error_response(message=str(e), status_code=400)


@dashboard_bp.route("/<dashboard_id>/public-token", methods=["POST"])
@jwt_required()
@require_permission("dashboard", "edit")
def enable_public_token(dashboard_id):
    """Enable public sharing and generate public token."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    if not org_id:
        return error_response(message="Organization context missing", status_code=400)
    try:
        result = dashboard_service.enable_public_sharing(dashboard_id, org_id, user_id)
        return success_response(data=result, message="Public sharing enabled")
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@dashboard_bp.route("/<dashboard_id>/public-token", methods=["DELETE"])
@jwt_required()
@require_permission("dashboard", "edit")
def disable_public_token(dashboard_id):
    """Disable public sharing and revoke public token."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    if not org_id:
        return error_response(message="Organization context missing", status_code=400)
    try:
        dashboard_service.disable_public_sharing(dashboard_id, org_id, user_id)
        return success_response(message="Public sharing disabled")
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@dashboard_bp.route("/<dashboard_id>/data", methods=["GET"])
@jwt_required()
@require_permission("dashboard", "view")
def get_dashboard_data(dashboard_id):
    """Get resolved data for all widgets in the dashboard (authenticated)."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    if not org_id:
        return error_response(message="Organization context missing", status_code=400)
    try:
        from models.dashboard import Dashboard
        dashboard = Dashboard.objects.get(
            id=dashboard_id, organization_id=org_id, is_deleted=False
        )
        runtime_filters = {}
        for key, val in request.args.items():
            if key.startswith("filter_"):
                runtime_filters[key[7:]] = val

        widgets_data = _resolve_widget_payloads(
            dashboard,
            org_id,
            runtime_filters,
        )
        widget_data_only = {}
        for w in widgets_data:
            widget_data_only[w["id"]] = {
                "status": "ok" if "error" not in w.get("data", {}) else "error",
                "data": w.get("data"),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        return success_response(data={"widget_data": widget_data_only})
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@dashboard_bp.route("/<dashboard_id>/widgets/<widget_id>/data", methods=["GET"])
@jwt_required()
@require_permission("dashboard", "view")
def get_widget_data_endpoint(dashboard_id, widget_id):
    """Get independent data for a specific widget."""
    org_id = get_jwt().get("org_id")
    if not org_id:
        return error_response(message="Organization context missing", status_code=400)
    try:
        from services.widget_data_binding_service import WidgetDataBindingService
        binding_service = WidgetDataBindingService()
        
        runtime_filters = {}
        for key, val in request.args.items():
            if key.startswith("filter_"):
                runtime_filters[key[7:]] = val

        bound_data = binding_service.get_widget_data(widget_id, org_id, runtime_filters)
        return success_response(data={
            "widget_id": widget_id,
            "status": "ok",
            "data": bound_data.data,
            "generated_at": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@dashboard_bp.route("/<dashboard_id>/filter-options", methods=["GET"])
@jwt_required()
@require_permission("dashboard", "view")
def get_filter_options(dashboard_id):
    """Get distinct values for a column in an analysis output node."""
    org_id = get_jwt().get("org_id")
    analysis_id = request.args.get("analysis_id")
    node_id = request.args.get("node_id")
    column = request.args.get("column")
    limit = request.args.get("limit", 200, type=int)

    if not all([analysis_id, node_id, column]):
        return error_response(message="Missing required parameters: analysis_id, node_id, column", status_code=400)

    try:
        from models.analysis import AnalysisResults
        import bson

        analysis_result = AnalysisResults.objects(
            analysis_id=bson.ObjectId(analysis_id),
            node_id=node_id,
            organization_id=org_id,
            is_deleted=False
        ).order_by("-created_at").first()

        if not analysis_result or not analysis_result.data:
            return error_response(message="No analysis results found", status_code=404)

        rows = []
        if isinstance(analysis_result.data, dict):
            rows = analysis_result.data.get("rows", [])
        elif isinstance(analysis_result.data, list):
            rows = analysis_result.data

        distinct_vals = set()
        for r in rows:
            if isinstance(r, dict) and column in r:
                distinct_vals.add(str(r[column]))

        sorted_vals = sorted(list(distinct_vals))
        limited_vals = sorted_vals[:limit]

        return success_response(data={
            "column": column,
            "values": limited_vals,
            "total_distinct": len(distinct_vals)
        })
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@dashboard_bp.route("/<dashboard_id>/snapshots", methods=["POST"])
@jwt_required()
@require_permission("dashboard", "edit")
def create_snapshot(dashboard_id):
    """Create a new dashboard snapshot."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    if not org_id:
        return error_response(message="Organization context missing", status_code=400)
    try:
        from services.dashboard_snapshot_service import DashboardSnapshotService, SnapshotCreateSchema
        snapshot_service = DashboardSnapshotService()
        
        from models.dashboard import Dashboard
        dashboard = Dashboard.objects.get(id=dashboard_id, organization_id=org_id, is_deleted=False)
        
        schema = SnapshotCreateSchema(
            dashboard_id=dashboard_id,
            name=f"Snapshot - {dashboard.name} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            description=f"Automated snapshot of {dashboard.name}"
        )
        snapshot = snapshot_service.create_snapshot(schema, user_id, org_id)
        return success_response(
            data={"snapshot": snapshot.model_dump()},
            message="Snapshot created successfully",
            status_code=201
        )
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@dashboard_bp.route("/<dashboard_id>/snapshots/<snapshot_id>", methods=["GET"])
@jwt_required()
@require_permission("dashboard", "view")
def get_snapshot(dashboard_id, snapshot_id):
    """Get full dashboard snapshot details."""
    org_id = get_jwt().get("org_id")
    try:
        from services.dashboard_snapshot_service import DashboardSnapshotService
        snapshot_service = DashboardSnapshotService()
        snapshot = snapshot_service.get_snapshot(snapshot_id, org_id)
        return success_response(data={"snapshot": snapshot.model_dump()})
    except Exception as e:
        return error_response(message=str(e), status_code=400)


@dashboard_bp.route("/<dashboard_id>/snapshots/<snapshot_id>", methods=["DELETE"])
@jwt_required()
@require_permission("dashboard", "edit")
def delete_snapshot(dashboard_id, snapshot_id):
    """Delete a dashboard snapshot."""
    user_id = get_jwt_identity()
    org_id = get_jwt().get("org_id")
    try:
        from services.dashboard_snapshot_service import DashboardSnapshotService
        snapshot_service = DashboardSnapshotService()
        snapshot_service.delete_snapshot(snapshot_id, org_id, user_id)
        return success_response(message="Snapshot deleted successfully")
    except Exception as e:
        return error_response(message=str(e), status_code=400)


# --- Public blueprint endpoints ---

@public_dashboard_bp.route("/<public_token>", methods=["GET"])
@rate_limit("20 per minute")
def get_public_dashboard(public_token):
    """Get public dashboard canvas and widget data."""
    try:
        from models.dashboard import Dashboard
        dashboard = Dashboard.objects.get(
            public_token=public_token, is_public=True, is_deleted=False
        )
        runtime_filters = {}
        for key, val in request.args.items():
            if key.startswith("filter_"):
                runtime_filters[key[7:]] = val

        widgets_data = _resolve_widget_payloads(
            dashboard,
            dashboard.organization_id,
            runtime_filters,
        )
        
        stripped_widgets = []
        for w in widgets_data:
            w_copy = w.copy()
            if "data_binding" in w_copy:
                w_copy.pop("data_binding")
            if "form_ref" in w_copy:
                w_copy.pop("form_ref")
            if "form_id" in w_copy:
                w_copy.pop("form_id")
            stripped_widgets.append(w_copy)

        canvas_data = {
            "width": getattr(dashboard, "canvas_width", 1920),
            "height": getattr(dashboard, "canvas_height", 1080),
            "background_color": getattr(dashboard, "background_color", "#F5F5F5"),
            "widgets": stripped_widgets,
        }
        
        payload = {
            "name": dashboard.name,
            "description": dashboard.description or "",
            "canvas": canvas_data,
            "settings": {
                "auto_refresh": getattr(dashboard, "auto_refresh", False),
                "refresh_interval_seconds": getattr(dashboard, "refresh_interval_seconds", 60),
                "theme": getattr(dashboard, "theme", {}) or {},
            },
            "last_updated": (dashboard.updated_at or datetime.now(timezone.utc)).isoformat(),
        }
        return success_response(data={
            "dashboard": payload,
            "widget_data": {w["id"]: w.get("data") for w in widgets_data}
        })
    except Dashboard.DoesNotExist:
        return error_response(message="Public dashboard not found or inactive", status_code=404)
    except Exception as e:
        error_logger.error(f"Error fetching public dashboard: {e}", exc_info=True)
        return error_response(message="Failed to load public dashboard", status_code=500)


@public_dashboard_bp.route("/<public_token>/data", methods=["GET"])
@rate_limit("20 per minute")
def get_public_dashboard_data(public_token):
    """Poll public dashboard widget data."""
    try:
        from models.dashboard import Dashboard
        dashboard = Dashboard.objects.get(
            public_token=public_token, is_public=True, is_deleted=False
        )
        runtime_filters = {}
        for key, val in request.args.items():
            if key.startswith("filter_"):
                runtime_filters[key[7:]] = val

        widgets_data = _resolve_widget_payloads(
            dashboard,
            dashboard.organization_id,
            runtime_filters,
        )
        widget_data_only = {}
        for w in widgets_data:
            widget_data_only[w["id"]] = {
                "status": "ok" if "error" not in w.get("data", {}) else "error",
                "data": w.get("data"),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        return success_response(data={
            "widget_data": widget_data_only,
            "server_time": datetime.now(timezone.utc).isoformat()
        })
    except Dashboard.DoesNotExist:
        return error_response(message="Public dashboard not found or inactive", status_code=404)
    except Exception as e:
        error_logger.error(f"Error fetching public dashboard data: {e}", exc_info=True)
        return error_response(message="Failed to load public dashboard data", status_code=500)
