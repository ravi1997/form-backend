from config.celery import celery_app
from services.notification_service import NotificationService
from logger.unified_logger import app_logger, error_logger, audit_logger

@celery_app.task
def process_notification_triggers(triggers_data, context_data):
    """
    Orchestrator task that fan-outs multiple notification actions.
    """
    app_logger.info(f"Entering process_notification_triggers: fanning out {len(triggers_data)} triggers")
    for trigger in triggers_data:
        process_single_trigger.delay(trigger, context_data)
    app_logger.info(f"Exiting process_notification_triggers: dispatched {len(triggers_data)} triggers")
    return {"status": "dispatched", "count": len(triggers_data)}


@celery_app.task(
    bind=True, 
    max_retries=5, 
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=3600,
    retry_jitter=True
)
def process_single_trigger(self, trigger_data, context_data):
    """
    Background task to process a SINGLE notification trigger.
    Includes robust retry with exponential backoff.
    """
    trigger_name = trigger_data.get("name", "unnamed")
    action_type = trigger_data.get("action_type")
    
    app_logger.info(f"Entering process_single_trigger: name={trigger_name}, type={action_type}")
    
    try:
        from services.notification_service import NotificationService
        
        if action_type == "webhook":
            NotificationService._call_webhook(trigger_data.get("action_config", {}), context_data)
        elif action_type == "api_call":
            NotificationService._call_external_api(trigger_data.get("action_config", {}), context_data)
        elif action_type == "execute_script":
            # Still blocked for security, but logged
            app_logger.warning(f"Custom script execution requested for {trigger_name} but blocked.")
        else:
            app_logger.warning(f"Unknown action type: {action_type}")
            
        audit_logger.info(f"Notification trigger {trigger_name} (type: {action_type}) processed successfully")
        app_logger.info(f"Exiting process_single_trigger: {trigger_name} processed")
    except Exception as e:
        error_logger.error(f"Trigger {trigger_name} failed: {str(e)}")
        # Re-raise to trigger Celery retry
        raise e


@celery_app.task
def long_running_computation(data):
    """
    Example of a long-running computation task.
    """
    import time

    app_logger.info(f"Entering long_running_computation for {data}")
    # Simulating work
    result = sum(i * i for i in range(1000000))
    time.sleep(2)
    app_logger.info("Exiting long_running_computation")
    return {"status": "completed", "result": result}
