"""
tasks/notification_tasks.py
Background tasks for notification processing.
"""

from datetime import datetime, timedelta
from celery import shared_task
from mongoengine import Q

from logger.unified_logger import app_logger, error_logger, audit_logger
from services.notification_engine_service import notification_engine_service
from services.redis_service import redis_service


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def deliver_notification(self, notification_id: str):
    """
    Deliver a notification to the specified channel.
    
    Args:
        notification_id: ID of the notification to deliver
    """
    try:
        app_logger.info(f"Delivering notification: {notification_id}")
        
        success = notification_engine_service.deliver_notification(notification_id)
        
        if success:
            app_logger.info(f"Notification delivered successfully: {notification_id}")
            return {"status": "delivered", "notification_id": notification_id}
        else:
            error_logger.error(f"Failed to deliver notification: {notification_id}")
            # Retry if not max retries exceeded
            if self.request.retries < self.max_retries:
                raise self.retry(countdown=60 * (self.request.retries + 1))
            return {"status": "failed", "notification_id": notification_id}
            
    except Exception as e:
        error_logger.error(f"Error delivering notification {notification_id}: {e}", exc_info=True)
        # Retry on any exception
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (self.request.retries + 1))
        return {"status": "error", "notification_id": notification_id, "error": str(e)}


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def process_notification_event(self, org_id: str, event_type: str, context: dict):
    """
    Process a notification event and create notifications for matching rules.
    
    Args:
        org_id: Organization ID
        event_type: Type of event (e.g., 'response.submitted', 'form.published')
        context: Event context data
    """
    try:
        app_logger.info(f"Processing notification event: {event_type} for org {org_id}")
        
        notifications = notification_engine_service.process_notification_event(
            org_id=org_id,
            event_type=event_type,
            context=context
        )
        
        if notifications:
            app_logger.info(f"Created {len(notifications)} notifications for event {event_type}")
            
            # Queue each notification for delivery
            for notification in notifications:
                deliver_notification.delay(str(notification.id))
            
            return {
                "status": "processed",
                "event_type": event_type,
                "notification_count": len(notifications),
                "notification_ids": [str(n.id) for n in notifications]
            }
        else:
            app_logger.info(f"No notifications created for event {event_type}")
            return {
                "status": "no_notifications",
                "event_type": event_type,
                "notification_count": 0
            }
            
    except Exception as e:
        error_logger.error(f"Error processing notification event {event_type}: {e}", exc_info=True)
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=300 * (self.request.retries + 1))
        return {"status": "error", "event_type": event_type, "error": str(e)}


