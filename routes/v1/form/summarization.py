from . import form_bp
from flasgger import swag_from
"""
Summarization Routes

API endpoints for automated response summarization.

Task: T-M2-03 - Automated Summarization
Task: M2-EXT-03c - Add summary comparison across time periods
"""

from flask import (
    Blueprint,
    request,
    jsonify,
    current_app,
    Response,
    stream_with_context,
)
from datetime import datetime, timedelta
import time
import json

from models import FormResponse, SummarySnapshot
from services.summarization_service import SummarizationService
from services.ollama_service import OllamaService
from flask_jwt_extended import jwt_required
from routes.v1.form.helper import get_current_user

summarization_bp = Blueprint("summarization", __name__, url_prefix="/api/v1/ai/forms")


@summarization_bp.route("/<form_id>/summarize", methods=["POST"])
@swag_from({
    "tags": [
        "Summarization"
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
def summarize(form_id: str):
    """
    Generate summary from form responses.

    Request Body:
        {
            "response_ids": [],
            "strategy": "hybrid",
            "format": "bullet_points",
            "config": {},
            "max_points": 5,
            "detail_level": "standard",
            "include_examples": True,
            "fallback_models": ["llama3.1", "mistral:7b", "gemma:2b"],
            "save_snapshot": True
        }
    """
    user = get_current_user()
    data = request.get_json() or {}

    response_ids = data.get("response_ids", [])
    strategy = data.get("strategy", "hybrid")
    format_type = data.get("format", "bullet_points")
    config = data.get("config", {})
    max_points = data.get("max_points", None)
    detail_level = data.get("detail_level", "standard")
    include_examples = data.get("include_examples", True)
    data.get("fallback_models", None)
    save_snapshot = data.get(
        "save_snapshot", True
    )  # Default to True for automatic snapshot creation

    start_time = time.time()

    if response_ids:
        responses = FormResponse.objects(id__in=response_ids, form_id=form_id)
    else:
        responses = FormResponse.objects(form_id=form_id).limit(200)

    response_texts = []
    period_start = None
    period_end = None

    for resp in responses:
        resp_data = {
            "id": str(resp.id),
            "text": str(resp.data),
            "sentiment": (
                resp.ai_results.get("sentiment", {})
                if hasattr(resp, "ai_results")
                else {}
            ),
        }
        response_texts.append(resp_data)

        # Track period range for snapshot
        if hasattr(resp, "submitted_at") and resp.submitted_at:
            if period_start is None or resp.submitted_at < period_start:
                period_start = resp.submitted_at
            if period_end is None or resp.submitted_at > period_end:
                period_end = resp.submitted_at

    summary = SummarizationService.hybrid_summarize(
        response_texts,
        strategy=strategy,
        format_type=format_type,
        config=config,
        max_points=max_points,
        detail_level=detail_level,
        include_examples=include_examples,
    )

    processing_time = int((time.time() - start_time) * 1000)

    # Automatically create snapshot if enabled
    snapshot_id = None
    if save_snapshot and len(response_texts) > 0:
        try:
            # Use current timestamp as period_end if not found
            if period_end is None:
                period_end = datetime.utcnow()
            if period_start is None:
                period_start = period_end - timedelta(
                    days=30
                )  # Default to last 30 days

            # Generate period label
            period_label = f"{period_start.strftime('%Y-%m-%d')} to {period_end.strftime('%Y-%m-%d')}"

            snapshot_id = SummarizationService.save_summary_snapshot(
                form_id=form_id,
                summary_data=summary,
                period_start=period_start,
                period_end=period_end,
                period_label=period_label,
                created_by=str(user.id) if hasattr(user, "id") else "system",
                strategy=strategy,
                response_count=len(response_texts),
            )
        except Exception as e:
            current_app.logger.warning(f"Failed to create snapshot: {str(e)}")

    result = {
        "form_id": form_id,
        "responses_analyzed": len(response_texts),
        "strategy_used": strategy,
        "summary": summary,
        "metadata": {
            "processing_time_ms": processing_time,
            "model_used": (
                OllamaService.get_default_model()
                if strategy != "extractive"
                else "tfidf"
            ),
            "cached": False,
        },
    }

    # Include snapshot ID if created
    if snapshot_id:
        result["metadata"]["snapshot_id"] = snapshot_id
        result["metadata"]["snapshot_created"] = True

    return jsonify(result)


@summarization_bp.route("/<form_id>/summarize/stream", methods=["POST"])
@swag_from({
    "tags": [
        "Summarization"
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
def summarize_stream(form_id: str):
    """
    Generate summary from form responses with streaming response.

    Request Body:
        {
            "response_ids": [],
            "strategy": "hybrid",
            "format": "bullet_points",
            "config": {},
            "max_points": 5,
            "detail_level": "standard",
            "include_examples": True,
            "fallback_models": ["llama3.1", "mistral:7b", "gemma:2b"]
        }

    Returns Server-Sent Events (SSE) stream:
        data: { "content": "partial text", "done": False }
        ...
        data: { "content": "", "done": True, "model_used": "llama3.2", "responses_analyzed": 150 }
    """
    get_current_user()
    data = request.get_json() or {}

    response_ids = data.get("response_ids", [])
    strategy = data.get("strategy", "hybrid")
    format_type = data.get("format", "bullet_points")
    config = data.get("config", {})
    max_points = data.get("max_points", None)
    detail_level = data.get("detail_level", "standard")
    include_examples = data.get("include_examples", True)
    fallback_models = data.get("fallback_models", None)

    def generate():
        try:
            start_time = time.time()

            # Send initial status
            yield f"data: {json.dumps({'content': 'Fetching responses...', 'done': False, 'stage': 'fetching'})}\n\n"

            if response_ids:
                responses = FormResponse.objects(id__in=response_ids, form_id=form_id)
            else:
                responses = FormResponse.objects(form_id=form_id).limit(200)

            response_texts = []
            for resp in responses:
                resp_data = {
                    "id": str(resp.id),
                    "text": str(resp.data),
                    "sentiment": (
                        resp.ai_results.get("sentiment", {})
                        if hasattr(resp, "ai_results")
                        else {}
                    ),
                }
                response_texts.append(resp_data)

            yield f"data: {json.dumps({'content': f'Analyzing {len(response_texts)} responses...', 'done': False, 'stage': 'analyzing'})}\n\n"

            # Use streaming chat for abstractive summarization
            if strategy in ["abstractive", "hybrid"]:
                # Build prompt for summarization
                prompt = f"Summarize the following form responses in {format_type} format:\n\n"
                for i, resp in enumerate(
                    response_texts[:50]
                ):  # Limit to 50 for context
                    prompt += f"Response {i+1}: {resp['text']}\n\n"

                system_prompt = f"You are a helpful assistant that summarizes form responses. Use {format_type} format."

                # Stream the summary
                model_used = None
                fallback_used = False
                fallback_model = None

                try:
                    if fallback_models:
                        for chunk in OllamaService.chat_stream_with_fallback(
                            prompt=prompt,
                            system_prompt=system_prompt,
                            temperature=0.7,
                            fallback_models=fallback_models,
                        ):
                            if chunk.get("done"):
                                model_used = chunk.get("model_used")
                                fallback_used = chunk.get("fallback_used", False)
                                fallback_model = chunk.get("fallback_model")
                            else:
                                yield f"data: {json.dumps({'content': chunk.get('content', ''), 'done': False})}\n\n"
                    else:
                        for chunk in OllamaService.chat_stream(
                            prompt=prompt, system_prompt=system_prompt, temperature=0.7
                        ):
                            if chunk.get("done"):
                                model_used = chunk.get("model_used")
                            else:
                                yield f"data: {json.dumps({'content': chunk.get('content', ''), 'done': False})}\n\n"

                    processing_time = int((time.time() - start_time) * 1000)

                    # Send final chunk
                    yield f"data: {json.dumps({'content': '', 'done': True, 'model_used': model_used or OllamaService.get_default_model(), 'fallback_used': fallback_used, 'fallback_model': fallback_model, 'responses_analyzed': len(response_texts), 'processing_time_ms': processing_time})}\n\n"

                except (ConnectionError, TimeoutError):
                    # Fallback to non-streaming summarization
                    summary = SummarizationService.hybrid_summarize(
                        response_texts,
                        strategy=strategy,
                        format_type=format_type,
                        config=config,
                        max_points=max_points,
                        detail_level=detail_level,
                        include_examples=include_examples,
                    )
                    processing_time = int((time.time() - start_time) * 1000)

                    yield f"data: {json.dumps({'content': summary, 'done': True, 'model_used': 'fallback', 'responses_analyzed': len(response_texts), 'processing_time_ms': processing_time})}\n\n"
            else:
                # Extractive summarization - return as single chunk
                summary = SummarizationService.hybrid_summarize(
                    response_texts,
                    strategy=strategy,
                    format_type=format_type,
                    config=config,
                    max_points=max_points,
                    detail_level=detail_level,
                    include_examples=include_examples,
                )
                processing_time = int((time.time() - start_time) * 1000)

                yield f"data: {json.dumps({'content': summary, 'done': True, 'model_used': 'tfidf', 'responses_analyzed': len(response_texts), 'processing_time_ms': processing_time})}\n\n"

        except Exception as e:
            error_data = {
                "content": "",
                "done": True,
                "error": str(e),
                "message": "Failed to generate summary",
            }
            yield f"data: {json.dumps(error_data)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@summarization_bp.route("/<form_id>/executive-summary", methods=["POST"])
@swag_from({
    "tags": [
        "Summarization"
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
def executive_summary(form_id: str):
    """
    Generate executive summary for leadership.

    Request Body:
        {
            "response_ids": [],
            "audience": "leadership",
            "tone": "formal",
            "max_points": 5,
            "detail_level": "standard",
            "include_examples": True,
            "fallback_models": ["llama3.1", "mistral:7b", "gemma:2b"]
        }
    """
    get_current_user()
    data = request.get_json() or {}

    response_ids = data.get("response_ids", [])
    audience = data.get("audience", "leadership")
    tone = data.get("tone", "formal")
    max_points = data.get("max_points", None)
    detail_level = data.get("detail_level", "standard")
    include_examples = data.get("include_examples", True)
    data.get("fallback_models", None)

    if response_ids:
        responses = FormResponse.objects(id__in=response_ids, form_id=form_id)
    else:
        responses = FormResponse.objects(form_id=form_id).limit(200)

    response_texts = [str(resp.data) for resp in responses]

    exec_summary = SummarizationService.generate_executive_summary(
        response_texts,
        audience=audience,
        tone=tone,
        max_points=max_points,
        detail_level=detail_level,
        include_examples=include_examples,
    )

    return jsonify(
        {
            "form_id": form_id,
            "executive_summary": exec_summary,
            "generated_at": datetime.utcnow().isoformat(),
        }
    )


@summarization_bp.route("/<form_id>/theme-summary", methods=["POST"])
@swag_from({
    "tags": [
        "Summarization"
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
def theme_summary(form_id: str):
    """
    Generate theme-based summary.

    Request Body:
        {
            "themes": ["delivery", "product", "support", "pricing"],
            "include_quote_examples": True,
            "sentiment_per_theme": True,
            "max_points": 5,
            "detail_level": "standard",
            "include_examples": True,
            "fallback_models": ["llama3.1", "mistral:7b", "gemma:2b"]
        }
    """
    get_current_user()
    data = request.get_json() or {}

    data.get("themes", ["delivery", "product", "support", "pricing"])
    data.get("include_quote_examples", True)
    data.get("sentiment_per_theme", True)
    max_points = data.get("max_points", None)
    detail_level = data.get("detail_level", "standard")
    include_examples = data.get("include_examples", True)
    data.get("fallback_models", None)

    responses = FormResponse.objects(form_id=form_id).limit(200)

    response_texts = [str(resp.data) for resp in responses]

    theme_analysis = SummarizationService._analyze_themes(
        response_texts, detail_level, include_examples
    )

    theme_summary = {}
    for theme, theme_data in theme_analysis.items():
        summary_item = {
            "sentiment": theme_data.get("sentiment", "mixed"),
            "mention_count": theme_data.get("mentions", 0),
            "summary": f"Analysis of {theme_data.get('mentions', 0)} responses related to {theme}.",
        }
        # Include examples if available
        if "examples" in theme_data:
            summary_item["examples"] = theme_data["examples"]
        theme_summary[theme] = summary_item

    # Track custom configuration
    custom_config = {
        "max_points": max_points if max_points else 5,
        "detail_level": detail_level,
        "include_examples": include_examples,
        "themes_analyzed": list(theme_summary.keys()),
    }

    return jsonify(
        {
            "form_id": form_id,
            "theme_summary": theme_summary,
            "custom_config": custom_config,
            "themes_generated": len(theme_summary),
        }
    )


@summarization_bp.route("/<form_id>/summary-comparison", methods=["GET"])
@swag_from({
    "tags": [
        "Summarization"
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
def summary_comparison(form_id: str):
    """
    Compare summaries across multiple time periods.

    Query Parameters:
        - period_ranges: JSON array of period ranges with 'start', 'end', and optional 'label'
          Example: [{"start": "2025-01-01T00:00:00Z", "end": "2025-01-31T23:59:59Z", "label": "January 2025"},
                    {"start": "2025-02-01T00:00:00Z", "end": "2025-02-28T23:59:59Z", "label": "February 2025"}]
        - preset: Optional preset period comparison (last_7_days, last_30_days, last_90_days, month_over_month)
          If provided, period_ranges is ignored

    Returns:
        Comparison data with trend analysis across periods
    """
    get_current_user()

    # Parse period ranges from query
    period_ranges_json = request.args.get("period_ranges")
    preset = request.args.get("preset")

    period_ranges = []

    if preset:
        # Generate preset period ranges
        now = datetime.utcnow()

        if preset == "last_7_days":
            period_ranges = [
                {
                    "start": (now - timedelta(days=14)).isoformat() + "Z",
                    "end": (now - timedelta(days=7)).isoformat() + "Z",
                    "label": "Previous 7 days",
                },
                {
                    "start": (now - timedelta(days=7)).isoformat() + "Z",
                    "end": now.isoformat() + "Z",
                    "label": "Last 7 days",
                },
            ]
        elif preset == "last_30_days":
            period_ranges = [
                {
                    "start": (now - timedelta(days=60)).isoformat() + "Z",
                    "end": (now - timedelta(days=30)).isoformat() + "Z",
                    "label": "Previous 30 days",
                },
                {
                    "start": (now - timedelta(days=30)).isoformat() + "Z",
                    "end": now.isoformat() + "Z",
                    "label": "Last 30 days",
                },
            ]
        elif preset == "last_90_days":
            period_ranges = [
                {
                    "start": (now - timedelta(days=180)).isoformat() + "Z",
                    "end": (now - timedelta(days=90)).isoformat() + "Z",
                    "label": "Previous 90 days",
                },
                {
                    "start": (now - timedelta(days=90)).isoformat() + "Z",
                    "end": now.isoformat() + "Z",
                    "label": "Last 90 days",
                },
            ]
        elif preset == "month_over_month":
            # Compare last month with current month
            current_month_start = now.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
            last_month_end = current_month_start - timedelta(seconds=1)

            period_ranges = [
                {
                    "start": last_month_start.isoformat() + "Z",
                    "end": last_month_end.isoformat() + "Z",
                    "label": last_month_start.strftime("%B %Y"),
                },
                {
                    "start": current_month_start.isoformat() + "Z",
                    "end": now.isoformat() + "Z",
                    "label": current_month_start.strftime("%B %Y"),
                },
            ]
    elif period_ranges_json:
        try:
            period_ranges = json.loads(period_ranges_json)
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON in period_ranges parameter"}), 400

    if not period_ranges:
        return (
            jsonify(
                {
                    "error": "Either period_ranges or preset parameter is required",
                    "available_presets": [
                        "last_7_days",
                        "last_30_days",
                        "last_90_days",
                        "month_over_month",
                    ],
                }
            ),
            400,
        )

    # Perform comparison
    comparison = SummarizationService.compare_summaries(form_id, period_ranges)

    return jsonify(comparison)


@summarization_bp.route("/<form_id>/summary-trends", methods=["GET"])
@swag_from({
    "tags": [
        "Summarization"
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
def summary_trends(form_id: str):
    """
    Get trend data for a specific metric over time.

    Query Parameters:
        - metric: Metric to track (sentiment, theme, response_count). Default: sentiment
        - limit: Maximum number of snapshots to include. Default: 10

    Returns:
        Trend data for the specified metric
    """
    get_current_user()

    metric = request.args.get("metric", "sentiment")
    limit = int(request.args.get("limit", 10))

    # Validate metric
    valid_metrics = ["sentiment", "theme", "response_count"]
    if metric not in valid_metrics:
        return (
            jsonify(
                {"error": f'Invalid metric. Valid options: {", ".join(valid_metrics)}'}
            ),
            400,
        )

    # Validate limit
    if limit < 1 or limit > 100:
        return jsonify({"error": "Limit must be between 1 and 100"}), 400

    # Get trend data
    trends = SummarizationService.get_summary_trends(form_id, metric, limit)

    return jsonify(trends)


@summarization_bp.route("/<form_id>/summary-snapshots", methods=["GET"])
@swag_from({
    "tags": [
        "Summarization"
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
def list_summary_snapshots(form_id: str):
    """
    List all summary snapshots for a form.

    Query Parameters:
        - limit: Maximum number of snapshots to return. Default: 20
        - offset: Number of snapshots to skip. Default: 0

    Returns:
        List of summary snapshots
    """
    get_current_user()

    limit = int(request.args.get("limit", 20))
    offset = int(request.args.get("offset", 0))

    # Validate parameters
    if limit < 1 or limit > 100:
        return jsonify({"error": "Limit must be between 1 and 100"}), 400

    if offset < 0:
        return jsonify({"error": "Offset must be non-negative"}), 400

    # Get snapshots
    snapshots = (
        SummarySnapshot.objects(form_id=form_id)
        .order_by("-timestamp")
        .skip(offset)
        .limit(limit)
    )

    # Get total count
    total = SummarySnapshot.objects(form_id=form_id).count()

    # Format response
    snapshot_list = []
    for snapshot in snapshots:
        snapshot_list.append(
            {
                "id": str(snapshot.id),
                "form_id": str(snapshot.form_id),
                "timestamp": snapshot.timestamp.isoformat(),
                "period_start": snapshot.period_start.isoformat(),
                "period_end": snapshot.period_end.isoformat(),
                "period_label": snapshot.period_label,
                "response_count": snapshot.response_count,
                "strategy_used": snapshot.strategy_used,
                "created_by": snapshot.created_by,
                "created_at": snapshot.created_at.isoformat(),
            }
        )

    return jsonify(
        {
            "form_id": form_id,
            "total": total,
            "offset": offset,
            "limit": limit,
            "snapshots": snapshot_list,
        }
    )
