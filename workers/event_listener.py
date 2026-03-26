import threading
from app import create_app
from services import event_bus
from models import Form
from tasks.notification_tasks import process_notification_triggers
from services.vector_provider import vector_provider
from services.search_service import search_service
from logger.unified_logger import app_logger, error_logger, audit_logger

def handle_form_submitted(payload: dict):
    """
    Consumer logic for the 'form.submitted' event.
    Re-couples the background asynchronous processing (Webhooks, Emails, SMS)
    without burdening the synchronous web tier.
    """
    form_id = payload.get("form_id")
    response_id = payload.get("response_id")
    
    app_logger.info(f"Entering handle_form_submitted: response_id={response_id}")
    
    try:
        form = Form.objects(id=form_id, is_deleted=False).first()
        if form and form.triggers:
            triggers_data = [t.to_mongo().to_dict() for t in form.triggers if t.is_active]
            if triggers_data:
                process_notification_triggers.delay(triggers_data, payload)
                app_logger.info(f"Delegated {len(triggers_data)} triggers to Celery for {response_id}")
        
        audit_logger.info(f"Event 'form.submitted' processed for response_id={response_id}")
        app_logger.info(f"Exiting handle_form_submitted: {response_id}")
    except Exception as e:
        error_logger.error(f"Error handling form.submitted event for {response_id}: {e}")

def handle_form_indexed(payload: dict):
    """
    Consumer logic for 'form.indexed'.
    Synchronizes the MongoDB truth to Elasticsearch entirely out-of-band.
    """
    form_id = payload.get('id')
    app_logger.info(f"Entering handle_form_indexed: form_id={form_id}")
    try:
        search_service.index_form(payload)
        # Simultaneously vectorize for RAG if configured
        vector_provider.embed_and_store(
            tenant_id=payload.get("organization_id", "unknown"),
            document_id=form_id,
            text=str(payload)
        )
        audit_logger.info(f"Event 'form.indexed' processed for form_id={form_id}")
        app_logger.info(f"Exiting handle_form_indexed: {form_id}")
    except Exception as e:
        error_logger.error(f"Error handling form.indexed event for {form_id}: {e}")

def start_consumers():
    """Blocking loop to consume Redis PubSub events."""
    app = create_app()
    with app.app_context():
        app_logger.info("Initializing Redis EventBus listeners...")
        listeners = [
            ("form.submitted", handle_form_submitted),
            ("form.indexed", handle_form_indexed),
        ]
        threads = []
        for topic, handler in listeners:
            thread = threading.Thread(
                target=event_bus.subscribe,
                args=(topic, handler),
                daemon=True,
            )
            thread.start()
            threads.append(thread)

        app_logger.info(f"Started {len(threads)} consumer threads")
        for thread in threads:
            thread.join()

if __name__ == "__main__":
    start_consumers()
