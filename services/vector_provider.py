import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any

import requests

from config.settings import settings
from logger.unified_logger import app_logger, error_logger


class AbstractVectorProvider(ABC):
    """
    Abstract interface for Retrieval-Augmented Generation (RAG) indices.
    Allows dynamic swapping between ChromaDB, Qdrant, Milvus, or PgVector.
    """
    @abstractmethod
    def embed_and_store(self, tenant_id: str, document_id: str, text: str, metadata: dict = None) -> bool:
        """Vectorizes text using an embedding model and stores it strictly within tenant bounds."""
        pass

    @abstractmethod
    def semantic_search(self, tenant_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Executes a Cosine-Similarity nearest-neighbor search adhering to tenant isolation."""
        pass


class MockVectorProvider(AbstractVectorProvider):
    """
    Placeholder implementation suitable for CI/CD or development 
    without a heavy active GPU instance available.
    """
    def embed_and_store(self, tenant_id: str, document_id: str, text: str, metadata: dict = None) -> bool:
        # We must never store raw PII in vector stores unprotected if they are multitenant.
        # RAG pipelines require significant security review per tenant.
        app_logger.info(f"Vector Stub: Simulated embedding for tenant {tenant_id} on doc {document_id}")
        return True

    def semantic_search(self, tenant_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        app_logger.info(f"Vector Stub: Searching tenant {tenant_id} namespace for: {query}")
        return [{"score": 0.99, "document_id": "dummy-123", "snippet": "Simulated match"}]


class QdrantVectorProvider(AbstractVectorProvider):
    """
    Qdrant implementation for Retrieval-Augmented Generation (RAG) indices.
    Uses the Qdrant REST API to store and query embeddings.
    """
    def __init__(self, host: str, port: int):
        self.base_url = f"http://{host}:{port}"
        app_logger.info(f"Initialized Qdrant Vector Interface mapped to {self.base_url}")

    def embed_and_store(self, tenant_id: str, document_id: str, text: str, metadata: dict = None) -> bool:
        app_logger.info(f"Embedding and storing document {document_id} for tenant {tenant_id}")
        try:
            from services.ai_service import ai_service
            vector = ai_service.generate_embeddings(text)
            
            # In this multi-tenant implementation, we use a single collection with filter
            # but we could also use a collection per tenant.
            collection_name = f"tenant_{tenant_id}"
            
            # Upsert point
            point = {
                "id": document_id,
                "vector": vector,
                "payload": {**(metadata or {}), "text": text, "tenant_id": tenant_id}
            }
            
            resp = requests.put(
                f"{self.base_url}/collections/{collection_name}/points?wait=true",
                json={"points": [point]},
                timeout=10
            )
            if resp.status_code != 200:
                app_logger.warning(f"Failed to store in collection {collection_name}: {resp.text}")
                return False
            
            app_logger.info(f"Successfully stored document {document_id} in collection {collection_name}")
            return True
        except Exception as e:
            error_logger.error(f"Qdrant embed_and_store failed for document {document_id}: {e}", exc_info=True)
            return False

    def semantic_search(self, tenant_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        app_logger.info(f"Executing semantic search for tenant {tenant_id} with query: {query}")
        try:
            from services.ai_service import ai_service
            vector = ai_service.generate_embeddings(query)
            collection_name = f"tenant_{tenant_id}"
            
            payload = {
                "vector": vector,
                "limit": limit,
                "with_payload": True
            }
            
            resp = requests.post(
                f"{self.base_url}/collections/{collection_name}/points/search",
                json=payload,
                timeout=10
            )
            if resp.status_code != 200:
                app_logger.warning(f"Qdrant search failed for {collection_name}: {resp.text}")
                return []
            
            results = [
                {
                    "score": r["score"],
                    "document_id": r["id"],
                    "snippet": r.get("payload", {}).get("text", "")
                }
                for r in resp.json().get("result", [])
            ]
            app_logger.info(f"Found {len(results)} matches for query in tenant {tenant_id} namespace")
            return results
        except Exception as e:
            error_logger.error(f"Qdrant semantic_search failed for tenant {tenant_id}: {e}", exc_info=True)
            return []


# Bootstrap active provider
if settings.APP_ENV != "development":
    vector_provider = QdrantVectorProvider(settings.QDRANT_HOST, settings.QDRANT_PORT)
else:
    vector_provider = MockVectorProvider()
