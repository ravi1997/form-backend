import os
from datetime import datetime
from typing import List, Dict, Any, Union
import requests
from logger.unified_logger import app_logger, error_logger, audit_logger
from models.components import Trigger
from utils.script_engine import execute_safe_script


class NotificationService:
    """
    Handles execution of Triggers (Webhooks, Emails, API Calls).
    Decouples trigger logic from the model save() methods for performance.
    """

    @staticmethod
    def execute_triggers(
        triggers: List[Union[Trigger, Dict[str, Any]]], context_data: Dict[str, Any]
    ):
        """
        Enqueues each active trigger as an individual background task.
        """
        app_logger.info(
            f"Executing triggers for context: {context_data.get('source', 'unknown')}"
        )
        from tasks.notification_tasks import process_single_trigger

        try:
            for trigger in triggers:
                # Handle both Trigger objects and serialized dictionaries
                trigger_dict = (
                    trigger.to_mongo().to_dict()
                    if hasattr(trigger, "to_mongo")
                    else trigger
                )

                if not trigger_dict.get("is_active", True):
                    app_logger.debug(
                        f"Skipping inactive trigger: {trigger_dict.get('name')}"
                    )
                    continue

                app_logger.info(
                    f"Enqueuing trigger: {trigger_dict.get('name')} ({trigger_dict.get('action_type')})"
                )
                process_single_trigger.delay(trigger_dict, context_data)
        except Exception as e:
            error_logger.error(f"Error enqueuing triggers: {str(e)}", exc_info=True)

    @staticmethod
    def _call_webhook(config: Dict, data: Dict):
        url = config.get("url")
        method = config.get("method", "POST").upper()
        headers = config.get("headers", {})
        secret = config.get("secret")

        if not url:
            app_logger.warning("No URL specified for webhook trigger")
            return

        app_logger.info(f"Delivering webhook: {method} {url}")
        try:
            # Add HMAC signature if secret is provided
            if secret:
                signature = NotificationService._generate_hmac_signature(secret, data)
                headers['X-Webhook-Signature'] = f'sha256={signature}'
            
            response = requests.request(
                method, url, json=data, headers=headers, timeout=30
            )
            response.raise_for_status()
            app_logger.info(f"Webhook delivered successfully: {response.status_code}")
        except requests.RequestException as e:
            error_logger.error(
                f"Webhook delivery failed for {url}: {str(e)}", exc_info=True
            )

    @staticmethod
    def _call_external_api(config: Dict, data: Dict):
        """
        Deliver a notification payload to the configured AIIMS email endpoint.

        Expected config keys:
        - url: optional full endpoint override
        - method: defaults to POST
        - headers: optional extra headers
        - path: optional path appended to the base URL
        - payload: optional payload template merged with context data
        """
        base_url = (
            config.get("url")
            or os.getenv("AIIMS_EMAIL_API_URL")
            or os.getenv("EMAIL_API_URL")
        )
        method = config.get("method", "POST").upper()
        headers = {"Content-Type": "application/json"}
        headers.update(config.get("headers", {}))
        token = (
            config.get("token")
            or os.getenv("AIIMS_EMAIL_API_TOKEN")
            or os.getenv("EMAIL_API_TOKEN")
        )
        if token:
            headers.setdefault("Authorization", f"Bearer {token}")

        if not base_url:
            message = "AIIMS email API is not configured"
            error_logger.error(message)
            raise RuntimeError(message)

        payload = dict(config.get("payload", {}))
        payload.update(data)
        path = config.get("path", "").strip()
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}" if path else base_url.rstrip("/")

        app_logger.info(f"External API call triggered: {method} {url}")
        try:
            response = requests.request(
                method,
                url,
                json=payload,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            try:
                result = response.json()
            except ValueError:
                result = {"status_code": response.status_code}

            audit_logger.info(
                f"AIIMS email sent successfully via {url}, status_code={response.status_code}"
            )
            return result
        except requests.RequestException as e:
            error_logger.error(
                f"AIIMS email delivery failed for {url}: {str(e)}", exc_info=True
            )
            raise

    @staticmethod
    def _run_custom_logic(script: str, data: Dict):
        """
        Execute a small expression-only script safely.
        This keeps the existing execute_script notification path usable without
        enabling arbitrary code execution.
        """
        app_logger.info("Executing safe custom notification logic")
        result = execute_safe_script(script or "", input_data=data or {})
        audit_logger.info(
            "Custom notification logic executed",
            extra={"event": "notification_custom_logic", "result": result.get("result")},
        )
        return result

    @staticmethod
    def _generate_hmac_signature(secret: str, payload: Dict) -> str:
        """
        Generate HMAC SHA-256 signature for webhook payload.
        """
        import hmac
        import hashlib
        import json
        
        if isinstance(payload, dict):
            payload = json.dumps(payload, sort_keys=True)
        
        secret = secret.encode('utf-8')
        payload = payload.encode('utf-8')
        
        signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        return signature

    @staticmethod
    def send_quota_warning_notification(org_id: str, threshold: float, usage_ratio: float, 
                                      used_bytes: int, quota_bytes: int):
        """
        Send quota warning notification to organization administrators.
        """
        try:
            from models.identity import Organization, User
            from models.oauth import NotificationRule
            
            # Get organization details
            org = Organization.objects(id=org_id).first()
            if not org:
                return
            
            # Get organization administrators
            admin_users = User.objects(
                org_memberships__org_id=org_id,
                org_memberships__role='org_admin',
                status='active'
            )
            
            # Create notification context
            context_data = {
                'org_id': org_id,
                'org_name': org.name,
                'threshold': threshold,
                'usage_ratio': usage_ratio,
                'used_bytes': used_bytes,
                'quota_bytes': quota_bytes,
                'used_mb': used_bytes / (1024 * 1024),
                'quota_mb': quota_bytes / (1024 * 1024),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Send email notification to admins
            for admin in admin_users:
                email_data = {
                    'to': admin.email,
                    'subject': f'Storage Quota Warning - {org.name}',
                    'body': f'''
                    Dear {admin.full_name or admin.email},
                    
                    Your organization {org.name} has reached {threshold:.0%} of its storage quota.
                    
                    Current Usage: {used_bytes / (1024 * 1024):.1f} MB
                    Quota Limit: {quota_bytes / (1024 * 1024):.1f} MB
                    Usage Percentage: {usage_ratio:.1%}
                    
                    Please consider upgrading your storage plan or cleaning up unused files.
                    
                    Thank you,
                    Form Builder Team
                    '''
                }
                
                # Queue email notification
                from tasks.notification_tasks import process_single_trigger
                trigger_dict = {
                    'id': f'quota_warning_{org_id}',
                    'action_type': 'email',
                    'config': email_data
                }
                
                process_single_trigger.delay(trigger_dict, context_data)
            
            audit_logger.info(f"Quota warning notification sent for org {org_id} at {usage_ratio:.1%}")
            
        except Exception as e:
            error_logger.error(f"Error sending quota warning notification: {e}")

    @staticmethod
    def send_quota_updated_notification(org_id: str, old_quota: int, new_quota: int):
        """
        Send notification when quota is updated.
        """
        try:
            from models.identity import Organization, User
            
            # Get organization details
            org = Organization.objects(id=org_id).first()
            if not org:
                return
            
            # Get organization administrators
            admin_users = User.objects(
                org_memberships__org_id=org_id,
                org_memberships__role='org_admin',
                status='active'
            )
            
            # Create notification context
            context_data = {
                'org_id': org_id,
                'org_name': org.name,
                'old_quota': old_quota,
                'new_quota': new_quota,
                'old_quota_mb': old_quota / (1024 * 1024),
                'new_quota_mb': new_quota / (1024 * 1024),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Send email notification to admins
            for admin in admin_users:
                email_data = {
                    'to': admin.email,
                    'subject': f'Storage Quota Updated - {org.name}',
                    'body': f'''
                    Dear {admin.full_name or admin.email},
                    
                    Your organization {org.name} storage quota has been updated.
                    
                    Previous Quota: {old_quota / (1024 * 1024):.1f} MB
                    New Quota: {new_quota / (1024 * 1024):.1f} MB
                    
                    Thank you,
                    Form Builder Team
                    '''
                }
                
                # Queue email notification
                from tasks.notification_tasks import process_single_trigger
                trigger_dict = {
                    'id': f'quota_updated_{org_id}',
                    'action_type': 'email',
                    'config': email_data
                }
                
                process_single_trigger.delay(trigger_dict, context_data)
            
            audit_logger.info(f"Quota update notification sent for org {org_id}: {old_quota} -> {new_quota}")
            
        except Exception as e:
            error_logger.error(f"Error sending quota update notification: {e}")


class NotificationObservability:
    @staticmethod
    def increment_attempt(action_type: str):
        try:
            from extensions import redis_client
            redis_client.incr("notification:metrics:total_attempts")
            redis_client.incr(f"notification:metrics:attempts:{action_type}")
        except Exception:
            pass

    @staticmethod
    def increment_success(action_type: str):
        try:
            from extensions import redis_client
            redis_client.incr("notification:metrics:success")
            redis_client.incr(f"notification:metrics:success:{action_type}")
        except Exception:
            pass

    @staticmethod
    def increment_failure(action_type: str):
        try:
            from extensions import redis_client
            redis_client.incr("notification:metrics:failed")
            redis_client.incr(f"notification:metrics:failed:{action_type}")
        except Exception:
            pass

    @staticmethod
    def increment_retry(action_type: str):
        try:
            from extensions import redis_client
            redis_client.incr("notification:metrics:retries")
            redis_client.incr(f"notification:metrics:retries:{action_type}")
        except Exception:
            pass

    @staticmethod
    def get_metrics() -> dict:
        try:
            from extensions import redis_client
            keys = [
                "notification:metrics:total_attempts",
                "notification:metrics:success",
                "notification:metrics:failed",
                "notification:metrics:retries"
            ]
            vals = redis_client.mget(keys)
            metrics = {keys[i].split(":")[-1]: int(v) if v else 0 for i, v in enumerate(vals)}
            return metrics
        except Exception:
            return {}


notification_service = NotificationService()
