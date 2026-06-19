import os
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

        if not url:
            app_logger.warning("No URL specified for webhook trigger")
            return

        app_logger.info(f"Delivering webhook: {method} {url}")
        try:
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
