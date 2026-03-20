from typing import List, Dict, Any, Union
import requests
from logger import get_logger, error_logger
from models.components import Trigger

logger = get_logger(__name__)


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
        from tasks.notification_tasks import process_single_trigger
        
        for trigger in triggers:
            # Handle both Trigger objects and serialized dictionaries
            trigger_dict = trigger.to_mongo().to_dict() if hasattr(trigger, 'to_mongo') else trigger
            
            if not trigger_dict.get("is_active", True):
                continue

            logger.info(f"Enqueuing trigger: {trigger_dict.get('name')} ({trigger_dict.get('action_type')})")
            process_single_trigger.delay(trigger_dict, context_data)

    @staticmethod
    def _call_webhook(config: Dict, data: Dict):
        url = config.get("url")
        method = config.get("method", "POST").upper()
        headers = config.get("headers", {})

        if not url:
            return

        try:
            response = requests.request(
                method, url, json=data, headers=headers, timeout=5
            )
            response.raise_for_status()
        except requests.RequestException as e:
            error_logger.error(f"Webhook delivery failed: {str(e)}", exc_info=True)

    @staticmethod
    def _call_external_api(config: Dict, data: Dict):
        # Specific business logic for internal/integrated API calls
        logger.info(f"External API call triggered with config: {config}")
        # Not yet implemented
        raise NotImplementedError("External API call not implemented")

    @staticmethod
    def _run_custom_logic(script: str, data: Dict):
        """
        SAFE execution of dynamic scripts.
        In production, this should use a restricted sandbox (like PyExecJS or a secure eval).
        """
        logger.error("Custom script execution blocked for security reasons.")
        raise NotImplementedError("Custom scripts are disabled for security reasons.")
