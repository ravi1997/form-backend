class NLPSearchService:
    @staticmethod
    def validate_date_range(date_range):
        return True, None

    @staticmethod
    def validate_field_names(form, fields):
        return True, []

    @staticmethod
    def generate_cache_key(*args):
        return "stub_cache_key"

    @staticmethod
    def parse_query(query):
        return {"intent": "search", "entities": []}

    @staticmethod
    def extract_entities(query):
        return []

    @staticmethod
    def build_mongo_query(parsed):
        return {}

    @staticmethod
    def filter_by_criteria(*args, **kwargs):
        return []

    @staticmethod
    def semantic_search(tenant_id: str, query: str, limit: int = 5):
        from services.vector_provider import vector_provider
        return vector_provider.semantic_search(tenant_id, query, limit)

    @staticmethod
    def _keyword_search(*args, **kwargs):
        return []

    @staticmethod
    def save_search(*args, **kwargs):
        return "stub_search_id"

    @staticmethod
    def get_query_suggestions(*args, **kwargs):
        return []

    @staticmethod
    def get_user_search_history(*args, **kwargs):
        return []

    @staticmethod
    def clear_user_search_history(*args, **kwargs):
        return 0

    @staticmethod
    def get_popular_queries(*args, **kwargs):
        return []

    @staticmethod
    def get_popular_queries_cached(*args, **kwargs):
        return []

    @staticmethod
    def invalidate_cache(*args, **kwargs):
        return True
