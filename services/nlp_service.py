from logger.unified_logger import app_logger, error_logger, audit_logger


class NLPSearchService:
    @staticmethod
    def validate_date_range(date_range):
        app_logger.debug(f"Validating date range: {date_range}")
        return True, None

    @staticmethod
    def validate_field_names(form, fields):
        app_logger.debug(f"Validating field names: {fields}")
        return True, []

    @staticmethod
    def generate_cache_key(*args):
        import hashlib

        normalized = "|".join(str(arg) for arg in args)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
        return f"nlp:{digest}"

    @staticmethod
    def parse_query(query):
        app_logger.info(f"Parsing NLP query: {query}")
        return {"intent": "search", "entities": []}

    @staticmethod
    def extract_entities(query):
        app_logger.info(f"Extracting entities from query: {query}")
        return []

    @staticmethod
    def build_mongo_query(parsed):
        app_logger.debug(f"Building mongo query from: {parsed}")
        return {}

    @staticmethod
    def filter_by_criteria(*args, **kwargs):
        app_logger.info("Filtering results by criteria")
        return []

    @staticmethod
    def semantic_search(tenant_id: str, query: str, limit: int = 5):
        app_logger.info(f"Performing semantic search for tenant {tenant_id}: {query}")
        try:
            from services.vector_provider import vector_provider

            results = vector_provider.semantic_search(tenant_id, query, limit)
            app_logger.info(f"Semantic search returned {len(results)} results")
            return results
        except Exception as e:
            error_logger.error(f"Error during semantic search: {str(e)}", exc_info=True)
            return []

    @staticmethod
    def _keyword_search(*args, **kwargs):
        return []

    @staticmethod
    def save_search(*args, **kwargs):
        app_logger.info("Saving search history")
        from models import SearchHistory

        payload = dict(kwargs)
        user_id = str(payload.get("user_id") or "")
        form_id = str(payload.get("form_id") or "")
        query = str(payload.get("query") or "")
        if not user_id or not form_id or not query:
            return None

        record = SearchHistory(
            user_id=user_id,
            form_id=form_id,
            query=query,
            results_count=int(payload.get("results_count") or 0),
            parsed_intent=payload.get("parsed_intent") or {},
            search_type=payload.get("search_type") or "nlp",
            cached=bool(payload.get("cached", False)),
        )
        record.save()
        return str(record.id)

    @staticmethod
    def get_query_suggestions(*args, **kwargs):
        app_logger.debug("Getting query suggestions")
        return []

    @staticmethod
    def get_user_search_history(*args, **kwargs):
        app_logger.debug("Getting user search history")
        from models import SearchHistory

        user_id = kwargs.get("user_id")
        form_id = kwargs.get("form_id")
        limit = int(kwargs.get("limit", 50))
        offset = int(kwargs.get("offset", 0))

        filters = {"user_id": user_id}
        if form_id:
            filters["form_id"] = form_id
        query = SearchHistory.objects(**filters)
        records = query.order_by("-created_at").skip(offset).limit(limit)
        return [
            {
                "id": str(record.id),
                "form_id": record.form_id,
                "user_id": record.user_id,
                "query": record.query,
                "results_count": record.results_count,
                "parsed_intent": record.parsed_intent,
                "search_type": record.search_type,
                "cached": record.cached,
                "created_at": record.created_at.isoformat()
                if record.created_at
                else None,
            }
            for record in records
        ]

    @staticmethod
    def clear_user_search_history(*args, **kwargs):
        app_logger.info("Clearing user search history")
        from models import SearchHistory

        user_id = kwargs.get("user_id")
        form_id = kwargs.get("form_id")
        filters = {"user_id": user_id}
        if form_id:
            filters["form_id"] = form_id
        query = SearchHistory.objects(**filters)
        deleted = query.delete()
        return deleted

    @staticmethod
    def get_popular_queries(*args, **kwargs):
        from models import SearchHistory

        form_id = kwargs.get("form_id")
        limit = int(kwargs.get("limit", 10))
        filters = {}
        if form_id:
            filters["form_id"] = form_id
        query = SearchHistory.objects(**filters)
        counts = {}
        for record in query:
            counts[record.query] = counts.get(record.query, 0) + 1
        return [
            {"query": query_text, "count": count}
            for query_text, count in sorted(
                counts.items(), key=lambda item: (-item[1], item[0])
            )[:limit]
        ]

    @staticmethod
    def get_popular_queries_cached(*args, **kwargs):
        return NLPSearchService.get_popular_queries(*args, **kwargs)

    @staticmethod
    def invalidate_cache(*args, **kwargs):
        app_logger.info("Invalidating search cache")
        return True
