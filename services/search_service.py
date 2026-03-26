from elasticsearch import Elasticsearch
from config.settings import settings
from logger.unified_logger import app_logger, error_logger, audit_logger

class SearchService:
    def __init__(self):
        self.es = Elasticsearch([settings.ELASTICSEARCH_URL])
        self.index_name = "forms_index"

    def init_index(self):
        """Initializes the Elasticsearch index with proper mappings."""
        app_logger.info(f"Checking if Elasticsearch index exists: {self.index_name}")
        try:
            if not self.es.indices.exists(index=self.index_name):
                mappings = {
                    "mappings": {
                        "properties": {
                            "title": {"type": "text"},
                            "description": {"type": "text"},
                            "slug": {"type": "keyword"},
                            "status": {"type": "keyword"},
                            "organization_id": {"type": "keyword"},
                            "created_at": {"type": "date"},
                            "tags": {"type": "keyword"},
                        }
                    }
                }
                self.es.indices.create(index=self.index_name, body=mappings)
                audit_logger.info(f"Created Elasticsearch index: {self.index_name}")
            else:
                app_logger.debug(f"Elasticsearch index already exists: {self.index_name}")
        except Exception as e:
            error_logger.error(f"Failed to initialize Elasticsearch index {self.index_name}: {str(e)}", exc_info=True)

    def index_form(self, form_data: dict):
        """Indexes a form document into Elasticsearch."""
        form_id = form_data.get("id")
        app_logger.info(f"Indexing form {form_id} into Elasticsearch")
        try:
            res = self.es.index(
                index=self.index_name, id=form_id, body=form_data
            )
            audit_logger.info(f"Indexed form {form_id}: {res['result']}")
        except Exception as e:
            error_logger.error(f"Failed to index form {form_id}: {str(e)}", exc_info=True)

    def search_forms(
        self, query_text: str, organization_id: str, page: int = 1, page_size: int = 10
    ):
        """Searches for forms using a multi-match query with filtering and pagination."""
        app_logger.info(f"Searching forms for query: '{query_text}', org: {organization_id}")
        body = {
            "from": (page - 1) * page_size,
            "size": page_size,
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query_text,
                                "fields": ["title^3", "description", "tags"],
                            }
                        }
                    ],
                    "filter": [{"term": {"organization_id": organization_id}}],
                }
            },
        }
        try:
            res = self.es.search(index=self.index_name, body=body)
            hits = res["hits"]["hits"]
            total = res["hits"]["total"]["value"]
            app_logger.info(f"Search successful. Found {total} results for query: '{query_text}'")
            return {
                "items": [hit["_source"] for hit in hits],
                "total": total,
                "page": page,
                "page_size": page_size,
            }
        except Exception as e:
            error_logger.error(f"Search failed for query '{query_text}': {str(e)}", exc_info=True)
            return {"items": [], "total": 0, "page": page, "page_size": page_size}


search_service = SearchService()
