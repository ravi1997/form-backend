from . import form_bp
"""
NLP Search Routes

Natural language search endpoints for form responses.
Provides semantic search, sentiment filtering, and query parsing.

Task: T-M2-02 - NLP Search Enhancement
"""

from flask import (
    Blueprint,
    request,
    jsonify,
    current_app,
    Response,
    stream_with_context,
)
from datetime import datetime
import time
import json

from models import FormResponse
from services.nlp_service import NLPSearchService
from services.ollama_service import OllamaService
from flask_jwt_extended import jwt_required
from routes.v1.form.helper import get_current_user
from utils.redis_client import redis_client

nlp_search_bp = Blueprint("nlp_search", __name__, url_prefix="/api/v1/ai/forms")


@nlp_search_bp.route("/<form_id>/nlp-search", methods=["POST"])
@jwt_required()
def nlp_search(form_id: str):
    """
    Natural language search across form responses with advanced filtering.

    Request Body:
        {
            "query": "Show me all users who were unhappy with delivery",
            "options": {
                "max_results": 50,
                "include_sentiment": true,
                "semantic_search": true,
                "cache_results": true,
                "fallback_models": ["llama3.1", "mistral:7b", "gemma:2b"]
            },
            "filters": {
                "date_range": {
                    "start_date": "2025-01-01T00:00:00Z",
                    "end_date": "2025-03-31T23:59:59Z"
                },
                "field_filters": [
                    {"field": "q_rating", "operator": ">", "value": "3"},
                    {"field": "q_satisfaction", "operator": "contains", "value": "positive"}
                ],
                "submitted_by": ["user1", "user2"],
                "source": ["web", "mobile"]
            },
            "filter_mode": "and"  # "and" or "or"
        }

    Returns:
        {
            "query": "Show me all users who were unhappy with delivery",
            "parsed_intent": {
                "sentiment_filter": "negative",
                "topic": "delivery",
                "entities": ["delivery", "users"],
                "date_range": {...},
                "field_filters": [...]
            },
            "results_count": 15,
            "results": [...],
            "processing_time_ms": 245,
            "cached": false,
            "filters_applied": {...}
        }
    """
    user = get_current_user()
    data = request.get_json()

    if not data or "query" not in data:
        return jsonify({"error": "Query is required"}), 400

    query = data["query"]
    options = data.get("options", {})
    filters = data.get("filters", {})
    filter_mode = data.get("filter_mode", "and")

    max_results = options.get("max_results", 50)
    include_sentiment = options.get("include_sentiment", True)
    use_semantic = options.get("semantic_search", True)
    use_cache = options.get("cache_results", True)
    options.get("fallback_models", None)

    # Validate filter_mode
    if filter_mode not in ["and", "or"]:
        return jsonify({"error": "filter_mode must be 'and' or 'or'"}), 400

    start_time = time.time()

    # Validate date range if provided
    if filters.get("date_range"):
        is_valid, error_msg = NLPSearchService.validate_date_range(
            filters["date_range"]
        )
        if not is_valid:
            return jsonify({"error": f"Invalid date range: {error_msg}"}), 400

    # Validate field names if form schema is available
    if filters.get("field_filters"):
        try:
            from models import Form

            form = Form.objects.get(id=form_id)
            form_schema = form.to_mongo().to_dict()
            is_valid, invalid_fields = NLPSearchService.validate_field_names(
                filters["field_filters"], form_schema
            )
            if not is_valid:
                return (
                    jsonify(
                        {
                            "error": "Invalid field names",
                            "invalid_fields": invalid_fields,
                        }
                    ),
                    400,
                )
        except Exception:
            # If form not found or schema unavailable, skip validation
            pass

    # Check cache first
    cache_key = NLPSearchService.generate_cache_key(form_id, query, "nlp")
    if use_cache:
        cached_result = redis_client.get_with_lock(cache_key)
        if cached_result:
            return jsonify({**cached_result, "cached": True})

    # Parse the query
    parsed = NLPSearchService.parse_query(query)
    entities = NLPSearchService.extract_entities(query)
    parsed["entities"] = entities

    # Merge filters from query with explicit filters
    # Query-parsed filters take precedence for date_range and field_filters
    if parsed.get("date_range"):
        filters["date_range"] = parsed["date_range"]
    if parsed.get("field_filters"):
        # Merge field filters - append to existing ones
        existing_field_filters = filters.get("field_filters", [])
        filters["field_filters"] = existing_field_filters + parsed["field_filters"]

    # Build MongoDB query
    mongo_query = NLPSearchService.build_mongo_query(parsed)
    mongo_query["form_id"] = form_id

    # Fetch responses (simplified - would need proper pagination in production)
    responses = FormResponse.objects(**mongo_query).limit(max_results * 2)

    # Prepare documents for search
    documents = []
    for resp in responses:
        resp_data = {
            "response_id": str(resp.id),
            "data": resp.data,
            "submitted_at": (
                resp.submitted_at.isoformat() if resp.submitted_at else None
            ),
            "submitted_by": resp.submitted_by,
            "metadata": resp.metadata or {},
        }

        # Include sentiment if available
        if include_sentiment and hasattr(resp, "ai_results") and resp.ai_results:
            resp_data["sentiment"] = resp.ai_results.get("sentiment", {})

        documents.append(resp_data)

    # Apply advanced filters if provided
    if filters:
        documents = NLPSearchService.filter_by_criteria(
            documents, filters, filter_mode=filter_mode
        )

    # Perform search
    if use_semantic:
        try:
            results = NLPSearchService.semantic_search(
                query, documents, similarity_threshold=0.7, max_results=max_results
            )
        except (ConnectionError, TimeoutError):
            # Fallback to keyword search
            results = NLPSearchService._keyword_search(query, documents, max_results)
    else:
        results = NLPSearchService._keyword_search(query, documents, max_results)

    processing_time = int((time.time() - start_time) * 1000)

    # Build response
    response = {
        "query": query,
        "parsed_intent": parsed,
        "results_count": len(results),
        "results": results[:max_results],
        "processing_time_ms": processing_time,
        "cached": False,
        "filters_applied": filters if filters else None,
        "filter_mode": filter_mode if filters else None,
    }

    # Cache results (1 hour TTL)
    if use_cache:
        redis_client.set_with_lock(cache_key, response, ttl=3600)
        response["cached"] = False  # Just cached

    # Save search to history (async, don't block response)
    try:
        search_type = "semantic" if use_semantic else "keyword"
        NLPSearchService.save_search(
            user_id=str(user.id),
            form_id=form_id,
            query=query,
            results_count=len(results),
            parsed_intent=parsed,
            search_type=search_type,
            cached=response.get("cached", False),
        )
    except Exception as e:
        # Log error but don't fail the request
        current_app.logger.warning(f"Failed to save search history: {e}")

    return jsonify(response)


