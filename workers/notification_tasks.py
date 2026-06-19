"""
workers/notification_tasks.py
Celery tasks for notification processing, including email/SMS dispatch and webhook delivery.
"""

import os
import json
import hmac
import hashlib
import requests
from datetime import datetime, timedelta
from celery import Celery
from logger.unified_logger import app_logger, error_logger, audit_logger
from services.notification_service import notification_service, NotificationObservability
from services.redis_service import redis_service
from models.notification import NotificationLog, WebhookDeliveryLog
from mongoengine import Q
from utils.response_helper import error_response

# Initialize Celery
celery = Celery('notification_tasks')
celery.conf.update(
    broker_url=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    result_backend=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30,  # 30 seconds timeout
    task_soft_time_limit=25,  # 25 seconds soft timeout
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)


@celery.task(bind=True, max_retries=3)
def process_single_trigger(self, trigger_dict, context_data):
    """
    Process a single trigger (webhook, email, SMS, etc.)
    """
    try:
        NotificationObservability.increment_attempt(trigger_dict.get('action_type', 'unknown'))
        
        action_type = trigger_dict.get('action_type')
        
        if action_type == 'webhook':
            return _process_webhook_trigger(trigger_dict, context_data)
        elif action_type == 'email':
            return _process_email_trigger(trigger_dict, context_data)
        elif action_type == 'sms':
            return _process_sms_trigger(trigger_dict, context_data)
        elif action_type == 'api_call':
            return _process_api_call_trigger(trigger_dict, context_data)
        else:
            error_logger.warning(f"Unknown trigger type: {action_type}")
            return {'status': 'skipped', 'reason': f'Unknown trigger type: {action_type}'}
            
    except Exception as e:
        error_logger.error(f"Error processing trigger: {e}", exc_info=True)
        NotificationObservability.increment_failure(trigger_dict.get('action_type', 'unknown'))
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=2 ** self.request.retries)
        
        return {'status': 'failed', 'error': str(e)}


def _process_webhook_trigger(trigger_dict, context_data):
    """Process webhook trigger with HMAC signing."""
    config = trigger_dict.get('config', {})
    url = config.get('url')
    secret = config.get('secret')
    
    if not url:
        error_logger.warning("Webhook trigger missing URL")
        return {'status': 'failed', 'error': 'Missing URL'}
    
    # Prepare payload
    payload = {
        'event': context_data.get('event', 'unknown'),
        'data': context_data.get('data', {}),
        'timestamp': datetime.utcnow().isoformat(),
        'trigger_id': trigger_dict.get('id')
    }
    
    # Generate HMAC signature if secret is provided
    headers = {'Content-Type': 'application/json'}
    if secret:
        signature = _generate_hmac_signature(secret, payload)
        headers['X-Webhook-Signature'] = f'sha256={signature}'
    
    # Add custom headers
    headers.update(config.get('headers', {}))
    
    # Log delivery attempt
    delivery_log = WebhookDeliveryLog(
        webhook_config_id=trigger_dict.get('id'),
        org_id=context_data.get('org_id'),
        event_type=context_data.get('event', 'unknown'),
        payload=payload,
        status='queued',
        attempt_count=1,
        created_at=datetime.utcnow()
    )
    delivery_log.save()
    
    try:
        # Send webhook
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        # Update delivery log
        delivery_log.status = 'delivered' if response.status_code < 400 else 'failed'
        delivery_log.http_status_code = response.status_code
        delivery_log.response_body = response.text[:1000]  # Limit response size
        delivery_log.delivered_at = datetime.utcnow()
        delivery_log.save()
        
        if response.status_code >= 400:
            error_logger.error(f"Webhook delivery failed: {response.status_code} - {response.text}")
            return {'status': 'failed', 'error': f'HTTP {response.status_code}'}
        
        NotificationObservability.increment_success('webhook')
        return {'status': 'delivered', 'status_code': response.status_code}
        
    except requests.RequestException as e:
        error_logger.error(f"Webhook delivery error: {e}")
        delivery_log.status = 'failed'
        delivery_log.response_body = str(e)[:1000]
        delivery_log.save()
        
        NotificationObservability.increment_failure('webhook')
        return {'status': 'failed', 'error': str(e)}


