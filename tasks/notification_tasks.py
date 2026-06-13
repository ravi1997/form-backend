from config.celery import celery_app
from services.notification_service import NotificationService
from logger.unified_logger import app_logger, error_logger, audit_logger
from models.NotificationLog import NotificationLog
from datetime import datetime, timezone


DEFAULT_NOTIFICATION_RETRY_BATCH_SIZE = 50
DEFAULT_NOTIFICATION_MAX_RETRIES = 3


@celery_app.task
def process_notification_triggers(triggers_data, context_data):
    """
    Orchestrator task that fan-outs multiple notification actions.
    """
    app_logger.info(
        f"Entering process_notification_triggers: fanning out {len(triggers_data)} triggers"
    )
    for trigger in triggers_data:
        process_single_trigger.delay(trigger, context_data)
    app_logger.info(
        f"Exiting process_notification_triggers: dispatched {len(triggers_data)} triggers"
    )
    return {"status": "dispatched", "count": len(triggers_data)}


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=3600,
    retry_jitter=True,
)
def process_single_trigger(self, trigger_data, context_data):
    """
    Background task to process a SINGLE notification trigger.
    Includes robust retry with exponential backoff.
    """
    from services.notification_service import NotificationObservability

    trigger_name = trigger_data.get("name", "unnamed")
    action_type = trigger_data.get("action_type", "unknown")

    app_logger.info(
        f"Entering process_single_trigger: name={trigger_name}, type={action_type}"
    )

    retries = self.request.retries or 0
    if retries > 0:
        NotificationObservability.increment_retry(action_type)
    else:
        NotificationObservability.increment_attempt(action_type)

    try:
        from services.notification_service import NotificationService

        if action_type == "webhook":
            NotificationService._call_webhook(
                trigger_data.get("action_config", {}), context_data
            )
        elif action_type == "email_notification":
            NotificationService._call_external_api(
                trigger_data.get("action_config", {}), context_data
            )
        elif action_type == "api_call":
            NotificationService._call_external_api(
                trigger_data.get("action_config", {}), context_data
            )
        elif action_type == "execute_script":
            # Still blocked for security, but logged
            app_logger.warning(
                f"Custom script execution requested for {trigger_name} but blocked."
            )
        else:
            app_logger.warning(f"Unknown action type: {action_type}")

        NotificationObservability.increment_success(action_type)
        audit_logger.info(
            f"Notification trigger {trigger_name} (type: {action_type}) processed successfully"
        )
        app_logger.info(f"Exiting process_single_trigger: {trigger_name} processed")
    except Exception as e:
        NotificationObservability.increment_failure(action_type)
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


@celery_app.task(bind=True)
def process_outbox_events_task(self, max_retries=3):
    """
    Background task/worker loop to publish failed/pending outbox events.
    """
    from services.outbox_service import outbox_service
    app_logger.info("Entering process_outbox_events_task")
    result = outbox_service.process_pending_outbox_events(max_retries=max_retries)
    app_logger.info(f"Exiting process_outbox_events_task with result: {result}")
    return result


def _deliver_notification_log(notification_log):
    """
    Replays a persisted notification delivery attempt using the stored log payload.
    """
    channel = str(notification_log.channel or "").strip().lower()
    payload = notification_log.payload or {}
    context_data = payload.get("context_data", payload)
    response = None
    action_config = payload.get("action_config") or payload.get("config") or {}

    if channel == "webhook":
        response = NotificationService._call_webhook(
            action_config, context_data
        )
    elif channel in {"email", "email_notification"}:
        response = NotificationService._call_external_api(
            action_config, context_data
        )
    elif channel == "api_call":
        response = NotificationService._call_external_api(
            action_config, context_data
        )
    elif channel == "execute_script":
        NotificationService._run_custom_logic(payload.get("script", ""), context_data)
    else:
        raise ValueError(f"Unsupported notification channel: {channel}")

    return response


@celery_app.task(bind=True)
def process_notification_retry_queue_task(
    self,
    batch_size=DEFAULT_NOTIFICATION_RETRY_BATCH_SIZE,
    max_retries=DEFAULT_NOTIFICATION_MAX_RETRIES,
):
    """
    Polls NotificationLog for retryable notification deliveries and replays them.
    """
    app_logger.info(
        "Entering process_notification_retry_queue_task "
        f"batch_size={batch_size}, max_retries={max_retries}"
    )

    retryable_logs = (
        NotificationLog.objects(status__in=["pending", "failed"], attempt_count__lt=max_retries)
        .order_by("created_at")
        .limit(batch_size)
    )

    processed = 0
    succeeded = 0
    failed = 0
    skipped = 0

    for notification_log in retryable_logs:
        processed += 1
        try:
            notification_log.attempt_count = (notification_log.attempt_count or 0) + 1
            response = _deliver_notification_log(notification_log)
            notification_log.status = "sent"
            notification_log.response = response or {}
            notification_log.error_message = ""
            notification_log.sent_at = datetime.now(timezone.utc)
            notification_log.save()
            audit_logger.info(
                "AUDIT: NotificationLog %s delivered successfully",
                str(notification_log.id),
            )
            succeeded += 1
        except ValueError as exc:
            notification_log.status = "skipped"
            notification_log.error_message = str(exc)
            notification_log.save()
            skipped += 1
            error_logger.error(
                f"NotificationLog {notification_log.id} skipped: {exc}",
                exc_info=True,
            )
        except Exception as exc:
            notification_log.status = "failed"
            notification_log.error_message = str(exc)
            notification_log.save()
            failed += 1
            error_logger.error(
                f"NotificationLog {notification_log.id} failed during retry: {exc}",
                exc_info=True,
            )

    result = {
        "status": "completed",
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
    }
    app_logger.info(
        "Exiting process_notification_retry_queue_task with result: %s",
        result,
    )
    return result
