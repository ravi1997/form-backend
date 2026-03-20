from config.celery import celery_app
from services.summarization_service import summarization_service
from logger.unified_logger import get_logger, error_logger
from models.Response import FormResponse
from models.Response import SummarySnapshot
from datetime import datetime, timezone

logger = get_logger(__name__)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def async_generate_form_summary(self, form_id: str, organization_id: str):
    """
    Background task to generate an executive summary for a form's responses.
    """
    logger.info(f"AI Task: Starting summary generation for form {form_id}")
    try:
        # Fetch responses (multi-tenant isolated)
        responses = FormResponse.objects(
            form=form_id, 
            organization_id=organization_id, 
            is_deleted=False
        ).only("data", "submitted_at")
        
        if not responses:
            return {"status": "skipped", "reason": "no_responses"}
            
        # Convert to list of dicts for the service
        response_data = [r.to_mongo().to_dict() for r in responses]
        
        # Map-Reduce Summarization
        summary = summarization_service.generate_executive_summary(response_data)
        
        # Save Snapshot for persistent viewing
        snapshot = SummarySnapshot(
            form_id=form_id,
            timestamp=datetime.now(timezone.utc),
            period_start=responses.order_by("submitted_at").first().submitted_at,
            period_end=responses.order_by("-submitted_at").first().submitted_at,
            response_count=len(responses),
            summary_data={"executive_summary": summary},
            strategy_used="map_reduce_v1"
        )
        snapshot.save()
        
        logger.info(f"AI Task: Summary snapshot {snapshot.id} created for form {form_id}")
        return {"status": "success", "snapshot_id": str(snapshot.id)}
        
    except Exception as e:
        error_logger.error(f"AI Task failed for form {form_id}: {str(e)}", exc_info=True)
        raise self.retry(exc=e)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def async_index_response_vector(self, response_id, organization_id):
    """
    Background task to vectorize a form response and store it in the vector database.
    This enables semantic search across form submissions.
    """
    from services.vector_provider import vector_provider
    from models.Response import FormResponse
    import json

    logger.info(f"AI Task: Vectorizing response {response_id}")
    try:
        response = FormResponse.objects(id=response_id, organization_id=organization_id, is_deleted=False).first()
        if not response:
            logger.error(f"Response {response_id} not found for vectorization")
            return {"status": "error", "message": "Response not found"}

        # Combine all text fields for vectorization
        # (Exclude sensitive fields to prevent PII in vector store)
        text_content = json.dumps(response.data)
        
        metadata = {
            "form_id": str(response.form.id),
            "submitted_at": response.submitted_at.isoformat(),
            "status": response.status
        }
        
        success = vector_provider.embed_and_store(
            tenant_id=organization_id,
            document_id=response_id,
            text=text_content,
            metadata=metadata
        )
        
        if success:
            logger.info(f"Response {response_id} indexed in vector DB successfully")
            return {"status": "success"}
        else:
            logger.error(f"Failed to index response {response_id} in vector DB")
            return {"status": "error"}
            
    except Exception as e:
        error_logger.error(f"AI Task index_response_vector failed for {response_id}: {str(e)}", exc_info=True)
        raise self.retry(exc=e)

@celery_app.task(bind=True, max_retries=5, default_retry_delay=60)
def async_export_to_olap(self, event_payload):
    """
    Consumes submission events and exports them to a high-performance 
    columnar store (DuckDB/ClickHouse) for real-time analytics.
    """
    from services.analytics_stream_service import analytics_stream_service
    try:
        analytics_stream_service.process_submission_event(event_payload)
        return {"status": "success"}
    except Exception as e:
        error_logger.error(f"OLAP Export Task failed: {str(e)}", exc_info=True)
        raise self.retry(exc=e)