@nlp_search_bp.route("/<form_id>/semantic-search", methods=["POST"])
@jwt_required()
def semantic_search(form_id: str):
    """
    Pure semantic search using Ollama embeddings with advanced filtering.

    Request Body:
        {
            "query": "What are the main complaints about product quality?",
            "similarity_threshold": 0.7,
            "max_results": 20,
            "fallback_models": ["llama3.1", "mistral:7b", "gemma:2b"],
            "date_range": {
                "start_date": "2025-01-01T00:00:00Z",
                "end_date": "2025-03-31T23:59:59Z"
            },
            "field_filters": [
                {"field": "q_rating", "operator": "<", "value": "3"}
            ],
            "submitted_by": ["user1", "user2"],
            "filter_mode": "and"
        }

    Returns:
        {
            "query": "What are the main complaints about product quality?",
            "embedding_model": "nomic-embed-text",
            "results_count": 8,
            "results": [...],
            "filters_applied": {...}
        }
    """
    user = get_current_user()
    data = request.get_json()

    if not data or "query" not in data:
        return jsonify({"error": "Query is required"}), 400

    query = data["query"]
    similarity_threshold = data.get("similarity_threshold", 0.7)
    max_results = data.get("max_results", 20)
    data.get("fallback_models", None)

    # Build filters object
    filters = {}

    # Date range filter
    if "date_range" in data:
        date_range = data["date_range"]
        is_valid, error_msg = NLPSearchService.validate_date_range(date_range)
        if not is_valid:
            return jsonify({"error": f"Invalid date range: {error_msg}"}), 400
        filters["date_range"] = date_range

    # Field filters
    if "field_filters" in data:
        field_filters = data["field_filters"]
        # Validate field names if form schema is available
        try:
            from models import Form

            form = Form.objects.get(id=form_id)
            form_schema = form.to_mongo().to_dict()
            is_valid, invalid_fields = NLPSearchService.validate_field_names(
                field_filters, form_schema
            )
            if not is_valid:
                return (
                    jsonify(
                        {
                            "error": "Invalid field names",
                            "invalid_fields": invalid_fields,
                        }
                    ),
                    400,
                )
        except Exception:
            # If form not found or schema unavailable, skip validation
            pass
        filters["field_filters"] = field_filters

    # Submitted by filter
    if "submitted_by" in data:
        filters["submitted_by"] = data["submitted_by"]

    # Source filter
    if "source" in data:
        filters["source"] = data["source"]

    filter_mode = data.get("filter_mode", "and")

    # Validate filter_mode
    if filter_mode not in ["and", "or"]:
        return jsonify({"error": "filter_mode must be 'and' or 'or'"}), 400

    # Fetch all responses for this form
    responses = FormResponse.objects(form_id=form_id).limit(500)

    # Prepare documents
    documents = [
        {
            "response_id": str(resp.id),
            "text": str(resp.data),
            "submitted_at": (
                resp.submitted_at.isoformat() if resp.submitted_at else None
            ),
            "submitted_by": resp.submitted_by,
            "metadata": resp.metadata or {},
        }
        for resp in responses
    ]

    # Apply filters if provided
    if filters:
        documents = NLPSearchService.filter_by_criteria(
            documents, filters, filter_mode=filter_mode
        )

    # Perform semantic search
    try:
        results = NLPSearchService.semantic_search(
            query,
            documents,
            similarity_threshold=similarity_threshold,
            max_results=max_results,
        )

        # Save search to history (async, don't block response)
        try:
            NLPSearchService.save_search(
                user_id=str(user.id),
                form_id=form_id,
                query=query,
                results_count=len(results),
                parsed_intent=None,
                search_type="semantic",
                cached=False,
            )
        except Exception as e:
            # Log error but don't fail the request
            current_app.logger.warning(f"Failed to save search history: {e}")

        return jsonify(
            {
                "query": query,
                "embedding_model": OllamaService.get_embedding_model(),
                "results_count": len(results),
                "results": results,
                "filters_applied": filters if filters else None,
                "filter_mode": filter_mode if filters else None,
            }
        )

    except (ConnectionError, TimeoutError):
        return (
            jsonify(
                {
                    "error": "Ollama service is not available",
                    "message": "Ensure Ollama is running with embedding support",
                }
            ),
            503,
        )


