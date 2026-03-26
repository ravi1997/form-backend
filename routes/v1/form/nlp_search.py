from . import form_bp
from flasgger import swag_from
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
@swag_from({
    "tags": [
        "Nlp_Search"
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
def nlp_search(form_id: str):
    """
    Natural language search across form responses with advanced filtering.
    """
    app_logger.info(f"Entering nlp_search for form_id: {form_id}")
    user = get_current_user()
    data = request.get_json()

    from uuid import UUID
    from models import Form
    try:
        form_uuid = UUID(form_id)
        # Check permission/existence
        form = Form.objects(id=form_uuid, organization_id=user.organization_id).first()
        if not form:
             app_logger.warning(f"Form not found: {form_id}")
             return jsonify({"error": "Form not found"}), 404
    except ValueError:
        app_logger.warning(f"Invalid form ID format: {form_id}")
        return jsonify({"error": "Invalid form ID format"}), 400

    if not data or "query" not in data:
        app_logger.warning("Query is required but missing in request data")
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
        app_logger.warning(f"Invalid filter_mode: {filter_mode}")
        return jsonify({"error": "filter_mode must be 'and' or 'or'"}), 400

    start_time = time.time()

    # Validate date range if provided
    if filters.get("date_range"):
        is_valid, error_msg = NLPSearchService.validate_date_range(
            filters["date_range"]
        )
        if not is_valid:
            app_logger.warning(f"Invalid date range: {error_msg}")
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
                app_logger.warning(f"Invalid field names: {invalid_fields}")
                return (
                    jsonify(
                        {
                            "error": "Invalid field names",
                            "invalid_fields": invalid_fields,
                        }
                    ),
                    400,
                )
        except Exception as e:
            # If form not found or schema unavailable, skip validation
            app_logger.debug(f"Skipping field validation for form {form_id}: {e}")
            pass

    # Check cache first
    cache_key = NLPSearchService.generate_cache_key(form_id, query, "nlp")
    if use_cache:
        cached_result = redis_client.get_with_lock(cache_key)
        if cached_result:
            app_logger.info(f"Returning cached search results for form {form_id}")
            return jsonify({**cached_result, "cached": True})

    try:
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
                app_logger.warning("Semantic search failed, falling back to keyword search")
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
            app_logger.warning(f"Failed to save search history: {e}")

        app_logger.info(f"Exiting nlp_search for form_id: {form_id} with {len(results)} results")
        return jsonify(response)
    except Exception as e:
        error_logger.error(f"Error in nlp_search for form {form_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error during search"}), 500


@nlp_search_bp.route("/<form_id>/semantic-search", methods=["POST"])
@swag_from({
    "tags": [
        "Nlp_Search"
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
def semantic_search(form_id: str):
    """
    Pure semantic search using Ollama embeddings with advanced filtering.
    """
    app_logger.info(f"Entering semantic_search for form_id: {form_id}")
    user = get_current_user()
    data = request.get_json()

    if not data or "query" not in data:
        app_logger.warning("Query is required but missing in request data")
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
            app_logger.warning(f"Invalid date range: {error_msg}")
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
                app_logger.warning(f"Invalid field names: {invalid_fields}")
                return (
                    jsonify(
                        {
                            "error": "Invalid field names",
                            "invalid_fields": invalid_fields,
                        }
                    ),
                    400,
                )
        except Exception as e:
            # If form not found or schema unavailable, skip validation
            app_logger.debug(f"Skipping field validation for form {form_id}: {e}")
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
        app_logger.warning(f"Invalid filter_mode: {filter_mode}")
        return jsonify({"error": "filter_mode must be 'and' or 'or'"}), 400

    try:
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
            app_logger.warning(f"Failed to save search history: {e}")

        app_logger.info(f"Exiting semantic_search for form_id: {form_id} with {len(results)} results")
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

    except (ConnectionError, TimeoutError) as e:
        error_logger.error(f"Ollama service error in semantic_search: {str(e)}")
        return (
            jsonify(
                {
                    "error": "Ollama service is not available",
                    "message": "Ensure Ollama is running with embedding support",
                }
            ),
            503,
        )
    except Exception as e:
        error_logger.error(f"Unexpected error in semantic_search for form {form_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error during semantic search"}), 500


@nlp_search_bp.route("/<form_id>/semantic-search/stream", methods=["POST"])
@swag_from({
    "tags": [
        "Nlp_Search"
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
def semantic_search_stream(form_id: str):
    """
    Pure semantic search using Ollama embeddings with streaming response and advanced filtering.
    """
    app_logger.info(f"Entering semantic_search_stream for form_id: {form_id}")
    get_current_user()
    data = request.get_json()

    if not data or "query" not in data:
        app_logger.warning("Query is required but missing in request data")
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
            app_logger.warning(f"Invalid date range: {error_msg}")
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
                app_logger.warning(f"Invalid field names: {invalid_fields}")
                return (
                    jsonify(
                        {
                            "error": "Invalid field names",
                            "invalid_fields": invalid_fields,
                        }
                    ),
                    400,
                )
        except Exception as e:
            # If form not found or schema unavailable, skip validation
            app_logger.debug(f"Skipping field validation for form {form_id}: {e}")
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
        app_logger.warning(f"Invalid filter_mode: {filter_mode}")
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
            app_logger.info(f"Exiting semantic_search_stream for form_id: {form_id} with {len(results)} results")
            yield f"data: {json.dumps({'content': json.dumps(results_data), 'done': True, 'model_used': OllamaService.get_embedding_model(), 'results_count': len(results)})}\n\n"

        except (ConnectionError, TimeoutError) as e:
            error_logger.error(f"Ollama service error in semantic_search_stream: {str(e)}")
            error_data = {
                "content": "",
                "done": True,
                "error": "Ollama service is not available",
                "message": "Ensure Ollama is running with embedding support",
            }
            yield f"data: {json.dumps(error_data)}\n\n"
        except Exception as e:
            error_logger.error(f"Unexpected error in semantic_search_stream for form {form_id}: {str(e)}", exc_info=True)
            error_data = {
                "content": "",
                "done": True,
                "error": "Internal server error",
                "message": str(e),
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
@swag_from({
    "tags": [
        "Nlp_Search"
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
def search_stats(form_id: str):
    """
    Get search-related statistics for a form.
    """
    app_logger.info(f"Entering search_stats for form_id: {form_id}")
    get_current_user()

    try:
        total_responses = FormResponse.objects(form_id=form_id).count()

        # Check Ollama availability
        ollama_health = OllamaService.health_check()
        ollama_available = ollama_health.get("available", False)

        app_logger.info(f"Exiting search_stats for form_id: {form_id}")
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
    except Exception as e:
        error_logger.error(f"Error in search_stats for form {form_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@nlp_search_bp.route("/<form_id>/query-suggestions", methods=["GET"])
@swag_from({
    "tags": [
        "Nlp_Search"
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
def query_suggestions(form_id: str):
    """
    Get query suggestions/autocomplete for a form.
    """
    app_logger.info(f"Entering query_suggestions for form_id: {form_id}")
    get_current_user()

    # Get query parameter
    partial_query = request.args.get("q", "").strip()
    if not partial_query:
        app_logger.warning("Query parameter 'q' is missing")
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

        app_logger.info(f"Exiting query_suggestions for form_id: {form_id} with {len(suggestions)} suggestions")
        return jsonify(
            {
                "form_id": form_id,
                "query": partial_query,
                "suggestions": suggestions,
                "total_suggestions": len(suggestions),
            }
        )

    except Exception as e:
        error_logger.error(f"Query suggestions error: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to get suggestions", "message": str(e)}), 500


@nlp_search_bp.route("/health", methods=["GET"])
@swag_from({
    "tags": [
        "Nlp_Search"
    ],
    "responses": {
        "200": {
            "description": "Success"
        }
    }
})
def health_check():
    """
    Health check for NLP search service.
    """
    app_logger.info("Entering health_check for nlp_search")
    ollama_status = OllamaService.health_check()

    app_logger.info("Exiting health_check for nlp_search")
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
@swag_from({
    "tags": [
        "Nlp_Search"
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
def get_search_history(form_id: str):
    """
    Get user's search history for a form.
    """
    app_logger.info(f"Entering get_search_history for form_id: {form_id}")
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

        app_logger.info(f"Exiting get_search_history for form_id: {form_id}")
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
        error_logger.error(f"Error fetching search history for form {form_id}: {str(e)}", exc_info=True)
        return (
            jsonify({"error": "Failed to fetch search history", "message": str(e)}),
            500,
        )


@nlp_search_bp.route("/<form_id>/search-history", methods=["POST"])
@swag_from({
    "tags": [
        "Nlp_Search"
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
def save_search_history(form_id: str):
    """
    Save a search query to user's search history.
    """
    app_logger.info(f"Entering save_search_history for form_id: {form_id}")
    user = get_current_user()
    data = request.get_json()

    if not data or "query" not in data:
        app_logger.warning("Query is required but missing in request data")
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
            app_logger.error(f"Failed to save search history for user {user.id} and form {form_id}")
            return jsonify({"error": "Failed to save search"}), 500

        audit_logger.info(f"User {user.id} saved search history item {search_id} for form {form_id}", extra={
            "user_id": str(user.id),
            "form_id": form_id,
            "search_id": str(search_id),
            "action": "save_search_history"
        })

        app_logger.info(f"Exiting save_search_history for form_id: {form_id}")
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
        error_logger.error(f"Error saving search history for form {form_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to save search", "message": str(e)}), 500


@nlp_search_bp.route("/<form_id>/search-history", methods=["DELETE"])
@swag_from({
    "tags": [
        "Nlp_Search"
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
def clear_search_history(form_id: str):
    """
    Clear user's search history for a form.
    """
    app_logger.info(f"Entering clear_search_history for form_id: {form_id}")
    user = get_current_user()

    # Check if clearing all history
    clear_all = request.args.get("all", "").lower() == "true"

    try:
        if clear_all:
            # Clear all search history for the user
            deleted_count = NLPSearchService.clear_user_search_history(
                user_id=str(user.id), form_id=None
            )
            audit_logger.info(f"User {user.id} cleared all search history", extra={
                "user_id": str(user.id),
                "action": "clear_all_search_history"
            })
        else:
            # Clear only for this form
            deleted_count = NLPSearchService.clear_user_search_history(
                user_id=str(user.id), form_id=form_id
            )
            audit_logger.info(f"User {user.id} cleared search history for form {form_id}", extra={
                "user_id": str(user.id),
                "form_id": form_id,
                "action": "clear_form_search_history"
            })

        app_logger.info(f"Exiting clear_search_history for form_id: {form_id}, deleted {deleted_count} items")
        return jsonify(
            {
                "deleted_count": deleted_count,
                "message": f"{deleted_count} search record(s) cleared successfully",
            }
        )

    except Exception as e:
        error_logger.error(f"Error clearing search history for form {form_id}: {str(e)}", exc_info=True)
        return (
            jsonify({"error": "Failed to clear search history", "message": str(e)}),
            500,
        )


@nlp_search_bp.route("/<form_id>/search-history/<search_id>", methods=["DELETE"])
@swag_from({
    "tags": [
        "Nlp_Search"
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
        },
        {
            "name": "search_id",
            "in": "path",
            "type": "string",
            "required": True
        }
    ]
})
@jwt_required()
def delete_search_history_item(form_id: str, search_id: str):
    """
    Delete a specific search history item.
    """
    app_logger.info(f"Entering delete_search_history_item for search_id: {search_id}")
    user = get_current_user()

    try:
        from models import SearchHistory
        from uuid import UUID

        # Validate search_id
        try:
            search_uuid = UUID(search_id)
        except ValueError:
            app_logger.warning(f"Invalid search ID format: {search_id}")
            return jsonify({"error": "Invalid search ID"}), 400

        # Delete the specific record (only if it belongs to the user)
        deleted_count = SearchHistory.objects(
            id=search_uuid, user_id=str(user.id)
        ).delete()

        if deleted_count == 0:
            app_logger.warning(f"Search record {search_id} not found or unauthorized for user {user.id}")
            return jsonify({"error": "Search record not found"}), 404

        audit_logger.info(f"User {user.id} deleted search history item {search_id}", extra={
            "user_id": str(user.id),
            "search_id": search_id,
            "action": "delete_search_history_item"
        })

        app_logger.info(f"Exiting delete_search_history_item for search_id: {search_id}")
        return jsonify(
            {
                "deleted_count": deleted_count,
                "message": "Search record deleted successfully",
            }
        )

    except Exception as e:
        error_logger.error(f"Error deleting search history item {search_id}: {str(e)}", exc_info=True)
        return (
            jsonify({"error": "Failed to delete search record", "message": str(e)}),
            500,
        )


@nlp_search_bp.route("/<form_id>/popular-queries", methods=["GET"])
@swag_from({
    "tags": [
        "Nlp_Search"
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
def get_popular_queries(form_id: str):
    """
    Get popular search queries for a form.
    """
    app_logger.info(f"Entering get_popular_queries for form_id: {form_id}")
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

        app_logger.info(f"Exiting get_popular_queries for form_id: {form_id}")
        return jsonify(
            {"form_id": form_id, "popular_queries": popular_queries, "cached": cached}
        )

    except Exception as e:
        error_logger.error(f"Error fetching popular queries for form {form_id}: {str(e)}", exc_info=True)
        return (
            jsonify({"error": "Failed to fetch popular queries", "message": str(e)}),
            500,
        )