def _process_email_trigger(trigger_dict, context_data):
    """Process email trigger using AIIMS email API."""
    config = trigger_dict.get('config', {})
    
    # Prepare email data
    email_data = {
        'to': context_data.get('recipient_email', config.get('to')),
        'subject': config.get('subject', 'Notification from Form Builder'),
        'body': config.get('body', ''),
        'html_body': config.get('html_body', '')
    }
    
    # Add template variables
    email_data = _substitute_template_variables(email_data, context_data)
    
    # Log notification attempt
    notification_log = NotificationLog(
        rule_id=trigger_dict.get('id'),
        org_id=context_data.get('org_id'),
        event_type=context_data.get('event', 'unknown'),
        recipient_id=context_data.get('recipient_id'),
        channel='email',
        status='queued',
        attempt_count=1,
        created_at=datetime.utcnow()
    )
    notification_log.save()
    
    try:
        # Send email via AIIMS API
        result = notification_service._call_external_api(config, email_data)
        
        # Update notification log
        notification_log.status = 'sent'
        notification_log.last_attempt_at = datetime.utcnow()
        notification_log.provider_response = result
        notification_log.save()
        
        NotificationObservability.increment_success('email')
        return {'status': 'sent', 'result': result}
        
    except Exception as e:
        error_logger.error(f"Email delivery error: {e}")
        notification_log.status = 'failed'
        notification_log.last_attempt_at = datetime.utcnow()
        notification_log.provider_response = {'error': str(e)}
        notification_log.save()
        
        NotificationObservability.increment_failure('email')
        return {'status': 'failed', 'error': str(e)}