@nlp_search_bp.route("/<form_id>/semantic-search/stream", methods=["POST"])
@jwt_required()
def semantic_search_stream(form_id: str):
    """
    Pure semantic search using Ollama embeddings with streaming response and advanced filtering.

    Request Body:
        {
            "query": "What are the main complaints about product quality?",
            "similarity_threshold": 0.7,
            "max_results": 20,
            "fallback_models": ["llama3.1", "mistral:7b", "gemma:2b"],
            "date_range": {
                "start_date": "2025-01-01T00:00:00Z",
                "end_date": "2025-03-31T23:59:59Z"
            },
            "field_filters": [
                {"field": "q_rating", "operator": "<", "value": "3"}
            ],
            "filter_mode": "and"
        }

    Returns Server-Sent Events (SSE) stream:
        data: { "content": "partial text", "done": false }
        ...
        data: { "content": "", "done": true, "model_used": "llama3.2", "results_count": 8 }
    """
    get_current_user()
    data = request.get_json()

    if not data or "query" not in data:
        return jsonify({"error": "Query is required"}), 400

    query = data["query"]
    similarity_threshold = data.get("similarity_threshold", 0.7)
    max_results = data.get("max_results", 20)
    data.get("fallback_models", None)

    # Build filters object
    filters = {}

    # Date range filter
    if "date_range" in data:
        date_range = data["date_range"]
        is_valid, error_msg = NLPSearchService.validate_date_range(date_range)
        if not is_valid:
            return jsonify({"error": f"Invalid date range: {error_msg}"}), 400
        filters["date_range"] = date_range

    # Field filters
    if "field_filters" in data:
        field_filters = data["field_filters"]
        # Validate field names if form schema is available
        try:
            from models import Form

            form = Form.objects.get(id=form_id)
            form_schema = form.to_mongo().to_dict()
            is_valid, invalid_fields = NLPSearchService.validate_field_names(
                field_filters, form_schema
            )
            if not is_valid:
                return (
                    jsonify(
                        {
                            "error": "Invalid field names",
                            "invalid_fields": invalid_fields,
                        }
                    ),
                    400,
                )
        except Exception:
            # If form not found or schema unavailable, skip validation
            pass
        filters["field_filters"] = field_filters

    # Submitted by filter
    if "submitted_by" in data:
        filters["submitted_by"] = data["submitted_by"]

    # Source filter
    if "source" in data:
        filters["source"] = data["source"]

    filter_mode = data.get("filter_mode", "and")

    # Validate filter_mode
    if filter_mode not in ["and", "or"]:
        return jsonify({"error": "filter_mode must be 'and' or 'or'"}), 400

    def generate():
        try:
            # Send initial status
            yield f"data: {json.dumps({'content': 'Fetching documents...', 'done': False, 'stage': 'fetching'})}\n\n"

            # Fetch all responses for this form
            responses = FormResponse.objects(form_id=form_id).limit(500)

            # Prepare documents
            documents = [
                {
                    "response_id": str(resp.id),
                    "text": str(resp.data),
                    "submitted_at": (
                        resp.submitted_at.isoformat() if resp.submitted_at else None
                    ),
                    "submitted_by": resp.submitted_by,
                    "metadata": resp.metadata or {},
                }
                for resp in responses
            ]

            # Apply filters if provided
            if filters:
                documents = NLPSearchService.filter_by_criteria(
                    documents, filters, filter_mode=filter_mode
                )

            yield f"data: {json.dumps({'content': f'Found {len(documents)} documents. Performing semantic search...', 'done': False, 'stage': 'searching'})}\n\n"

            # Perform semantic search
            results = NLPSearchService.semantic_search(
                query,
                documents,
                similarity_threshold=similarity_threshold,
                max_results=max_results,
            )

            # Send results as JSON
            results_data = {
                "query": query,
                "embedding_model": OllamaService.get_embedding_model(),
                "results_count": len(results),
                "results": results,
                "filters_applied": filters if filters else None,
                "filter_mode": filter_mode if filters else None,
            }

            # Send final chunk with results
            yield f"data: {json.dumps({'content': json.dumps(results_data), 'done': True, 'model_used': OllamaService.get_embedding_model(), 'results_count': len(results)})}\n\n"

        except (ConnectionError, TimeoutError):
            error_data = {
                "content": "",
                "done": True,
                "error": "Ollama service is not available",
                "message": "Ensure Ollama is running with embedding support",
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


@nlp_search_bp.route("/<form_id>/search-stats", methods=["GET"])
@jwt_required()
def search_stats(form_id: str):
    """
    Get search-related statistics for a form.

    Returns:
        {
            "total_responses": 250,
            "indexed_responses": 250,
            "ollama_available": true,
            "supported_query_types": ["sentiment", "topic", "semantic", "time"]
        }
    """
    get_current_user()

    total_responses = FormResponse.objects(form_id=form_id).count()

    # Check Ollama availability
    ollama_health = OllamaService.health_check()
    ollama_available = ollama_health.get("available", False)

    return jsonify(
        {
            "form_id": form_id,
            "total_responses": total_responses,
            "indexed_responses": total_responses,  # All responses indexed by default
            "ollama_available": ollama_available,
            "ollama_models": ollama_health.get("models", []),
            "supported_query_types": [
                "sentiment",
                "topic",
                "semantic",
                "keyword",
                "time_based",
            ],
            "cache_ttl_seconds": 3600,
        }
    )


@nlp_search_bp.route("/<form_id>/query-suggestions", methods=["GET"])
@jwt_required()
def query_suggestions(form_id: str):
    """
    Get query suggestions/autocomplete for a form.

    Provides intelligent suggestions based on:
    - Most common terms from existing responses
    - Form question labels and field names
    - Fuzzy matching for partial queries

    Query Parameters:
        q: Partial query string (required)
        limit: Maximum number of suggestions (optional, default: 10)

    Returns:
        {
            "form_id": "form123",
            "query": "del",
            "suggestions": [
                {"text": "delivery", "count": 98, "match_score": 0.92, "is_form_term": false},
                {"text": "delivered", "count": 45, "match_score": 0.88, "is_form_term": false},
                {"text": "delay", "count": 23, "match_score": 0.75, "is_form_term": true}
            ],
            "total_suggestions": 3
        }
    """
    get_current_user()

    # Get query parameter
    partial_query = request.args.get("q", "").strip()
    if not partial_query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    # Get limit parameter (max 50)
    try:
        limit = min(int(request.args.get("limit", 10)), 50)
    except (ValueError, TypeError):
        limit = 10

    # Get suggestions
    try:
        suggestions = NLPSearchService.get_query_suggestions(
            form_id=form_id, partial_query=partial_query, max_suggestions=limit
        )

        return jsonify(
            {
                "form_id": form_id,
                "query": partial_query,
                "suggestions": suggestions,
                "total_suggestions": len(suggestions),
            }
        )

    except Exception as e:
        current_app.logger.error(f"Query suggestions error: {str(e)}")
        return jsonify({"error": "Failed to get suggestions", "message": str(e)}), 500


@nlp_search_bp.route("/health", methods=["GET"])
def health_check():
    """
    Health check for NLP search service.

    Returns:
        {
            "status": "healthy",
            "ollama": {...},
            "nlp": {...}
        }
    """
    ollama_status = OllamaService.health_check()

    return jsonify(
        {
            "status": "healthy" if ollama_status.get("available") else "degraded",
            "ollama": ollama_status,
            "timestamp": datetime.utcnow().isoformat(),
        }
    )


# --- Search History Endpoints ---
# Task: M2-EXT-02b - Persist user search history


@nlp_search_bp.route("/<form_id>/search-history", methods=["GET"])
@jwt_required()
def get_search_history(form_id: str):
    """
    Get user's search history for a form.

    Query Parameters:
        limit: Maximum number of results (default: 50, max: 100)
        offset: Number of results to skip (default: 0)

    Returns:
        {
            "form_id": "form123",
            "user_id": "user456",
            "history": [
                {
                    "id": "search_id",
                    "query": "search text",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "results_count": 15,
                    "search_type": "nlp",
                    "cached": false
                }
            ],
            "total": 50,
            "limit": 50,
            "offset": 0
        }
    """
    user = get_current_user()

    # Get pagination parameters
    try:
        limit = min(int(request.args.get("limit", 50)), 100)
    except (ValueError, TypeError):
        limit = 50

    try:
        offset = max(int(request.args.get("offset", 0)), 0)
    except (ValueError, TypeError):
        offset = 0

    # Get search history
    try:
        history = NLPSearchService.get_user_search_history(
            user_id=str(user.id), form_id=form_id, limit=limit, offset=offset
        )

        # Get total count for pagination
        from models import SearchHistory

        total = SearchHistory.objects(user_id=str(user.id), form_id=form_id).count()

        return jsonify(
            {
                "form_id": form_id,
                "user_id": str(user.id),
                "history": history,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )

    except Exception as e:
        current_app.logger.error(f"Error fetching search history: {str(e)}")
        return (
            jsonify({"error": "Failed to fetch search history", "message": str(e)}),
            500,
        )


@nlp_search_bp.route("/<form_id>/search-history", methods=["POST"])
@jwt_required()
def save_search_history(form_id: str):
    """
    Save a search query to user's search history.

    Request Body:
        {
            "query": "search text",
            "results_count": 15,
            "parsed_intent": {...},
            "search_type": "nlp",
            "cached": false
        }

    Returns:
        {
            "id": "search_id",
            "query": "search text",
            "timestamp": "2024-01-15T10:30:00Z",
            "message": "Search saved successfully"
        }
    """
    user = get_current_user()
    data = request.get_json()

    if not data or "query" not in data:
        return jsonify({"error": "Query is required"}), 400

    query = data["query"]
    results_count = data.get("results_count", 0)
    parsed_intent = data.get("parsed_intent", {})
    search_type = data.get("search_type", "nlp")
    cached = data.get("cached", False)

    # Save search
    try:
        search_id = NLPSearchService.save_search(
            user_id=str(user.id),
            form_id=form_id,
            query=query,
            results_count=results_count,
            parsed_intent=parsed_intent,
            search_type=search_type,
            cached=cached,
        )

        if not search_id:
            return jsonify({"error": "Failed to save search"}), 500

        return (
            jsonify(
                {
                    "id": search_id,
                    "query": query,
                    "timestamp": datetime.utcnow().isoformat(),
                    "message": "Search saved successfully",
                }
            ),
            201,
        )

    except Exception as e:
        current_app.logger.error(f"Error saving search history: {str(e)}")
        return jsonify({"error": "Failed to save search", "message": str(e)}), 500


@nlp_search_bp.route("/<form_id>/search-history", methods=["DELETE"])
@jwt_required()
def clear_search_history(form_id: str):
    """
    Clear user's search history for a form.

    Query Parameters:
        all: If "true", clears all search history (not just for this form)

    Returns:
        {
            "deleted_count": 15,
            "message": "Search history cleared successfully"
        }
    """
    user = get_current_user()

    # Check if clearing all history
    clear_all = request.args.get("all", "").lower() == "true"

    try:
        if clear_all:
            # Clear all search history for the user
            deleted_count = NLPSearchService.clear_user_search_history(
                user_id=str(user.id), form_id=None
            )
        else:
            # Clear only for this form
            deleted_count = NLPSearchService.clear_user_search_history(
                user_id=str(user.id), form_id=form_id
            )

        return jsonify(
            {
                "deleted_count": deleted_count,
                "message": f"{deleted_count} search record(s) cleared successfully",
            }
        )

    except Exception as e:
        current_app.logger.error(f"Error clearing search history: {str(e)}")
        return (
            jsonify({"error": "Failed to clear search history", "message": str(e)}),
            500,
        )


@nlp_search_bp.route("/<form_id>/search-history/<search_id>", methods=["DELETE"])
@jwt_required()
def delete_search_history_item(form_id: str, search_id: str):
    """
    Delete a specific search history item.

    Returns:
        {
            "deleted_count": 1,
            "message": "Search record deleted successfully"
        }
    """
    user = get_current_user()

    try:
        from models import SearchHistory
        from uuid import UUID

        # Validate search_id
        try:
            search_uuid = UUID(search_id)
        except ValueError:
            return jsonify({"error": "Invalid search ID"}), 400

        # Delete the specific record (only if it belongs to the user)
        deleted_count = SearchHistory.objects(
            id=search_uuid, user_id=str(user.id)
        ).delete()

        if deleted_count == 0:
            return jsonify({"error": "Search record not found"}), 404

        return jsonify(
            {
                "deleted_count": deleted_count,
                "message": "Search record deleted successfully",
            }
        )

    except Exception as e:
        current_app.logger.error(f"Error deleting search history item: {str(e)}")
        return (
            jsonify({"error": "Failed to delete search record", "message": str(e)}),
            500,
        )


@nlp_search_bp.route("/<form_id>/popular-queries", methods=["GET"])
@jwt_required()
def get_popular_queries(form_id: str):
    """
    Get popular search queries for a form.

    Uses caching (1 hour TTL) for performance.

    Query Parameters:
        limit: Maximum number of results (default: 10, max: 50)
        nocache: If "true", bypasses cache and fetches fresh data

    Returns:
        {
            "form_id": "form123",
            "popular_queries": [
                {"query": "delivery issues", "count": 45},
                {"query": "product quality", "count": 32},
                {"query": "customer support", "count": 28}
            ],
            "cached": true
        }
    """
    get_current_user()

    # Get limit parameter
    try:
        limit = min(int(request.args.get("limit", 10)), 50)
    except (ValueError, TypeError):
        limit = 10

    # Check if bypassing cache
    nocache = request.args.get("nocache", "").lower() == "true"

    try:
        if nocache:
            # Fetch fresh data without cache
            popular_queries = NLPSearchService.get_popular_queries(
                form_id=form_id, limit=limit
            )
            cached = False
        else:
            # Use cached version
            popular_queries = NLPSearchService.get_popular_queries_cached(
                form_id=form_id, limit=limit
            )
            cached = True

        return jsonify(
            {"form_id": form_id, "popular_queries": popular_queries, "cached": cached}
        )

    except Exception as e:
        current_app.logger.error(f"Error fetching popular queries: {str(e)}")
        return (
            jsonify({"error": "Failed to fetch popular queries", "message": str(e)}),
            500,
        )
