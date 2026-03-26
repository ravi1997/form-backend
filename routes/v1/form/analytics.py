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

# -------------------- Analytics Endpoints --------------------


@form_bp.route("/<form_id>/analytics/summary", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def get_analytics_summary(form_id):
    app_logger.info(f"Entering get_analytics_summary for form_id: {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)

        if not has_form_permission(current_user, form, "view"):
            app_logger.warning(f"Unauthorized analytics summary access attempt for form_id: {form_id} by user: {getattr(current_user, 'id', 'unknown')}")
            return jsonify({"error": "Unauthorized"}), 403

        # Python-side aggregation for robustness
        responses = FormResponse.objects(form=form.id, deleted=False)

        total = responses.count()

        # Optimize: fetch only status
        statuses = [r.status or "submitted" for r in responses.only("status")]
        status_breakdown = dict(Counter(statuses))

        last_submission = responses.order_by("-submitted_at").first()
        last_submitted_at = (
            last_submission.submitted_at.isoformat() if last_submission else None
        )

        app_logger.info(f"Successfully retrieved analytics summary for form_id: {form_id}")
        return (
            jsonify(
                {
                    "total_responses": total,
                    "status_breakdown": status_breakdown,
                    "last_submitted_at": last_submitted_at,
                }
            ),
            200,
        )

    except DoesNotExist:
        app_logger.warning(f"Form not found for analytics summary: {form_id}")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(f"Error in get_analytics_summary for form_id {form_id}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@form_bp.route("/<form_id>/analytics/timeline", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def get_analytics_timeline(form_id):
    app_logger.info(f"Entering get_analytics_timeline for form_id: {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)

        if not has_form_permission(current_user, form, "view"):
            app_logger.warning(f"Unauthorized analytics timeline access attempt for form_id: {form_id} by user: {getattr(current_user, 'id', 'unknown')}")
            return jsonify({"error": "Unauthorized"}), 403

        days = request.args.get("days", 30, type=int)
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Python-side aggregation
        responses = FormResponse.objects(
            form=form.id, deleted=False, submitted_at__gte=start_date
        ).only("submitted_at")

        date_counts = Counter()
        for r in responses:
            if r.submitted_at:
                date_str = r.submitted_at.strftime("%Y-%m-%d")
                date_counts[date_str] += 1

        # Sort by date
        sorted_dates = sorted(date_counts.keys())
        timeline = [{"date": d, "count": date_counts[d]} for d in sorted_dates]

        app_logger.info(f"Successfully retrieved analytics timeline for form_id: {form_id}")
        return jsonify({"period_days": days, "timeline": timeline}), 200

    except DoesNotExist:
        app_logger.warning(f"Form not found for analytics timeline: {form_id}")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(f"Analytics Timeline Error for form_id {form_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


@form_bp.route("/<form_id>/analytics/distribution", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def get_analytics_distribution(form_id):
    app_logger.info(f"Entering get_analytics_distribution for form_id: {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)

        if not has_form_permission(current_user, form, "view"):
            app_logger.warning(f"Unauthorized analytics distribution access attempt for form_id: {form_id} by user: {getattr(current_user, 'id', 'unknown')}")
            return jsonify({"error": "Unauthorized"}), 403

        # Identify choice-based questions from latest version
        if not form.versions:
            app_logger.info(f"No versions found for form_id: {form_id}, returning empty distribution")
            return jsonify({"distribution": {}}), 200

        latest_version = form.versions[-1]
        choice_questions = {}  # qid -> label

        target_types = ["radio", "select", "checkbox", "rating", "boolean"]

        for section in latest_version.sections:
            sid = str(section.id)
            for q in section.questions:
                if q.field_type in target_types:
                    choice_questions[str(q.id)] = {
                        "label": q.label,
                        "sid": sid,
                        "type": q.field_type,
                    }

        # Process responses (Python-side for flexibility)
        # Fetch only necessary fields to optimize
        responses = FormResponse.objects(form=form.id, deleted=False).only("data")

        distribution = defaultdict(Counter)  # qid -> Counter

        for r in responses:
            for qid, info in choice_questions.items():
                sid = info["sid"]
                section_data = r.data.get(sid)

                if not section_data:
                    continue

                # Handle Repeatable Sections?
                # If repeatable, we aggregate ALL answers from that section
                entries = (
                    section_data if isinstance(section_data, list) else [section_data]
                )

                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    val = entry.get(qid)

                    if val is None or val == "":
                        continue

                    if isinstance(val, list):
                        # Checkboxes
                        for v in val:
                            distribution[qid][str(v)] += 1
                    else:
                        distribution[qid][str(val)] += 1

        # Format result
        results = []
        for qid, counts in distribution.items():
            results.append(
                {
                    "question_id": qid,
                    "label": choice_questions[qid]["label"],
                    "type": choice_questions[qid]["type"],
                    "counts": dict(counts),
                }
            )

        app_logger.info(f"Successfully retrieved analytics distribution for form_id: {form_id}")
        return jsonify({"distribution": results}), 200

    except DoesNotExist:
        app_logger.warning(f"Form not found for analytics distribution: {form_id}")
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        error_logger.error(f"Analytics Distribution Error for form_id {form_id}: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@form_bp.route("/<form_id>/analytics", methods=["GET"])
@swag_from({
    "tags": [
        "Form"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    },
    "parameters": [
        {
            "name": "form_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def get_full_analytics(form_id):
    """
    M-11 Aggregated Analytics Endpoint
    Returns: totalSubmissions, completionRate, trends, fieldDistributions
    """
    app_logger.info(f"Entering get_full_analytics for form_id: {form_id}")
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)

        if not has_form_permission(current_user, form, "view"):
            app_logger.warning(f"Unauthorized full analytics access attempt for form_id: {form_id} by user: {getattr(current_user, 'id', 'unknown')}")
            return jsonify({"error": "Unauthorized"}), 403

        # 1. Total Submissions
        responses = FormResponse.objects(form=form.id, deleted=False).only(
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

            # Map qid -> label
            q_map = {}
            for s in latest.sections:
                sid = str(s.id)
                for q in s.questions:
                    if q.field_type in target_types:
                        q_map[str(q.id)] = {"label": q.label, "sid": sid}

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

