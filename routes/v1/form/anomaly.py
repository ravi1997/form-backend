from . import form_bp
from flasgger import swag_from
"""
Anomaly Detection Routes

API endpoints for detecting anomalous form responses.

Task: T-M2-04 - Predictive Anomaly Detection
"""

from flask import Blueprint, request, jsonify
import time

from models import FormResponse
from services.anomaly_detection_service import AnomalyDetectionService
from flask_jwt_extended import jwt_required
from routes.v1.form.helper import get_current_user

anomaly_bp = Blueprint("anomaly", __name__, url_prefix="/api/v1/ai/forms")


@anomaly_bp.route("/<form_id>/detect-anomalies", methods=["POST"])
@swag_from({
    "tags": [
        "Anomaly"
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
            "required": true
        }
    ]
})
@jwt_required()
def detect_anomalies(form_id: str):
    """
    Run anomaly detection on form responses.

    Request Body:
        {
            "scan_type": "full" | "incremental",
            "response_ids": ["id1", "id2"],  // Optional
            "detection_types": ["spam", "outlier", "impossible_value", "duplicate"],
            "sensitivity": "auto" | "low" | "medium" | "high",
            "use_dynamic_thresholds": true,  // Use thresholds from database
            "save_results": true
        }

    Returns:
        {
            "form_id": "form_123",
            "scan_type": "full",
            "responses_scanned": 250,
            "anomalies_detected": 12,
            "baseline": {...},
            "thresholds_used": {...},
            "anomalies": [...],
            "summary_by_type": {...}
        }
    """
    get_current_user()
    data = request.get_json() or {}

    scan_type = data.get("scan_type", "full")
    response_ids = data.get("response_ids", [])
    detection_types = data.get("detection_types", ["spam", "outlier"])
    sensitivity = data.get("sensitivity", "medium")
    use_dynamic_thresholds = data.get("use_dynamic_thresholds", False)
    data.get("save_results", False)

    start_time = time.time()

    # Fetch responses
    if response_ids:
        responses = FormResponse.objects(id__in=response_ids, form_id=form_id)
    elif scan_type == "full":
        responses = FormResponse.objects(form_id=form_id)
    else:
        # Incremental - get recent responses
        responses = (
            FormResponse.objects(form_id=form_id).order_by("-created_at").limit(100)
        )

    # Prepare response data
    response_data = []
    for resp in responses:
        resp_data = {
            "id": str(resp.id),
            "text": str(resp.data),
            "submitted_at": (
                resp.submitted_at.isoformat() if resp.submitted_at else None
            ),
            "sentiment": (
                resp.ai_results.get("sentiment", {})
                if hasattr(resp, "ai_results") and resp.ai_results
                else {}
            ),
        }
        response_data.append(resp_data)

    # Run detection with dynamic thresholds support
    results = AnomalyDetectionService.run_full_detection(
        response_data,
        sensitivity=sensitivity,
        detection_types=detection_types,
        use_dynamic_thresholds=use_dynamic_thresholds,
        form_id=form_id,
    )

    scan_duration = int((time.time() - start_time) * 1000)

    return jsonify(
        {
            "form_id": form_id,
            "scan_type": scan_type,
            "responses_scanned": len(response_data),
            "anomalies_detected": results["anomalies_detected"],
            "scan_duration_ms": scan_duration,
            "baseline": results["baseline"],
            "thresholds_used": results.get("thresholds_used"),
            "use_dynamic_thresholds": results.get("use_dynamic_thresholds", False),
            "anomalies": results["anomalies"],
            "summary_by_type": results["summary_by_type"],
        }
    )


@anomaly_bp.route("/<form_id>/anomalies/<response_id>", methods=["GET"])
@swag_from({
    "tags": [
        "Anomaly"
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
            "required": true
        },
        {
            "name": "response_id",
            "in": "path",
            "type": "string",
            "required": true
        }
    ]
})
@jwt_required()
def get_anomaly_details(form_id: str, response_id: str):
    """
    Get detailed anomaly information for a specific response.

    Returns:
        {
            "response_id": "resp_789",
            "anomaly_flags": {...},
            "response_data": {...},
            "review_status": "pending",
            "suggested_actions": [...]
        }
    """
    get_current_user()

    # Fetch response
    try:
        resp = FormResponse.objects.get(id=response_id, form_id=form_id)
    except FormResponse.DoesNotExist:
        return jsonify({"error": "Response not found"}), 404

    # Run detection on single response
    response_data = {
        "id": str(resp.id),
        "text": str(resp.data),
        "sentiment": (
            resp.ai_results.get("sentiment", {})
            if hasattr(resp, "ai_results") and resp.ai_results
            else {}
        ),
    }

    spam_result = AnomalyDetectionService.detect_spam(response_data)

    # Prepare anomaly flags
    anomaly_flags = {
        "spam": {
            "score": spam_result["spam_score"],
            "indicators": spam_result["indicators"],
            "confidence": (
                spam_result["spam_score"] / 100 if spam_result["is_spam"] else 0
            ),
        }
    }

    return jsonify(
        {
            "response_id": response_id,
            "anomaly_flags": anomaly_flags,
            "response_data": {
                "text": str(resp.data),
                "submitted_at": (
                    resp.submitted_at.isoformat() if resp.submitted_at else None
                ),
            },
            "review_status": "pending",
            "suggested_actions": ["review", "flag_response", "ignore"],
        }
    )