def _process_sms_trigger(trigger_dict, context_data):
    """Process SMS trigger using AIIMS SMS API."""
    config = trigger_dict.get('config', {})
    
    # Prepare SMS data
    sms_data = {
        'to': context_data.get('recipient_phone', config.get('to')),
        'message': config.get('message', '')
    }
    
    # Add template variables
    sms_data = _substitute_template_variables(sms_data, context_data)
    
    # Log notification attempt
    notification_log = NotificationLog(
        rule_id=trigger_dict.get('id'),
        org_id=context_data.get('org_id'),
        event_type=context_data.get('event', 'unknown'),
        recipient_id=context_data.get('recipient_id'),
        channel='sms',
        status='queued',
        attempt_count=1,
        created_at=datetime.utcnow()
    )
    notification_log.save()
    
    try:
        # Send SMS via AIIMS API
        base_url = os.getenv('AIIMS_SMS_API_URL') or os.getenv('SMS_API_URL')
        token = os.getenv('AIIMS_SMS_API_TOKEN') or os.getenv('SMS_API_TOKEN')
        
        if not base_url or not token:
            raise ValueError("SMS API not configured")
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        
        response = requests.post(
            base_url,
            json=sms_data,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        result = response.json()
        
        # Update notification log
        notification_log.status = 'sent'
        notification_log.last_attempt_at = datetime.utcnow()
        notification_log.provider_response = result
        notification_log.save()
        
        NotificationObservability.increment_success('sms')
        return {'status': 'sent', 'result': result}
        
    except Exception as e:
        error_logger.error(f"SMS delivery error: {e}")
        notification_log.status = 'failed'
        notification_log.last_attempt_at = datetime.utcnow()
        notification_log.provider_response = {'error': str(e)}
        notification_log.save()
        
        NotificationObservability.increment_failure('sms')
        return {'status': 'failed', 'error': str(e)}


def _process_api_call_trigger(trigger_dict, context_data):
    """Process generic API call trigger."""
    config = trigger_dict.get('config', {})
    url = config.get('url')
    method = config.get('method', 'POST').upper()
    
    if not url:
        error_logger.warning("API call trigger missing URL")
        return {'status': 'failed', 'error': 'Missing URL'}
    
    # Prepare payload
    payload = config.get('payload', {})
    payload = _substitute_template_variables(payload, context_data)
    
    # Prepare headers
    headers = {'Content-Type': 'application/json'}
    headers.update(config.get('headers', {}))
    
    try:
        response = requests.request(
            method,
            url,
            json=payload,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        result = response.json() if response.content else {}
        
        NotificationObservability.increment_success('api_call')
        return {'status': 'success', 'result': result}
        
    except Exception as e:
        error_logger.error(f"API call error: {e}")
        NotificationObservability.increment_failure('api_call')
        return {'status': 'failed', 'error': str(e)}


def _generate_hmac_signature(secret, payload):
    """Generate HMAC SHA-256 signature for webhook payload."""
    if isinstance(payload, dict):
        payload = json.dumps(payload, sort_keys=True)
    
    secret = secret.encode('utf-8')
    payload = payload.encode('utf-8')
    
    signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return signature


def _substitute_template_variables(data, context_data):
    """Substitute template variables in data with values from context."""
    if isinstance(data, dict):
        return {k: _substitute_template_variables(v, context_data) for k, v in data.items()}
    elif isinstance(data, list):
        return [_substitute_template_variables(item, context_data) for item in data]
    elif isinstance(data, str):
        # Simple template substitution
        template_vars = {
            '{{user_name}}': context_data.get('user_name', ''),
            '{{user_email}}': context_data.get('user_email', ''),
            '{{org_name}}': context_data.get('org_name', ''),
            '{{project_name}}': context_data.get('project_name', ''),
            '{{form_name}}': context_data.get('form_name', ''),
            '{{response_count}}': str(context_data.get('response_count', 0)),
            '{{action_url}}': context_data.get('action_url', ''),
            '{{timestamp}}': context_data.get('timestamp', ''),
            '{{actor_name}}': context_data.get('actor_name', ''),
            '{{entity_type}}': context_data.get('entity_type', ''),
            '{{entity_name}}': context_data.get('entity_name', ''),
        }
        
        result = data
        for var, value in template_vars.items():
            result = result.replace(var, str(value))
        
        return result
    else:
        return data


@celery.task
def retry_failed_notifications():
    """Retry failed notifications and webhook deliveries."""
    try:
        # Retry failed notifications
        failed_notifications = NotificationLog.objects(
            status='failed',
            attempt_count__lt=3,
            next_retry_at__lte=datetime.utcnow()
        )
        
        for notification in failed_notifications:
            # Implement retry logic here
            notification.attempt_count += 1
            notification.next_retry_at = datetime.utcnow() + timedelta(minutes=5 * notification.attempt_count)
            notification.save()
            
            # Re-process the notification
            # This would need to be implemented based on your notification system
        
        # Retry failed webhook deliveries
        failed_webhooks = WebhookDeliveryLog.objects(
            status='failed',
            attempt_count__lt=3,
            next_retry_at__lte=datetime.utcnow()
        )
        
        for webhook in failed_webhooks:
            # Implement retry logic here
            webhook.attempt_count += 1
            webhook.next_retry_at = datetime.utcnow() + timedelta(minutes=5 * webhook.attempt_count)
            webhook.save()
            
            # Re-process the webhook
            # This would need to be implemented based on your webhook system
        
        app_logger.info(f"Retried {len(failed_notifications)} notifications and {len(failed_webhooks)} webhooks")
        
    except Exception as e:
        error_logger.error(f"Error retrying failed notifications: {e}")


@celery.task
def cleanup_old_notification_logs():
    """Clean up old notification and webhook logs."""
    try:
        # Keep logs for 30 days
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        # Delete old notification logs
        old_notifications = NotificationLog.objects(created_at__lt=cutoff_date)
        notification_count = old_notifications.count()
        old_notifications.delete()
        
        # Delete old webhook logs
        old_webhooks = WebhookDeliveryLog.objects(created_at__lt=cutoff_date)
        webhook_count = old_webhooks.count()
        old_webhooks.delete()
        
        app_logger.info(f"Cleaned up {notification_count} notification logs and {webhook_count} webhook logs")
        
    except Exception as e:
        error_logger.error(f"Error cleaning up notification logs: {e}")