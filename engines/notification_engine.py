"""
engines/notification_engine.py
Notification engine for handling email, SMS, in-app, and webhook notifications.
Provides templating, delivery, and retry logic with proper error handling.
"""

import json
import logging
import requests
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List, Optional, Union
from jinja2 import Template
import re

from models.notification import (
    NotificationTemplate, NotificationRule, NotificationLog,
    WebhookConfig, WebhookDeliveryLog
)
from services.notification_service import NotificationService
from utils.exceptions import NotificationError, ValidationError
from logger.unified_logger import audit_logger, app_logger

logger = logging.getLogger(__name__)


class NotificationEngine:
    """
    Notification engine for handling all types of notifications with templating
    and delivery management.
    """
    
    def __init__(self):
        self.notification_service = NotificationService()
        self.email_config = None
        self.sms_config = None
        self._load_config()
        
    def _load_config(self):
        """Load email and SMS configuration from system config."""
        # In a real implementation, this would load from database or environment
        self.email_config = {
            'smtp_host': 'smtp.example.com',
            'smtp_port': 587,
            'smtp_username': 'notifications@example.com',
            'smtp_password': 'password',
            'from_email': 'notifications@example.com',
            'from_name': 'MahaSangrah Setu'
        }
        
        self.sms_config = {
            'api_url': 'https://rpcapplication.aiims.edu/services/api/v1/sms/single',
            'api_token': 'your-sms-token'
        }
    
    def send_notification(
        self,
        rule_id: str,
        organization_id: str,
        event_data: Dict[str, Any],
        recipient_data: Dict[str, Any] = None
    ) -> List[NotificationLog]:
        """
        Send notification based on a rule.
        
        Args:
            rule_id: Notification rule ID
            organization_id: Organization ID
            event_data: Event data for template variables
            recipient_data: Additional recipient data
            
        Returns:
            List of notification log entries
            
        Raises:
            ValidationError: If rule not found or invalid
            NotificationError: If sending fails
        """
        try:
            # Get notification rule
            rule = NotificationRule.objects(
                id=rule_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not rule:
                raise ValidationError(f"Notification rule not found: {rule_id}")
            
            if not rule.is_active:
                logger.info(f"Notification rule {rule_id} is inactive, skipping")
                return []
            
            # Check trigger conditions
            if not self._evaluate_trigger_conditions(rule, event_data):
                logger.info(f"Trigger conditions not met for rule {rule_id}")
                return []
            
            # Get recipients
            recipients = self._get_recipients(rule, event_data, recipient_data)
            if not recipients:
                logger.info(f"No recipients found for rule {rule_id}")
                return []
            
            # Get template
            template = NotificationTemplate.objects(
                id=rule.template_id,
                organization_id__in=[organization_id, None],  # Allow system templates
                is_active=True
            ).first()
            
            if not template:
                raise ValidationError(f"Template not found: {rule.template_id}")
            
            # Send notifications
            logs = []
            for channel in rule.channels:
                for recipient in recipients:
                    try:
                        log = self._send_channel_notification(
                            channel=channel,
                            template=template,
                            recipient=recipient,
                            event_data=event_data,
                            rule=rule,
                            organization_id=organization_id
                        )
                        logs.append(log)
                    except Exception as e:
                        logger.error(f"Failed to send {channel} notification: {str(e)}")
                        # Create failed log entry
                        logs.append(NotificationLog(
                            rule_id=rule_id,
                            organization_id=organization_id,
                            event_type=rule.event_type,
                            recipient_id=recipient.get('id'),
                            channel=channel,
                            status='failed',
                            error_message=str(e)
                        ))
            
            audit_logger.info(
                f"AUDIT: Sent notifications for rule {rule_id}, "
                f"channels: {rule.channels}, recipients: {len(recipients)}"
            )
            
            return logs
            
        except Exception as e:
            logger.error(f"Failed to send notification for rule {rule_id}: {str(e)}", exc_info=True)
            raise NotificationError(f"Notification sending failed: {str(e)}")
    
    def _evaluate_trigger_conditions(self, rule: NotificationRule, event_data: Dict[str, Any]) -> bool:
        """Evaluate trigger conditions for a notification rule."""
        # Simple implementation - in real system would support complex conditions
        conditions = rule.trigger_conditions or []
        
        for condition in conditions:
            field = condition.get('field')
            operator = condition.get('operator')
            value = condition.get('value')
            
            if field not in event_data:
                return False
            
            event_value = event_data[field]
            
            if operator == 'equals':
                if event_value != value:
                    return False
            elif operator == 'contains':
                if value not in str(event_value):
                    return False
            elif operator == 'in':
                if event_value not in value:
                    return False
        
        return True
    
    def _get_recipients(
        self,
        rule: NotificationRule,
        event_data: Dict[str, Any],
        recipient_data: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Get recipients for notification based on rule configuration."""
        recipient_type = rule.recipient_type
        
        if recipient_type == 'form_owner':
            # Get form owner from event data
            form_id = event_data.get('form_id')
            if form_id:
                # In real implementation, query form to get owner
                return [{'id': 'form_owner', 'email': 'owner@example.com'}]
        
        elif recipient_type == 'specific_users':
            return rule.recipient_ids or []
        
        elif recipient_type == 'role':
            # Get users with specified role
            role = rule.recipient_ids[0] if rule.recipient_ids else 'admin'
            # In real implementation, query users by role
            return [{'id': f'user_{role}', 'email': f'{role}@example.com'}]
        
        elif recipient_type == 'group':
            # Get users in specified group
            group_id = rule.recipient_ids[0] if rule.recipient_ids else None
            # In real implementation, query users by group
            return [{'id': f'group_{group_id}', 'email': f'group@example.com'}]
        
        elif recipient_type == 'respondent':
            # Get respondent from event data
            respondent_id = event_data.get('respondent_id')
            if respondent_id:
                return [{'id': respondent_id, 'email': event_data.get('respondent_email')}]
        
        return []
    
    def _send_channel_notification(
        self,
        channel: str,
        template: NotificationTemplate,
        recipient: Dict[str, Any],
        event_data: Dict[str, Any],
        rule: NotificationRule,
        organization_id: str
    ) -> NotificationLog:
        """Send notification through specific channel."""
        # Prepare template variables
        template_vars = self._prepare_template_variables(template, event_data, recipient)
        
        if channel == 'email':
            return self._send_email_notification(template, template_vars, recipient, rule, organization_id)
        elif channel == 'sms':
            return self._send_sms_notification(template, template_vars, recipient, rule, organization_id)
        elif channel == 'in_app':
            return self._send_in_app_notification(template, template_vars, recipient, rule, organization_id)
        elif channel == 'webhook':
            return self._send_webhook_notification(template, template_vars, recipient, rule, organization_id)
        else:
            raise ValueError(f"Unsupported notification channel: {channel}")
    
    def _prepare_template_variables(
        self,
        template: NotificationTemplate,
        event_data: Dict[str, Any],
        recipient: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepare template variables from event data and recipient info."""
        variables = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'recipient': recipient,
            'event': event_data
        }
        
        # Add default variables
        default_vars = {
            'user_name': recipient.get('name', recipient.get('email', 'User')),
            'user_email': recipient.get('email', ''),
            'organization_name': event_data.get('organization_name', 'Organization'),
            'project_name': event_data.get('project_name', 'Project'),
            'form_name': event_data.get('form_name', 'Form'),
            'response_count': event_data.get('response_count', 0),
            'action_url': event_data.get('action_url', ''),
            'actor_name': event_data.get('actor_name', 'System'),
            'entity_type': event_data.get('entity_type', 'Item'),
            'entity_name': event_data.get('entity_name', 'Item')
        }
        
        variables.update(default_vars)
        
        # Add custom variables from template
        for var_def in template.variables or []:
            key = var_def.get('key')
            if key and key not in variables:
                variables[key] = event_data.get(key, '')
        
        return variables
    
    def _send_email_notification(
        self,
        template: NotificationTemplate,
        variables: Dict[str, Any],
        recipient: Dict[str, Any],
        rule: NotificationRule,
        organization_id: str
    ) -> NotificationLog:
        """Send email notification."""
        try:
            # Render email content
            subject = Template(template.channels['email']['subject']).render(**variables)
            body_html = Template(template.channels['email']['body_html']).render(**variables)
            body_text = Template(template.channels['email']['body_text']).render(**variables)
            
            # Create email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.email_config['from_name']} <{self.email_config['from_email']}>"
            msg['To'] = recipient['email']
            
            # Add HTML and text parts
            msg.attach(MIMEText(body_text, 'plain'))
            msg.attach(MIMEText(body_html, 'html'))
            
            # Send email
            with smtplib.SMTP(self.email_config['smtp_host'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['smtp_username'], self.email_config['smtp_password'])
                server.send_message(msg)
            
            # Create log entry
            log = NotificationLog(
                rule_id=str(rule.id),
                organization_id=organization_id,
                event_type=rule.event_type,
                recipient_id=recipient.get('id'),
                channel='email',
                status='sent',
                provider_response={'message': 'Email sent successfully'}
            )
            log.save()
            
            logger.info(f"Email sent to {recipient['email']}")
            return log
            
        except Exception as e:
            logger.error(f"Failed to send email to {recipient['email']}: {str(e)}", exc_info=True)
            
            # Create failed log entry
            log = NotificationLog(
                rule_id=str(rule.id),
                organization_id=organization_id,
                event_type=rule.event_type,
                recipient_id=recipient.get('id'),
                channel='email',
                status='failed',
                error_message=str(e)
            )
            log.save()
            
            raise NotificationError(f"Failed to send email: {str(e)}")
    
    def _send_sms_notification(
        self,
        template: NotificationTemplate,
        variables: Dict[str, Any],
        recipient: Dict[str, Any],
        rule: NotificationRule,
        organization_id: str
    ) -> NotificationLog:
        """Send SMS notification."""
        try:
            # Render SMS message
            message = Template(template.channels['sms']['message']).render(**variables)
            
            # Send SMS via API
            headers = {
                'Authorization': f'Bearer {self.sms_config["api_token"]}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'to': recipient.get('phone', recipient.get('mobile')),
                'message': message
            }
            
            response = requests.post(
                self.sms_config['api_url'],
                headers=headers,
                json=payload,
                timeout=30
            )
            
            response.raise_for_status()
            
            # Create log entry
            log = NotificationLog(
                rule_id=str(rule.id),
                organization_id=organization_id,
                event_type=rule.event_type,
                recipient_id=recipient.get('id'),
                channel='sms',
                status='sent',
                provider_response=response.json()
            )
            log.save()
            
            logger.info(f"SMS sent to {recipient.get('phone')}")
            return log
            
        except Exception as e:
            logger.error(f"Failed to send SMS to {recipient.get('phone')}: {str(e)}", exc_info=True)
            
            # Create failed log entry
            log = NotificationLog(
                rule_id=str(rule.id),
                organization_id=organization_id,
                event_type=rule.event_type,
                recipient_id=recipient.get('id'),
                channel='sms',
                status='failed',
                error_message=str(e)
            )
            log.save()
            
            raise NotificationError(f"Failed to send SMS: {str(e)}")
    
    def _send_in_app_notification(
        self,
        template: NotificationTemplate,
        variables: Dict[str, Any],
        recipient: Dict[str, Any],
        rule: NotificationRule,
        organization_id: str
    ) -> NotificationLog:
        """Send in-app notification."""
        try:
            # Render notification content
            title = Template(template.channels['in_app']['title']).render(**variables)
            body = Template(template.channels['in_app']['body']).render(**variables)
            
            # In real implementation, would store in database for user to see
            # For now, just create log entry
            log = NotificationLog(
                rule_id=str(rule.id),
                organization_id=organization_id,
                event_type=rule.event_type,
                recipient_id=recipient.get('id'),
                channel='in_app',
                status='sent',
                provider_response={
                    'title': title,
                    'body': body,
                    'delivered_at': datetime.now(timezone.utc).isoformat()
                }
            )
            log.save()
            
            logger.info(f"In-app notification sent to {recipient.get('id')}")
            return log
            
        except Exception as e:
            logger.error(f"Failed to send in-app notification to {recipient.get('id')}: {str(e)}", exc_info=True)
            
            # Create failed log entry
            log = NotificationLog(
                rule_id=str(rule.id),
                organization_id=organization_id,
                event_type=rule.event_type,
                recipient_id=recipient.get('id'),
                channel='in_app',
                status='failed',
                error_message=str(e)
            )
            log.save()
            
            raise NotificationError(f"Failed to send in-app notification: {str(e)}")
    
    def _send_webhook_notification(
        self,
        template: NotificationTemplate,
        variables: Dict[str, Any],
        recipient: Dict[str, Any],
        rule: NotificationRule,
        organization_id: str
    ) -> WebhookDeliveryLog:
        """Send webhook notification."""
        try:
            # Get webhook configuration
            webhook_config = WebhookConfig.objects(
                id=rule.recipient_ids[0] if rule.recipient_ids else None,
                organization_id=organization_id,
                is_active=True
            ).first()
            
            if not webhook_config:
                raise ValidationError("Webhook configuration not found")
            
            # Prepare webhook payload
            payload = {
                'event': rule.event_type,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'data': variables,
                'recipient': recipient
            }
            
            # Add HMAC signature if secret is configured
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'MahaSangrah-Setu-Webhook/1.0'
            }
            
            if webhook_config.secret:
                import hmac
                import hashlib
                
                payload_json = json.dumps(payload, sort_keys=True)
                signature = hmac.new(
                    webhook_config.secret.encode(),
                    payload_json.encode(),
                    hashlib.sha256
                ).hexdigest()
                
                headers['X-Webhook-Signature'] = f'sha256={signature}'
            
            # Send webhook
            response = requests.post(
                webhook_config.url,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            # Create delivery log
            log = WebhookDeliveryLog(
                webhook_config_id=str(webhook_config.id),
                organization_id=organization_id,
                event_type=rule.event_type,
                payload=payload,
                status='delivered' if response.status_code < 400 else 'failed',
                http_status_code=response.status_code,
                response_body=response.text if response.text else None
            )
            log.save()
            
            logger.info(f"Webhook sent to {webhook_config.url}, status: {response.status_code}")
            return log
            
        except Exception as e:
            logger.error(f"Failed to send webhook: {str(e)}", exc_info=True)
            
            # Create failed delivery log
            log = WebhookDeliveryLog(
                webhook_config_id=str(rule.recipient_ids[0]) if rule.recipient_ids else None,
                organization_id=organization_id,
                event_type=rule.event_type,
                payload={},
                status='failed',
                error_message=str(e)
            )
            log.save()
            
            raise NotificationError(f"Failed to send webhook: {str(e)}")
    
    def retry_failed_notifications(self, max_attempts: int = 3) -> int:
        """
        Retry failed notifications.
        
        Args:
            max_attempts: Maximum number of retry attempts
            
        Returns:
            Number of notifications retried
        """
        retry_count = 0
        
        # Get failed notifications that haven't exceeded max attempts
        failed_logs = NotificationLog.objects(
            status='failed',
            attempt_count__lt=max_attempts
        ).order_by('created_at')
        
        for log in failed_logs:
            try:
                # Calculate retry delay with exponential backoff
                delay_seconds = min(60 * (2 ** log.attempt_count), 3600)  # Max 1 hour
                
                if log.created_at + timedelta(seconds=delay_seconds) > datetime.now(timezone.utc):
                    continue  # Not time to retry yet
                
                # Get the original rule and template
                rule = NotificationRule.objects(id=log.rule_id).first()
                if not rule or not rule.is_active:
                    continue
                
                template = NotificationTemplate.objects(id=rule.template_id).first()
                if not template or not template.is_active:
                    continue
                
                # Resend notification
                self._send_channel_notification(
                    channel=log.channel,
                    template=template,
                    recipient={'id': log.recipient_id},
                    event_data={},  # We don't have original event data
                    rule=rule,
                    organization_id=log.organization_id
                )
                
                # Update attempt count
                log.attempt_count += 1
                log.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds * 2)
                log.save()
                
                retry_count += 1
                
            except Exception as e:
                logger.error(f"Failed to retry notification {log.id}: {str(e)}")
        
        audit_logger.info(f"AUDIT: Retried {retry_count} failed notifications")
        return retry_count
    
    def create_notification_template(
        self,
        organization_id: str,
        name: str,
        event_type: str,
        channels: Dict[str, Dict[str, str]],
        variables: List[Dict[str, Any]] = None
    ) -> NotificationTemplate:
        """
        Create a new notification template.
        
        Args:
            organization_id: Organization ID
            name: Template name
            event_type: Event type
            channels: Channel configurations
            variables: Template variable definitions
            
        Returns:
            Created template
        """
        template = NotificationTemplate(
            organization_id=organization_id,
            name=name,
            event_type=event_type,
            channels=channels,
            variables=variables or []
        )
        template.save()
        
        audit_logger.info(f"AUDIT: Created notification template {template.id} for org {organization_id}")
        return template