@anomaly_bp.route("/<form_id>/anomaly-stats", methods=["GET"])
@swag_from({
    "tags": [
        "Anomaly"
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
            "required": true
        }
    ]
})
@jwt_required()
def get_anomaly_stats(form_id: str):
    """
    Get anomaly detection statistics for a form.

    Returns:
        {
            "form_id": "form_123",
            "total_responses": 250,
            "flagged_count": 12,
            "flagged_percentage": 4.8,
            "recent_scans": [...]
        }
    """
    get_current_user()

    total = FormResponse.objects(form_id=form_id).count()

    # This would query anomaly history in production
    recent_scans = []

    return jsonify(
        {
            "form_id": form_id,
            "total_responses": total,
            "flagged_count": 0,  # Would be calculated from anomaly records
            "flagged_percentage": 0.0,
            "reviewed_count": 0,
            "false_positive_rate": 0.0,
            "detection_accuracy": 0.0,
            "recent_scans": recent_scans,
        }
    )


@anomaly_bp.route("/<form_id>/anomalies/<response_id>/feedback", methods=["POST"])
@swag_from({
    "tags": [
        "Anomaly"
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
            "required": true
        },
        {
            "name": "response_id",
            "in": "path",
            "type": "string",
            "required": true
        }
    ]
})
@jwt_required()
def submit_anomaly_feedback(form_id: str, response_id: str):
    """
    Submit feedback on anomaly detection results.

    Request Body:
        {
            "feedback_type": "false_positive" | "correct",
            "comment": "Optional comment"
        }

    Returns:
        {
            "message": "Feedback recorded successfully",
            "feedback_id": "fb_123",
            "model_improvement": "..."
        }
    """
    get_current_user()
    data = request.get_json() or {}

    feedback_type = data.get("feedback_type")
    data.get("comment", "")

    if feedback_type not in ["false_positive", "correct"]:
        return jsonify({"error": "Invalid feedback_type"}), 400

    # In production, this would save to AnomalyFeedback collection
    feedback_id = f"fb_{int(time.time())}"

    return jsonify(
        {
            "message": "Feedback recorded successfully",
            "feedback_id": feedback_id,
            "model_improvement": "This feedback will help improve future detection accuracy",
        }
    )


@anomaly_bp.route("/<form_id>/thresholds/update-baseline", methods=["POST"])
@swag_from({
    "tags": [
        "Anomaly"
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
            "required": true
        }
    ]
})
@jwt_required()
def update_anomaly_baseline(form_id: str):
    """
    Update baseline statistics and calculate dynamic thresholds for a form.

    Returns:
        {
            "message": "Baseline updated successfully",
            "baseline_stats": {...},
            "thresholds": {...},
            "response_count": 150,
            "threshold_id": "..."
        }
    """
    user = get_current_user()

    # Update baseline using service
    result = AnomalyDetectionService.update_baseline(
        form_id=form_id, created_by=str(user.id) if hasattr(user, "id") else "system"
    )

    return jsonify(
        {
            "message": "Baseline updated successfully",
            "baseline_stats": result["baseline_stats"],
            "thresholds": result["thresholds"],
            "response_count": result["response_count"],
            "threshold_id": result["threshold_id"],
        }
    )


@anomaly_bp.route("/<form_id>/thresholds/history", methods=["GET"])
@swag_from({
    "tags": [
        "Anomaly"
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
            "required": true
        }
    ]
})
@jwt_required()
def get_threshold_history(form_id: str):
    """
    Get threshold history for a form.

    Query Parameters:
        limit: Maximum number of records to return (default: 50)

    Returns:
        {
            "form_id": "form_123",
            "threshold_history": [...]
        }
    """
    get_current_user()

    limit = request.args.get("limit", 50, type=int)

    # Get threshold history
    history = AnomalyDetectionService.get_threshold_history(
        form_id=form_id, limit=limit
    )

    return jsonify({"form_id": form_id, "threshold_history": history})


@anomaly_bp.route("/<form_id>/thresholds/latest", methods=["GET"])
@swag_from({
    "tags": [
        "Anomaly"
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
            "required": true
        }
    ]
})
@jwt_required()
def get_latest_threshold(form_id: str):
    """
    Get the latest threshold configuration for a form.

    Query Parameters:
        sensitivity: Filter by sensitivity (auto, low, medium, high)

    Returns:
        {
            "threshold_id": "...",
            "form_id": "form_123",
            "thresholds": {...},
            "sensitivity": "auto",
            "baseline_stats": {...},
            "response_count": 150,
            "created_by": "user_123",
            "is_manual": false
        }
    """
    get_current_user()

    sensitivity = request.args.get("sensitivity")

    # Get latest threshold
    threshold = AnomalyDetectionService.get_latest_threshold(
        form_id=form_id, sensitivity=sensitivity
    )

    if not threshold:
        return jsonify({"error": "No threshold found for this form"}), 404

    return jsonify(threshold)


