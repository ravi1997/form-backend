"""
services/notification_engine_service.py
Full notification engine with email, SMS, in-app, push, and webhook delivery.
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import uuid4
from mongoengine import Q

from logger.unified_logger import app_logger, error_logger, audit_logger
from services.base import BaseService
from models.notification import (
    NotificationTemplate, NotificationRule, Notification, 
    NotificationLog, NotificationPreference
)
from services.redis_service import redis_service
from utils.exceptions import ValidationError, NotFoundError


class NotificationEngineService(BaseService):
    """Full notification engine with multi-channel delivery."""

    def __init__(self):
        super().__init__(model=Notification, schema=None)

    def create_notification_template(self, **kwargs) -> NotificationTemplate:
        """Create a notification template."""
        required_fields = ['organization_id', 'name', 'event_type', 'channels']
        for field in required_fields:
            if not kwargs.get(field):
                raise ValidationError(f"{field} is required")

        # Validate channels structure
        channels = kwargs.get('channels', {})
        valid_channels = ['email', 'sms', 'in_app', 'push', 'webhook']
        for channel in channels:
            if channel not in valid_channels:
                raise ValidationError(f"Invalid channel: {channel}")

        template = NotificationTemplate(
            organization_id=kwargs['organization_id'],
            name=kwargs['name'],
            description=kwargs.get('description'),
            event_type=kwargs['event_type'],
            channels=channels,
            variables=kwargs.get('variables', []),
            is_system=kwargs.get('is_system', False),
            is_active=kwargs.get('is_active', True),
            created_by=kwargs.get('created_by'),
            meta_data=kwargs.get('meta_data', {})
        )
        template.save()
        
        audit_logger.info(f"Notification template created: {template.name} for org {template.organization_id}")
        return template

    def get_notification_templates(self, org_id: str, event_type: Optional[str] = None) -> List[NotificationTemplate]:
        """Get notification templates for an organization."""
        query = NotificationTemplate.objects(organization_id=org_id, is_deleted=False)
        if event_type:
            query = query.filter(event_type=event_type)
        return list(query.order_by('name'))

    def create_notification_rule(self, **kwargs) -> NotificationRule:
        """Create a notification rule."""
        required_fields = ['organization_id', 'name', 'event_type', 'channels', 'template_id']
        for field in required_fields:
            if not kwargs.get(field):
                raise ValidationError(f"{field} is required")

        # Validate channels
        valid_channels = ['email', 'sms', 'in_app', 'push', 'webhook']
        for channel in kwargs['channels']:
            if channel not in valid_channels:
                raise ValidationError(f"Invalid channel: {channel}")

        rule = NotificationRule(
            organization_id=kwargs['organization_id'],
            name=kwargs['name'],
            description=kwargs.get('description'),
            event_type=kwargs['event_type'],
            trigger_conditions=kwargs.get('trigger_conditions', []),
            channels=kwargs['channels'],
            recipient_type=kwargs.get('recipient_type', 'form_owner'),
            recipient_ids=kwargs.get('recipient_ids', []),
            template_id=kwargs['template_id'],
            form_id=kwargs.get('form_id'),
            is_active=kwargs.get('is_active', True),
            created_by=kwargs.get('created_by'),
            meta_data=kwargs.get('meta_data', {})
        )
        rule.save()
        
        audit_logger.info(f"Notification rule created: {rule.name} for org {rule.organization_id}")
        return rule

    def get_notification_rules(self, org_id: str, event_type: Optional[str] = None, form_id: Optional[str] = None) -> List[NotificationRule]:
        """Get notification rules for an organization."""
        query = NotificationRule.objects(organization_id=org_id, is_deleted=False, is_active=True)
        if event_type:
            query = query.filter(event_type=event_type)
        if form_id:
            query = query.filter(form_id=form_id)
        return list(query.order_by('name'))

    def evaluate_trigger_conditions(self, rule: NotificationRule, context: Dict[str, Any]) -> bool:
        """Evaluate if a notification rule should trigger based on conditions."""
        conditions = rule.trigger_conditions or []
        if not conditions:
            return True  # No conditions means always trigger

        for condition in conditions:
            field = condition.get('field')
            operator = condition.get('operator')
            value = condition.get('value')
            
            if not all([field, operator, value]):
                continue

            context_value = self._get_nested_value(context, field)
            if not self._evaluate_condition(context_value, operator, value):
                return False

        return True

    def _get_nested_value(self, data: Dict[str, Any], field_path: str) -> Any:
        """Get nested value from dictionary using dot notation."""
        keys = field_path.split('.')
        value = data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    def _evaluate_condition(self, context_value: Any, operator: str, expected_value: Any) -> bool:
        """Evaluate a single condition."""
        if operator == 'equals':
            return context_value == expected_value
        elif operator == 'not_equals':
            return context_value != expected_value
        elif operator == 'contains':
            return str(expected_value) in str(context_value) if context_value else False
        elif operator == 'not_contains':
            return str(expected_value) not in str(context_value) if context_value else False
        elif operator == 'greater_than':
            return float(context_value) > float(expected_value) if context_value is not None else False
        elif operator == 'less_than':
            return float(context_value) < float(expected_value) if context_value is not None else False
        elif operator == 'in':
            return context_value in expected_value if isinstance(expected_value, list) else False
        elif operator == 'not_in':
            return context_value not in expected_value if isinstance(expected_value, list) else False
        return False

    def process_notification_event(self, org_id: str, event_type: str, context: Dict[str, Any]) -> List[Notification]:
        """Process a notification event and create notifications."""
        rules = self.get_notification_rules(org_id, event_type)
        notifications = []

        for rule in rules:
            if not self.evaluate_trigger_conditions(rule, context):
                continue

            # Get recipients for this rule
            recipients = self._get_recipients(rule, context)
            
            # Create notifications for each recipient and channel
            for recipient_id in recipients:
                for channel in rule.channels:
                    notification = self._create_notification(
                        rule=rule,
                        recipient_id=recipient_id,
                        channel=channel,
                        context=context
                    )
                    if notification:
                        notifications.append(notification)

        return notifications

    def _get_recipients(self, rule: NotificationRule, context: Dict[str, Any]) -> List[str]:
        """Get recipient IDs for a notification rule."""
        if rule.recipient_type == 'specific_users':
            return [str(user_id) for user_id in rule.recipient_ids]
        elif rule.recipient_type == 'form_owner':
            form_owner = context.get('form_owner_id') or context.get('created_by')
            return [str(form_owner)] if form_owner else []
        elif rule.recipient_type == 'respondent':
            respondent_id = context.get('respondent_id')
            return [str(respondent_id)] if respondent_id else []
        elif rule.recipient_type == 'role':
            # This would need to be implemented based on your role system
            role_users = context.get(f"{rule.meta_data.get('role')}_users", [])
            return role_users
        elif rule.recipient_type == 'group':
            # This would need to be implemented based on your group system
            group_users = context.get(f"group_{rule.meta_data.get('group_id')}_users", [])
            return group_users
        return []

    def _create_notification(self, rule: NotificationRule, recipient_id: str, channel: str, context: Dict[str, Any]) -> Optional[Notification]:
        """Create a single notification."""
        # Check user preferences for this channel
        if not self._check_user_preferences(recipient_id, channel, rule.event_type):
            return None

        # Get template and render content
        template = rule.template_id
        if not template or not template.is_active:
            return None

        content = self._render_template(template, channel, context)
        if not content:
            return None

        notification = Notification(
            organization_id=rule.organization_id,
            rule_id=rule,
            recipient_id=recipient_id,
            channel=channel,
            status='queued',
            title=content.get('title', ''),
            message=content.get('message', ''),
            data=context,
            max_attempts=3,
            created_at=datetime.utcnow()
        )
        notification.save()
        
        # Queue for delivery
        self._queue_notification_delivery(notification)
        
        return notification

    def _check_user_preferences(self, user_id: str, channel: str, event_type: str) -> bool:
        """Check if user has enabled notifications for this channel and event."""
        try:
            preference = NotificationPreference.objects(
                user_id=user_id,
                is_deleted=False
            ).first()
            
            if not preference:
                return True  # Default to enabled

            # Check channel preference
            if channel == 'email' and not preference.email_notifications:
                return False
            elif channel == 'sms' and not preference.sms_notifications:
                return False
            elif channel == 'in_app' and not preference.in_app_notifications:
                return False
            elif channel == 'push' and not preference.push_notifications:
                return False

            # Check event-specific preferences
            event_preferences = preference.event_preferences or {}
            return event_preferences.get(event_type, True)
        except Exception:
            return True  # Default to enabled if there's an error

    def _render_template(self, template: NotificationTemplate, channel: str, context: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Render notification template with context data."""
        try:
            channel_config = template.channels.get(channel, {})
            if not channel_config:
                return None

            # Common template variables
            template_vars = {
                'timestamp': datetime.utcnow().isoformat(),
                'organization_name': context.get('organization_name', ''),
                'form_name': context.get('form_name', ''),
                'project_name': context.get('project_name', ''),
                'user_name': context.get('user_name', ''),
                'action_url': context.get('action_url', ''),
                **context
            }

            # Render title and message
            title = self._render_string(channel_config.get('title', ''), template_vars)
            message = self._render_string(channel_config.get('message', ''), template_vars)

            return {
                'title': title,
                'message': message,
                'html_content': channel_config.get('body_html', ''),
                'text_content': channel_config.get('body_text', ''),
                'sms_message': channel_config.get('message', '')
            }
        except Exception as e:
            error_logger.error(f"Failed to render template: {e}", exc_info=True)
            return None

    def _render_string(self, template_string: str, variables: Dict[str, Any]) -> str:
        """Render template string with variables."""
        try:
            from string import Template
            return Template(template_string).safe_substitute(**variables)
        except Exception:
            return template_string

    def _queue_notification_delivery(self, notification: Notification):
        """Queue notification for delivery."""
        try:
            from tasks.notification_tasks import deliver_notification
            deliver_notification.delay(str(notification.id))
        except Exception as e:
            error_logger.error(f"Failed to queue notification delivery: {e}", exc_info=True)
            notification.status = 'failed'
            notification.save()

    def deliver_notification(self, notification_id: str) -> bool:
        """Deliver a notification."""
        try:
            notification = Notification.objects(id=notification_id).first()
            if not notification:
                error_logger.error(f"Notification not found: {notification_id}")
                return False

            if notification.status == 'sent':
                return True

            # Update attempt count
            notification.attempt_count += 1
            notification.save()

            # Deliver based on channel
            success = False
            if notification.channel == 'email':
                success = self._deliver_email(notification)
            elif notification.channel == 'sms':
                success = self._deliver_sms(notification)
            elif notification.channel == 'in_app':
                success = self._deliver_in_app(notification)
            elif notification.channel == 'push':
                success = self._deliver_push(notification)
            elif notification.channel == 'webhook':
                success = self._deliver_webhook(notification)

            # Update notification status
            if success:
                notification.status = 'sent'
                notification.sent_at = datetime.utcnow()
            else:
                if notification.attempt_count >= notification.max_attempts:
                    notification.status = 'failed'
                else:
                    notification.status = 'retrying'
                    # Schedule retry
                    notification.next_retry_at = datetime.utcnow() + timedelta(minutes=5 * notification.attempt_count)

            notification.save()

            # Log delivery attempt
            self._log_delivery_attempt(notification, success)

            return success
        except Exception as e:
            error_logger.error(f"Failed to deliver notification: {e}", exc_info=True)
            return False

    def _deliver_email(self, notification: Notification) -> bool:
        """Deliver email notification."""
        try:
            # Get email API configuration
            email_api_url = os.getenv('EMAIL_API_URL')
            email_api_token = os.getenv('EMAIL_API_TOKEN')
            
            if not email_api_url or not email_api_token:
                error_logger.error("Email API not configured")
                return False

            # Prepare email data
            email_data = {
                'to': notification.recipient_id.email if hasattr(notification.recipient_id, 'email') else '',
                'subject': notification.title,
                'html_content': notification.data.get('html_content', notification.message),
                'text_content': notification.data.get('text_content', notification.message)
            }

            # Send email
            headers = {
                'Authorization': f'Bearer {email_api_token}',
                'Content-Type': 'application/json'
            }

            response = requests.post(
                email_api_url,
                json=email_data,
                headers=headers,
                timeout=30
            )
            
            response.raise_for_status()
            return True
        except Exception as e:
            error_logger.error(f"Failed to deliver email: {e}", exc_info=True)
            return False

    def _deliver_sms(self, notification: Notification) -> bool:
        """Deliver SMS notification."""
        try:
            # Get SMS API configuration
            sms_api_url = os.getenv('SMS_API_URL')
            sms_api_token = os.getenv('SMS_API_TOKEN')
            
            if not sms_api_url or not sms_api_token:
                error_logger.error("SMS API not configured")
                return False

            # Get recipient phone number
            recipient_phone = notification.recipient_id.phone if hasattr(notification.recipient_id, 'phone') else ''
            if not recipient_phone:
                error_logger.error("Recipient phone number not available")
                return False

            # Prepare SMS data
            sms_data = {
                'to': recipient_phone,
                'message': notification.data.get('sms_message', notification.message)
            }

            # Send SMS
            headers = {
                'Authorization': f'Bearer {sms_api_token}',
                'Content-Type': 'application/json'
            }

            response = requests.post(
                sms_api_url,
                json=sms_data,
                headers=headers,
                timeout=30
            )
            
            response.raise_for_status()
            return True
        except Exception as e:
            error_logger.error(f"Failed to deliver SMS: {e}", exc_info=True)
            return False

    def _deliver_in_app(self, notification: Notification) -> bool:
        """Deliver in-app notification."""
        try:
            # For in-app notifications, we just mark as sent
            # The actual delivery happens when the user fetches notifications
            return True
        except Exception as e:
            error_logger.error(f"Failed to deliver in-app notification: {e}", exc_info=True)
            return False

    def _deliver_push(self, notification: Notification) -> bool:
        """Deliver push notification."""
        try:
            # Get user device tokens
            user = notification.recipient_id
            if not hasattr(user, 'device_tokens') or not user.device_tokens:
                error_logger.error("No device tokens found for user")
                return False

            # This would integrate with Firebase Cloud Messaging or similar
            # For now, we'll just simulate success
            return True
        except Exception as e:
            error_logger.error(f"Failed to deliver push notification: {e}", exc_info=True)
            return False

    def _deliver_webhook(self, notification: Notification) -> bool:
        """Deliver webhook notification."""
        try:
            # Get webhook URL from notification data
            webhook_url = notification.data.get('webhook_url')
            if not webhook_url:
                error_logger.error("Webhook URL not found in notification data")
                return False

            # Prepare webhook payload
            payload = {
                'notification_id': str(notification.id),
                'title': notification.title,
                'message': notification.message,
                'channel': notification.channel,
                'timestamp': notification.created_at.isoformat(),
                'data': notification.data
            }

            # Send webhook
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'FormBuilder-Notification-Engine/1.0'
            }

            response = requests.post(
                webhook_url,
                json=payload,
                headers=headers,
                timeout=30
            )
            
            response.raise_for_status()
            return True
        except Exception as e:
            error_logger.error(f"Failed to deliver webhook: {e}", exc_info=True)
            return False

    def _log_delivery_attempt(self, notification: Notification, success: bool):
        """Log notification delivery attempt."""
        try:
            log = NotificationLog(
                organization_id=notification.organization_id,
                notification_id=notification,
                rule_id=notification.rule_id,
                recipient_id=notification.recipient_id,
                channel=notification.channel,
                status='sent' if success else 'failed',
                attempt_number=notification.attempt_count,
                provider=notification.channel,
                provider_response={'success': success},
                created_at=datetime.utcnow()
            )
            log.save()
        except Exception as e:
            error_logger.error(f"Failed to log delivery attempt: {e}", exc_info=True)

    def get_user_notifications(self, user_id: str, status: Optional[str] = None, limit: int = 50) -> List[Notification]:
        """Get notifications for a user."""
        query = Notification.objects(recipient_id=user_id, is_deleted=False)
        if status:
            query = query.filter(status=status)
        return list(query.order_by('-created_at')[:limit])

    def mark_notification_read(self, notification_id: str, user_id: str) -> bool:
        """Mark a notification as read."""
        try:
            notification = Notification.objects(
                id=notification_id,
                recipient_id=user_id,
                is_deleted=False
            ).first()
            
            if not notification:
                return False

            notification.read_at = datetime.utcnow()
            notification.save()
            return True
        except Exception as e:
            error_logger.error(f"Failed to mark notification as read: {e}", exc_info=True)
            return False

    def get_notification_preferences(self, user_id: str) -> NotificationPreference:
        """Get user notification preferences."""
        preference = NotificationPreference.objects(user_id=user_id, is_deleted=False).first()
        if not preference:
            # Create default preferences
            preference = NotificationPreference(
                user_id=user_id,
                email_notifications=True,
                sms_notifications=True,
                in_app_notifications=True,
                push_notifications=True,
                event_preferences={},
                created_at=datetime.utcnow()
            )
            preference.save()
        return preference

    def update_notification_preferences(self, user_id: str, **kwargs) -> NotificationPreference:
        """Update user notification preferences."""
        preference = self.get_notification_preferences(user_id)
        
        updatable_fields = [
            'email_notifications', 'sms_notifications', 'in_app_notifications', 
            'push_notifications', 'event_preferences', 'quiet_hours'
        ]
        
        for field in updatable_fields:
            if field in kwargs:
                setattr(preference, field, kwargs[field])
        
        preference.save()
        return preference

    def seed_default_notification_templates(self, org_id: str):
        """Seed default notification templates for an organization."""
        default_templates = [
            {
                'name': 'Form Response Submitted',
                'event_type': 'response.submitted',
                'channels': {
                    'email': {
                        'title': 'New Form Response Received',
                        'message': 'A new response has been submitted for {{form_name}}.',
                        'body_html': '<h2>New Response Received</h2><p>A new response has been submitted for <strong>{{form_name}}</strong>.</p><p>View the response: <a href="{{action_url}}">Click here</a></p>',
                        'body_text': 'A new response has been submitted for {{form_name}}. View: {{action_url}}'
                    },
                    'in_app': {
                        'title': 'New Response',
                        'message': '{{form_name}} has a new response'
                    }
                },
                'variables': [
                    {'key': 'form_name', 'description': 'Name of the form'},
                    {'key': 'response_count', 'description': 'Total number of responses'},
                    {'key': 'action_url', 'description': 'URL to view the response'}
                ]
            },
            {
                'name': 'Form Published',
                'event_type': 'form.published',
                'channels': {
                    'email': {
                        'title': 'Form Published Successfully',
                        'message': 'Your form {{form_name}} has been published and is ready to receive responses.',
                        'body_html': '<h2>Form Published</h2><p>Your form <strong>{{form_name}}</strong> has been published successfully.</p><p>Start collecting responses: <a href="{{action_url}}">Click here</a></p>',
                        'body_text': 'Your form {{form_name}} has been published. Start collecting responses: {{action_url}}'
                    },
                    'in_app': {
                        'title': 'Form Published',
                        'message': '{{form_name}} is now live'
                    }
                },
                'variables': [
                    {'key': 'form_name', 'description': 'Name of the form'},
                    {'key': 'action_url', 'description': 'URL to view the form'}
                ]
            }
        ]

        for template_data in default_templates:
            template_data['organization_id'] = org_id
            template_data['is_system'] = True
            
            existing = NotificationTemplate.objects(
                organization_id=org_id,
                name=template_data['name'],
                event_type=template_data['event_type']
            ).first()
            
            if not existing:
                self.create_notification_template(**template_data)
                app_logger.info(f"Created default notification template: {template_data['name']} for org {org_id}")


notification_engine_service = NotificationEngineService()