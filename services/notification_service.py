from typing import List, Dict, Any, Union
import requests
from logger.unified_logger import app_logger, error_logger, audit_logger
from models.components import Trigger

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
        app_logger.info(f"Executing triggers for context: {context_data.get('source', 'unknown')}")
        from tasks.notification_tasks import process_single_trigger
        
        try:
            for trigger in triggers:
                # Handle both Trigger objects and serialized dictionaries
                trigger_dict = trigger.to_mongo().to_dict() if hasattr(trigger, 'to_mongo') else trigger
                
                if not trigger_dict.get("is_active", True):
                    app_logger.debug(f"Skipping inactive trigger: {trigger_dict.get('name')}")
                    continue

                app_logger.info(f"Enqueuing trigger: {trigger_dict.get('name')} ({trigger_dict.get('action_type')})")
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
                method, url, json=data, headers=headers, timeout=5
            )
            response.raise_for_status()
            app_logger.info(f"Webhook delivered successfully: {response.status_code}")
        except requests.RequestException as e:
            error_logger.error(f"Webhook delivery failed for {url}: {str(e)}", exc_info=True)

    @staticmethod
    def _call_external_api(config: Dict, data: Dict):
        # Specific business logic for internal/integrated API calls
        app_logger.info(f"External API call triggered with config: {config}")
        # Not yet implemented
        error_logger.error("External API call not implemented")
        raise NotImplementedError("External API call not implemented")

    @staticmethod
    def _run_custom_logic(script: str, data: Dict):
        """
        SAFE execution of dynamic scripts.
        In production, this should use a restricted sandbox (like PyExecJS or a secure eval).
        """
        app_logger.warning("Attempted custom script execution")
        error_logger.error("Custom script execution blocked for security reasons.")
        raise NotImplementedError("Custom scripts are disabled for security reasons.")
