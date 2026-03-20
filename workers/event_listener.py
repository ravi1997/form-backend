import logging
from app import create_app
from services import event_bus
from models import Form
from tasks.notification_tasks import process_notification_triggers
from services.vector_provider import vector_provider
from services.search_service import search_service

logger = logging.getLogger(__name__)

def handle_form_submitted(payload: dict):
    """
    Consumer logic for the 'form.submitted' event.
    Re-couples the background asynchronous processing (Webhooks, Emails, SMS)
    without burdening the synchronous web tier.
    """
    form_id = payload.get("form_id")
    response_id = payload.get("response_id")
    
    logger.info(f"EventBus Consumer working on FormSubmitted: {response_id}")
    
    try:
        form = Form.objects(id=form_id, is_deleted=False).first()
        if form and form.triggers:
            triggers_data = [t.to_mongo().to_dict() for t in form.triggers if t.is_active]
            if triggers_data:
                process_notification_triggers.delay(triggers_data, payload)
                logger.info(f"Delegated {len(triggers_data)} triggers to Celery for {response_id}")
    except Exception as e:
        logger.error(f"Error handling form.submitted event: {e}")

def handle_form_indexed(payload: dict):
    """
    Consumer logic for 'form.indexed'.
    Synchronizes the MongoDB truth to Elasticsearch entirely out-of-band.
    """
    logger.info(f"EventBus Consumer working on FormIndexed: {payload.get('id')}")
    try:
        search_service.index_form(payload)
        # Simultaneously vectorize for RAG if configured
        vector_provider.embed_and_store(
            tenant_id=payload.get("organization_id", "unknown"),
            document_id=payload.get("id"),
            text=str(payload)
        )
    except Exception as e:
        logger.error(f"Error handling form.indexed event: {e}")

def start_consumers():
    """Blocking loop to consume Redis PubSub events."""
    app = create_app()
    with app.app_context():
        logger.info("Initializing Redis EventBus listeners...")
        event_bus.subscribe("form.submitted", handle_form_submitted)
        event_bus.subscribe("form.indexed", handle_form_indexed)

if __name__ == "__main__":
    start_consumers()
