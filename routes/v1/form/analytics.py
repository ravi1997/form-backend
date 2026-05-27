from . import form_bp
from flasgger import swag_from
from flask import jsonify, request, current_app
from flask_jwt_extended import jwt_required
from routes.v1.form import form_bp
from models import Form, FormResponse
from routes.v1.form.helper import get_current_user, has_form_permission
from mongoengine.errors import DoesNotExist
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict
from logger.unified_logger import app_logger, error_logger
from services.analytics_service import AnalyticsService
from services.analytics_cache import analytics_cache

# -------------------- Analytics Endpoints --------------------


@form_bp.route("/<form_id>/analytics/summary", methods=["GET"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {"200": {"description": "Success"}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
def get_analytics_summary(form_id):
    app_logger.info(f"Entering get_analytics_summary for form_id: {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id
        )

        if not has_form_permission(current_user, form, "view"):
            app_logger.warning(
                f"Unauthorized analytics summary access attempt for form_id: {form_id} by user: {getattr(current_user, 'id', 'unknown')}"
            )
            return jsonify({"error": "Unauthorized"}), 403

        cache_key_params = {"metric_type": "summary"}
        cached_result = analytics_cache.get(form_id, "summary", cache_key_params)

        if cached_result:
            app_logger.info(
                f"Returning cached analytics summary for form_id: {form_id}"
            )
            return jsonify(cached_result), 200

        result = AnalyticsService.get_analytics_summary(
            form_id, current_user.organization_id
        )

        analytics_cache.set(form_id, "summary", result, cache_key_params, ttl=300)

        app_logger.info(
            f"Successfully retrieved analytics summary for form_id: {form_id}"
        )
        return jsonify(result), 200

    except DoesNotExist:
        app_logger.warning(f"Form not found for analytics summary: {form_id}")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(
            f"Error in get_analytics_summary for form_id {form_id}: {str(e)}"
        )
        return jsonify({"error": "Internal server error"}), 500


@form_bp.route("/<form_id>/analytics/timeline", methods=["GET"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {"200": {"description": "Success"}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
def get_analytics_timeline(form_id):
    app_logger.info(f"Entering get_analytics_timeline for form_id: {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id
        )

        if not has_form_permission(current_user, form, "view"):
            app_logger.warning(
                f"Unauthorized analytics timeline access attempt for form_id: {form_id} by user: {getattr(current_user, 'id', 'unknown')}"
            )
            return jsonify({"error": "Unauthorized"}), 403

        days = request.args.get("days", 30, type=int)
        cache_key_params = {"metric_type": "timeline", "days": days}

        cached_result = analytics_cache.get(form_id, "timeline", cache_key_params)

        if cached_result:
            app_logger.info(
                f"Returning cached analytics timeline for form_id: {form_id}"
            )
            return jsonify(cached_result), 200

        result = AnalyticsService.get_analytics_timeline(
            form_id, current_user.organization_id, days
        )

        analytics_cache.set(form_id, "timeline", result, cache_key_params, ttl=300)

        app_logger.info(
            f"Successfully retrieved analytics timeline for form_id: {form_id}"
        )
        return jsonify(result), 200

    except DoesNotExist:
        app_logger.warning(f"Form not found for analytics timeline: {form_id}")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(f"Analytics Timeline Error for form_id {form_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


@form_bp.route("/<form_id>/analytics/distribution", methods=["GET"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {"200": {"description": "Success"}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
def get_analytics_distribution(form_id):
    app_logger.info(f"Entering get_analytics_distribution for form_id: {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id
        )

        if not has_form_permission(current_user, form, "view"):
            app_logger.warning(
                f"Unauthorized analytics distribution access attempt for form_id: {form_id} by user: {getattr(current_user, 'id', 'unknown')}"
            )
            return jsonify({"error": "Unauthorized"}), 403

        cache_key_params = {"metric_type": "distribution"}
        cached_result = analytics_cache.get(form_id, "distribution", cache_key_params)

        if cached_result:
            app_logger.info(
                f"Returning cached analytics distribution for form_id: {form_id}"
            )
            return jsonify(cached_result), 200

        result = AnalyticsService.get_analytics_distribution(
            form_id, current_user.organization_id, form
        )

        analytics_cache.set(form_id, "distribution", result, cache_key_params, ttl=300)

        app_logger.info(
            f"Successfully retrieved analytics distribution for form_id: {form_id}"
        )
        return jsonify(result), 200

    except DoesNotExist:
        app_logger.warning(f"Form not found for analytics distribution: {form_id}")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(
            f"Analytics Distribution Error for form_id {form_id}: {str(e)}"
        )
        return jsonify({"error": "Internal server error"}), 500


@form_bp.route("/<form_id>/analytics", methods=["GET"])
@swag_from(
    {
        "tags": ["Form"],
        "responses": {"200": {"description": "Success"}},
        "parameters": [
            {"name": "form_id", "in": "path", "type": "string", "required": True}
        ],
    }
)
@jwt_required()
def get_full_analytics(form_id):
    """
    M-11 Aggregated Analytics Endpoint
    Returns: totalSubmissions, completionRate, trends, fieldDistributions
    """
    app_logger.info(f"Entering get_full_analytics for form_id: {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(
            id=form_id, organization_id=current_user.organization_id
        )

        if not has_form_permission(current_user, form, "view"):
            app_logger.warning(
                f"Unauthorized full analytics access attempt for form_id: {form_id} by user: {getattr(current_user, 'id', 'unknown')}"
            )
            return jsonify({"error": "Unauthorized"}), 403

        # 1. Total Submissions
        responses = FormResponse.objects(form=form.id, is_deleted=False).only(
            "submitted_at", "data"
        )
        total = responses.count()

        # 2. Trends (Last 7 days including today)
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=6)
        # timeline_responses = [r for r in responses if r.submitted_at >= seven_days_ago]

        timeline_responses = []
        for r in responses:
            if r.submitted_at:
                r_dt = r.submitted_at
                # Handle naive datetimes (assume UTC if naive)
                if r_dt.tzinfo is None:
                    r_dt = r_dt.replace(tzinfo=timezone.utc)

                if r_dt >= start_date:
                    timeline_responses.append(r)

        date_counts = Counter()
        for r in timeline_responses:
            if r.submitted_at:
                d_str = r.submitted_at.strftime("%Y-%m-%d")
                date_counts[d_str] += 1

        # Fill zeros for last 7 days
        trends = []
        for i in range(7):
            d = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            trends.append({"date": d, "value": date_counts.get(d, 0)})

        # 3. Field Distributions
        # Reuse logic from get_analytics_distribution but streamlined
        distribution = defaultdict(Counter)

        if form.versions:
            latest = form.versions[-1]
            target_types = ["radio", "select", "checkbox", "rating", "boolean"]
            sections = (
                latest.resolved_snapshot.get("sections", [])
                if hasattr(latest, "resolved_snapshot")
                else []
            )

            # Map qid -> label
            q_map = {}
            for s in sections:
                sid = str(s.get("id"))
                for q in s.get("questions", []):
                    if q.get("field_type") in target_types:
                        q_map[str(q.get("id"))] = {"label": q.get("label"), "sid": sid}

            for r in responses:
                for qid, info in q_map.items():
                    sid = info["sid"]
                    # Data structure: data[sid][qid]
                    sec_data = r.data.get(sid)
                    if not sec_data:
                        continue

                    entries = sec_data if isinstance(sec_data, list) else [sec_data]
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                        val = entry.get(qid)
                        if val is None or val == "":
                            continue

                        if isinstance(val, list):
                            for v in val:
                                distribution[info["label"]][str(v)] += 1
                        else:
                            distribution[info["label"]][str(val)] += 1

        # Format distribution
        field_dist_map = {}
        for label, counts in distribution.items():
            total_answers = sum(counts.values())
            field_dist_map[label] = [
                {
                    "label": k,
                    "count": v,
                    "percentage": (
                        round((v / total_answers) * 100, 1) if total_answers > 0 else 0
                    ),
                }
                for k, v in counts.items()
            ]

        app_logger.info(f"Successfully retrieved full analytics for form_id: {form_id}")
        return (
            jsonify(
                {
                    "totalSubmissions": total,
                    "completionRate": (
                        0.0 if total == 0 else 0.85
                    ),  # Mocked as requested
                    "trends": trends,
                    "fieldDistributions": field_dist_map,
                }
            ),
            200,
        )

    except DoesNotExist:
        app_logger.warning(f"Form not found for full analytics: {form_id}")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(f"Full Analytics Error for form_id {form_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500
