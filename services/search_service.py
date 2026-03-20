from elasticsearch import Elasticsearch
from config.settings import settings
from logger import get_logger, error_logger

logger = get_logger(__name__)


class SearchService:
    def __init__(self):
        self.es = Elasticsearch([settings.ELASTICSEARCH_URL])
        self.index_name = "forms_index"

    def init_index(self):
        """Initializes the Elasticsearch index with proper mappings."""
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
            logger.info(f"Created Elasticsearch index: {self.index_name}")

    def index_form(self, form_data: dict):
        """Indexes a form document into Elasticsearch."""
        try:
            res = self.es.index(
                index=self.index_name, id=form_data["id"], body=form_data
            )
            logger.info(f"Indexed form {form_data['id']}: {res['result']}")
        except Exception as e:
            error_logger.error(f"Failed to index form {form_data.get('id')}: {e}")

    def search_forms(
        self, query_text: str, organization_id: str, page: int = 1, page_size: int = 10
    ):
        """Searches for forms using a multi-match query with filtering and pagination."""
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
            return {
                "items": [hit["_source"] for hit in hits],
                "total": total,
                "page": page,
                "page_size": page_size,
            }
        except Exception as e:
            error_logger.error(f"Search failed for query '{query_text}': {e}")
            return {"items": [], "total": 0, "page": page, "page_size": page_size}


search_service = SearchService()
