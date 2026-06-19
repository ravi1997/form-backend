"""
tasks/webhook_tasks.py
Background tasks for webhook processing.
"""

from datetime import datetime, timedelta
from celery import shared_task

from logger.unified_logger import app_logger, error_logger, audit_logger
from services.enhanced_webhook_service import enhanced_webhook_service


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def retry_webhook_delivery(self, delivery_id: str):
    """
    Retry a failed webhook delivery.
    
    Args:
        delivery_id: ID of the webhook delivery to retry
    """
    try:
        app_logger.info(f"Retrying webhook delivery: {delivery_id}")
        
        result = enhanced_webhook_service.retry_webhook_delivery(delivery_id)
        
        if result.get("status") in ["delivered", "retrying"]:
            app_logger.info(f"Webhook delivery retry successful: {delivery_id}")
            return {"status": "retried", "delivery_id": delivery_id, "result": result}
        else:
            error_logger.error(f"Webhook delivery retry failed: {delivery_id}")
            # Retry if not max retries exceeded
            if self.request.retries < self.max_retries:
                raise self.retry(countdown=60 * (self.request.retries + 1))
            return {"status": "failed", "delivery_id": delivery_id, "result": result}
            
    except Exception as e:
        error_logger.error(f"Error retrying webhook delivery {delivery_id}: {e}", exc_info=True)
        # Retry on any exception
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (self.request.retries + 1))
        return {"status": "error", "delivery_id": delivery_id, "error": str(e)}


@shared_task
def cleanup_old_webhook_logs():
    """
    Clean up old webhook delivery logs (older than 30 days).
    Runs daily.
    """
    try:
        from models.integration import WebhookDeliveryLog
        
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        old_logs = WebhookDeliveryLog.objects(
            created_at__lt=cutoff_date,
            status__in=['delivered', 'failed', 'cancelled']
        )
        
        deleted_count = old_logs.count()
        old_logs.delete()
        
        if deleted_count > 0:
            app_logger.info(f"Cleaned up {deleted_count} old webhook delivery logs")
        
        return {"status": "completed", "deleted_count": deleted_count}
        
    except Exception as e:
        error_logger.error(f"Error in cleanup_old_webhook_logs: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task
def process_webhook_queue():
    """
    Process scheduled webhook deliveries.
    Runs every minute.
    """
    try:
        from models.integration import WebhookDeliveryLog
        
        # Find webhooks that are scheduled for now or overdue
        now = datetime.utcnow()
        scheduled_webhooks = WebhookDeliveryLog.objects(
            status="scheduled",
            scheduled_for__lte=now
        )
        
        processed_count = 0
        for webhook_log in scheduled_webhooks:
            # Trigger the webhook delivery
            from services.enhanced_webhook_service import enhanced_webhook_service
            
            result = enhanced_webhook_service.send_webhook(
                url=webhook_log.url,
                payload=webhook_log.payload,
                webhook_id=webhook_log.webhook_id,
                form_id=webhook_log.form_id,
                created_by=webhook_log.created_by,
                max_retries=webhook_log.max_retries,
                headers=webhook_log.headers,
                timeout=webhook_log.timeout,
            )
            
            processed_count += 1
        
        if processed_count > 0:
            app_logger.info(f"Processed {processed_count} scheduled webhook deliveries")
        
        return {"status": "completed", "processed_count": processed_count}
        
    except Exception as e:
        error_logger.error(f"Error in process_webhook_queue: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task
def update_webhook_metrics():
    """
    Update webhook delivery metrics in Redis.
    Runs every hour.
    """
    try:
        from models.integration import WebhookDeliveryLog
        from services.redis_service import redis_service
        
        # Get metrics for the last hour
        hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        # Count by status for the last hour
        pipeline = [
            {"$match": {"created_at": {"$gte": hour_ago}}},
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1},
                "avg_response_time": {"$avg": "$response_time"}
            }}
        ]
        
        metrics = {}
        for doc in WebhookDeliveryLog.objects.aggregate(pipeline):
            status = doc['_id']
            metrics[f"{status}_count"] = doc['count']
            metrics[f"{status}_avg_response_time"] = doc['avg_response_time']
        
        # Store in Redis with 1-hour expiration
        if redis_service.cache:
            redis_key = "webhook_metrics:current_hour"
            redis_service.cache.setex(redis_key, 3600, metrics)
        
        app_logger.info(f"Updated webhook metrics: {metrics}")
        return {"status": "completed", "metrics": metrics}
        
    except Exception as e:
        error_logger.error(f"Error in update_webhook_metrics: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task
def monitor_webhook_health():
    """
    Monitor webhook health and alert on failures.
    Runs every 5 minutes.
    """
    try:
        from models.integration import WebhookDeliveryLog
        from services.redis_service import redis_service
        
        # Get failure rate for the last hour
        hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        total_deliveries = WebhookDeliveryLog.objects(
            created_at__gte=hour_ago
        ).count()
        
        failed_deliveries = WebhookDeliveryLog.objects(
            created_at__gte=hour_ago,
            status="failed"
        ).count()
        
        if total_deliveries > 0:
            failure_rate = (failed_deliveries / total_deliveries) * 100
            
            # Alert if failure rate is above 20%
            if failure_rate > 20:
                app_logger.warning(
                    f"High webhook failure rate: {failure_rate:.1f}% "
                    f"({failed_deliveries}/{total_deliveries} deliveries)"
                )
                
                # Store alert in Redis
                if redis_service.cache:
                    alert_key = "webhook_alert:high_failure_rate"
                    alert_data = {
                        "failure_rate": failure_rate,
                        "total_deliveries": total_deliveries,
                        "failed_deliveries": failed_deliveries,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    redis_service.cache.setex(alert_key, 3600, alert_data)
        
        return {"status": "completed", "total_deliveries": total_deliveries, "failed_deliveries": failed_deliveries}
        
    except Exception as e:
        error_logger.error(f"Error in monitor_webhook_health: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task
def cleanup_stale_retries():
    """
    Clean up stale webhook retries that have been in retrying state for too long.
    Runs every hour.
    """
    try:
        from models.integration import WebhookDeliveryLog
        
        # Find webhooks that have been in retrying state for more than 24 hours
        retry_cutoff = datetime.utcnow() - timedelta(hours=24)
        stale_retries = WebhookDeliveryLog.objects(
            status="retrying",
            created_at__lt=retry_cutoff
        )
        
        cancelled_count = 0
        for webhook_log in stale_retries:
            webhook_log.status = "cancelled"
            webhook_log.cancelled_at = datetime.utcnow()
            webhook_log.save()
            cancelled_count += 1
        
        if cancelled_count > 0:
            app_logger.info(f"Cancelled {cancelled_count} stale webhook retries")
        
        return {"status": "completed", "cancelled_count": cancelled_count}
        
    except Exception as e:
        error_logger.error(f"Error in cleanup_stale_retries: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}