@shared_task
def retry_failed_notifications():
    """
    Retry failed notifications that haven't exceeded max attempts.
    Runs every 5 minutes.
    """
    try:
        from models.notification import Notification
        
        # Find notifications that need retrying
        retry_cutoff = datetime.utcnow() - timedelta(minutes=5)
        notifications = Notification.objects(
            status='retrying',
            next_retry_at__lte=retry_cutoff,
            attempt_count__lt=3
        )
        
        retry_count = 0
        for notification in notifications:
            deliver_notification.delay(str(notification.id))
            retry_count += 1
        
        if retry_count > 0:
            app_logger.info(f"Queued {retry_count} notifications for retry")
        
        return {"status": "completed", "retry_count": retry_count}
        
    except Exception as e:
        error_logger.error(f"Error in retry_failed_notifications: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task
def cleanup_old_notifications():
    """
    Clean up old notifications (older than 90 days).
    Runs daily.
    """
    try:
        from models.notification import Notification
        
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        old_notifications = Notification.objects(
            created_at__lt=cutoff_date,
            status__in=['sent', 'failed']
        )
        
        deleted_count = old_notifications.count()
        old_notifications.delete()
        
        if deleted_count > 0:
            app_logger.info(f"Cleaned up {deleted_count} old notifications")
        
        return {"status": "completed", "deleted_count": deleted_count}
        
    except Exception as e:
        error_logger.error(f"Error in cleanup_old_notifications: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task
def send_quota_warnings():
    """
    Send quota warning notifications to organizations approaching their limits.
    Runs daily.
    """
    try:
        from models.system import StorageQuotas
        from models.identity import Organisation
        
        # Get organizations approaching quota limits
        orgs_with_quotas = StorageQuotas.objects()
        
        warning_count = 0
        for quota in orgs_with_quotas:
            org = Organisation.objects(id=quota.org_id).first()
            if not org:
                continue
            
            # Calculate usage percentage
            if quota.quota_bytes > 0:
                usage_percentage = (quota.used_bytes.get('total', 0) / quota.quota_bytes) * 100
                
                # Check if warning threshold is reached
                warning_threshold = quota.warning_threshold or 0.8  # 80% default
                if usage_percentage >= (warning_threshold * 100):
                    # Send warning notification
                    context = {
                        'organization_name': org.name,
                        'usage_percentage': round(usage_percentage, 2),
                        'quota_bytes': quota.quota_bytes,
                        'used_bytes': quota.used_bytes.get('total', 0),
                        'warning_threshold': round(warning_threshold * 100, 2)
                    }
                    
                    process_notification_event.delay(
                        org_id=str(quota.org_id),
                        event_type='quota.warning_80',
                        context=context
                    )
                    warning_count += 1
                    
                    # Check for critical threshold (90%)
                    if usage_percentage >= 90:
                        process_notification_event.delay(
                            org_id=str(quota.org_id),
                            event_type='quota.warning_90',
                            context=context
                        )
        
        if warning_count > 0:
            app_logger.info(f"Sent {warning_count} quota warning notifications")
        
        return {"status": "completed", "warning_count": warning_count}
        
    except Exception as e:
        error_logger.error(f"Error in send_quota_warnings: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task
def process_scheduled_notifications():
    """
    Process scheduled notifications (e.g., audit reminders, compliance deadlines).
    Runs hourly.
    """
    try:
        from models.compliance import ComplianceAudit
        
        # Find audits that are due soon (within 24 hours)
        soon_cutoff = datetime.utcnow() + timedelta(hours=24)
        due_audits = ComplianceAudit.objects(
            status='scheduled',
            scheduled_date__lte=soon_cutoff,
            scheduled_date__gt=datetime.utcnow()
        )
        
        reminder_count = 0
        for audit in due_audits:
            # Send reminder notification
            context = {
                'audit_title': audit.title,
                'audit_type': audit.audit_type,
                'scheduled_date': audit.scheduled_date.isoformat(),
                'compliance_standard': audit.compliance_id.name if audit.compliance_id else ''
            }
            
            process_notification_event.delay(
                org_id=audit.org_id,
                event_type='audit.reminder',
                context=context
            )
            reminder_count += 1
        
        # Find overdue audits
        overdue_audits = ComplianceAudit.objects(
            status='scheduled',
            scheduled_date__lt=datetime.utcnow()
        )
        
        overdue_count = 0
        for audit in overdue_audits:
            # Send overdue notification
            context = {
                'audit_title': audit.title,
                'audit_type': audit.audit_type,
                'scheduled_date': audit.scheduled_date.isoformat(),
                'overdue_days': (datetime.utcnow() - audit.scheduled_date).days,
                'compliance_standard': audit.compliance_id.name if audit.compliance_id else ''
            }
            
            process_notification_event.delay(
                org_id=audit.org_id,
                event_type='audit.overdue',
                context=context
            )
            overdue_count += 1
        
        if reminder_count > 0 or overdue_count > 0:
            app_logger.info(f"Processed {reminder_count} audit reminders and {overdue_count} overdue notifications")
        
        return {
            "status": "completed",
            "reminder_count": reminder_count,
            "overdue_count": overdue_count
        }
        
    except Exception as e:
        error_logger.error(f"Error in process_scheduled_notifications: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task
def update_notification_metrics():
    """
    Update notification delivery metrics in Redis.
    Runs every hour.
    """
    try:
        from models.notification import NotificationLog
        
        # Get metrics for the last hour
        hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        # Count by status and channel
        pipeline = [
            {"$match": {"created_at": {"$gte": hour_ago}}},
            {"$group": {
                "_id": {"status": "$status", "channel": "$channel"},
                "count": {"$sum": 1}
            }}
        ]
        
        metrics = {}
        for doc in NotificationLog.objects.aggregate(pipeline):
            key = f"{doc['_id']['channel']}_{doc['_id']['status']}"
            metrics[key] = doc['count']
        
        # Store in Redis with 1-hour expiration
        if redis_service.cache:
            redis_key = "notification_metrics:current_hour"
            redis_service.cache.setex(redis_key, 3600, metrics)
        
        app_logger.info(f"Updated notification metrics: {metrics}")
        return {"status": "completed", "metrics": metrics}
        
    except Exception as e:
        error_logger.error(f"Error in update_notification_metrics: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task
def seed_default_notification_templates():
    """
    Seed default notification templates for all organizations.
    Runs once on startup.
    """
    try:
        from models.identity import Organisation
        
        orgs = Organisation.objects(is_deleted=False)
        seeded_count = 0
        
        for org in orgs:
            # Check if templates already exist
            from models.notification import NotificationTemplate
            existing_templates = NotificationTemplate.objects(
                organization_id=str(org.id),
                is_system=True
            ).count()
            
            if existing_templates == 0:
                notification_engine_service.seed_default_notification_templates(str(org.id))
                seeded_count += 1
        
        if seeded_count > 0:
            app_logger.info(f"Seeded default notification templates for {seeded_count} organizations")
        
        return {"status": "completed", "seeded_count": seeded_count}
        
    except Exception as e:
        error_logger.error(f"Error in seed_default_notification_templates: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}