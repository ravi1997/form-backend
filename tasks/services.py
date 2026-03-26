from celery import shared_task
from logger.unified_logger import app_logger, error_logger, audit_logger

# Service type configurations (can be extended)
# Priorities: 0 (Highest) to 9 (Lowest)

SERVICE_TYPES_CONFIG = {
    "sms": {
        "OTP": {"priority": 0},
        "PROMOTIONAL": {"priority": 9},
        "TRANSACTIONAL": {"priority": 3},
    },
    "mail": {
        "PASSWORD_RESET": {"priority": 0},
        "NEWSLETTER": {"priority": 9},
        "WELCOME_EMAIL": {"priority": 5},
    },
    "ehospital": {
        "EMERGENCY": {"priority": 0},
        "APPOINTMENT": {"priority": 4},
        "REPORT_GENERATION": {"priority": 7},
    },
    "request": {
        "PAYMENT": {"priority": 1},
        "SUPPORT": {"priority": 5},
        "FEEDBACK": {"priority": 8},
    },
    "employee": {
        "ONBOARDING": {"priority": 2},
        "PAYROLL": {"priority": 2},
        "LEAVE_REQUEST": {"priority": 6},
    },
}


@shared_task(queue="sms", bind=True)
def process_sms(self, sub_type: str, data: dict):
    """
    Empty function for SMS service queue.
    Sub-types and their priorities:
    - OTP: highest priority (0)
    - TRANSACTIONAL: medium priority (3)
    - PROMOTIONAL: lowest priority (9)
    """
    app_logger.info(f"Entering process_sms: sub_type={sub_type}")
    try:
        priority = SERVICE_TYPES_CONFIG.get("sms", {}).get(sub_type, {}).get("priority", 5)
        app_logger.info(f"Processing SMS of type {sub_type} with priority {priority}")
        audit_logger.info(f"SMS processed: sub_type={sub_type}, priority={priority}")
        app_logger.info("Exiting process_sms")
    except Exception as e:
        error_logger.error(f"Error processing SMS: {e}")
        raise e


@shared_task(queue="mail", bind=True)
def process_mail(self, sub_type: str, data: dict):
    """
    Empty function for Mail service queue.
    """
    app_logger.info(f"Entering process_mail: sub_type={sub_type}")
    try:
        priority = SERVICE_TYPES_CONFIG.get("mail", {}).get(sub_type, {}).get("priority", 5)
        app_logger.info(f"Processing Mail of type {sub_type} with priority {priority}")
        audit_logger.info(f"Mail processed: sub_type={sub_type}, priority={priority}")
        app_logger.info("Exiting process_mail")
    except Exception as e:
        error_logger.error(f"Error processing Mail: {e}")
        raise e


@shared_task(queue="ehospital", bind=True)
def process_ehospital(self, sub_type: str, data: dict):
    """
    Empty function for eHospital service queue.
    """
    app_logger.info(f"Entering process_ehospital: sub_type={sub_type}")
    try:
        priority = (
            SERVICE_TYPES_CONFIG.get("ehospital", {}).get(sub_type, {}).get("priority", 5)
        )
        app_logger.info(
            f"Processing eHospital request of type {sub_type} with priority {priority}"
        )
        audit_logger.info(f"eHospital request processed: sub_type={sub_type}, priority={priority}")
        app_logger.info("Exiting process_ehospital")
    except Exception as e:
        error_logger.error(f"Error processing eHospital request: {e}")
        raise e


@shared_task(queue="request", bind=True)
def process_request(self, sub_type: str, data: dict):
    """
    Empty function for Request service queue.
    """
    app_logger.info(f"Entering process_request: sub_type={sub_type}")
    try:
        priority = (
            SERVICE_TYPES_CONFIG.get("request", {}).get(sub_type, {}).get("priority", 5)
        )
        app_logger.info(f"Processing Request of type {sub_type} with priority {priority}")
        audit_logger.info(f"Request processed: sub_type={sub_type}, priority={priority}")
        app_logger.info("Exiting process_request")
    except Exception as e:
        error_logger.error(f"Error processing request: {e}")
        raise e


@shared_task(queue="employee", bind=True)
def process_employee(self, sub_type: str, data: dict):
    """
    Empty function for Employee service queue.
    """
    app_logger.info(f"Entering process_employee: sub_type={sub_type}")
    try:
        priority = (
            SERVICE_TYPES_CONFIG.get("employee", {}).get(sub_type, {}).get("priority", 5)
        )
        app_logger.info(
            f"Processing Employee service of type {sub_type} with priority {priority}"
        )
        audit_logger.info(f"Employee service processed: sub_type={sub_type}, priority={priority}")
        app_logger.info("Exiting process_employee")
    except Exception as e:
        error_logger.error(f"Error processing employee service: {e}")
        raise e