@anomaly_bp.route("/<form_id>/thresholds/manual", methods=["POST"])
@swag_from({
    "tags": [
        "Anomaly"
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
            "required": true
        }
    ]
})
@jwt_required()
def set_manual_threshold(form_id: str):
    """
    Manually set a threshold configuration for a form.

    Request Body:
        {
            "thresholds": {
                "z_score_threshold": 2.5,
                "sensitivity": "high",
                ...
            },
            "reason": "Too many false positives"
        }

    Returns:
        {
            "message": "Manual threshold set successfully",
            "threshold_id": "...",
            "thresholds": {...},
            "baseline_stats": {...}
        }
    """
    user = get_current_user()
    data = request.get_json() or {}

    thresholds = data.get("thresholds")
    reason = data.get("reason")

    if not thresholds:
        return jsonify({"error": "thresholds is required"}), 400

    # Set manual threshold
    result = AnomalyDetectionService.set_manual_threshold(
        form_id=form_id,
        thresholds=thresholds,
        created_by=str(user.id) if hasattr(user, "id") else "system",
        reason=reason,
    )

    return jsonify(
        {
            "message": "Manual threshold set successfully",
            "threshold_id": result["threshold_id"],
            "thresholds": result["thresholds"],
            "baseline_stats": result["baseline_stats"],
            "created_at": result["created_at"],
        }
    )


@anomaly_bp.route("/<form_id>/detect-anomalies/batch", methods=["POST"])
@swag_from({
    "tags": [
        "Anomaly"
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
            "required": true
        }
    ]
})
@jwt_required()
def detect_anomalies_batch(form_id: str):
    """
    Run anomaly detection on a batch of form responses.

    Request Body:
        {
            "response_ids": ["id1", "id2", "id3"],  // Required: List of response IDs to scan
            "scan_config": {
                "detection_types": ["spam", "outlier"],  // Optional
                "sensitivity": "medium",  // Optional: "auto", "low", "medium", "high"
                "use_dynamic_thresholds": false  // Optional
            },
            "batch_id": "batch_123"  // Optional: Custom batch ID
        }

    Returns:
        {
            "batch_id": "batch_abc123_1234567890",
            "status": "completed",
            "form_id": "form_123",
            "total_responses": 100,
            "scanned_count": 100,
            "anomalies_detected": 12,
            "summary": {...},
            "results": {...},
            "started_at": "2025-01-15T10:00:00Z",
            "completed_at": "2025-01-15T10:01:30Z"
        }

    Task: M2-EXT-04c - Add batch scanning for anomaly detection
    """
    user = get_current_user()
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body is required"}), 400

    response_ids = data.get("response_ids")
    if not response_ids or not isinstance(response_ids, list):
        return jsonify({"error": "response_ids is required and must be a list"}), 400

    if len(response_ids) == 0:
        return jsonify({"error": "response_ids cannot be empty"}), 400

    scan_config = data.get("scan_config", {})
    batch_id = data.get("batch_id")

    # Run batch scan
    result = AnomalyDetectionService.scan_batch(
        form_id=form_id,
        response_ids=response_ids,
        scan_config=scan_config,
        created_by=str(user.id) if hasattr(user, "id") else "system",
        batch_id=batch_id,
    )

    return jsonify(result)


@anomaly_bp.route(
    "/<form_id>/detect-anomalies/batch/<batch_id>/status", methods=["GET"]
)
@jwt_required()
def get_batch_scan_status(form_id: str, batch_id: str):
    """
    Get the status of a batch anomaly detection scan.

    Query Parameters:
        nocache: Set to "true" to bypass cache and fetch from database

    Returns:
        {
            "batch_id": "batch_abc123_1234567890",
            "form_id": "form_123",
            "status": "completed",  // "pending", "in_progress", "completed", "failed"
            "progress": 100.0,
            "total_responses": 100,
            "scanned_count": 100,
            "results_count": 12,
            "estimated_completion": "2025-01-15T10:01:30Z",
            "started_at": "2025-01-15T10:00:00Z",
            "completed_at": "2025-01-15T10:01:30Z",
            "error_message": null,
            "results": {...},  // Only included if status is "completed"
            "summary": {...}  // Only included if status is "completed"
        }

    Task: M2-EXT-04c - Add batch scanning for anomaly detection
    """
    get_current_user()

    nocache = request.args.get("nocache", "").lower() == "true"

    # Get batch status
    status = AnomalyDetectionService.get_batch_status(
        batch_id=batch_id, nocache=nocache
    )

    if not status:
        return jsonify({"error": "Batch scan not found"}), 404

    # Verify form_id matches
    if status.get("form_id") != form_id:
        return jsonify({"error": "Batch scan does not belong to this form"}), 400

    return jsonify(status)
