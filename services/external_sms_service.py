from logger.unified_logger import app_logger, error_logger, audit_logger

class SMSResult:
    def __init__(self, success, message_id=None, status_code=200, error_message=None):
        self.success = success
        self.message_id = message_id
        self.status_code = status_code
        self.error_message = error_message


class ExternalSMSService:
    def __init__(self):
        self.api_url = "http://stub-sms-api.com"
        self.api_token = "stub-token"

    def send_sms(self, mobile, message):
        app_logger.info(f"Sending SMS to {mobile[:5]}***")
        try:
            # Stub implementation
            result = SMSResult(True, "stub_msg_id")
            app_logger.info(f"SMS sent successfully to {mobile[:5]}***, message_id: {result.message_id}")
            audit_logger.info(f"SMS sent: recipient={mobile[:5]}***, message_id={result.message_id}")
            return result
        except Exception as e:
            error_logger.error(f"Failed to send SMS to {mobile[:5]}***: {str(e)}")
            return SMSResult(False, error_message=str(e))

    def send_otp(self, mobile, otp):
        app_logger.info(f"Sending OTP to {mobile[:5]}***")
        try:
            # Stub implementation
            result = SMSResult(True, "stub_otp_id")
            app_logger.info(f"OTP sent successfully to {mobile[:5]}***, message_id: {result.message_id}")
            audit_logger.info(f"OTP sent: recipient={mobile[:5]}***, message_id={result.message_id}")
            return result
        except Exception as e:
            error_logger.error(f"Failed to send OTP to {mobile[:5]}***: {str(e)}")
            return SMSResult(False, error_message=str(e))

    def send_notification(self, mobile, title, body):
        app_logger.info(f"Sending SMS notification to {mobile[:5]}***, title: {title}")
        try:
            # Stub implementation
            result = SMSResult(True, "stub_notify_id")
            app_logger.info(f"SMS notification sent successfully to {mobile[:5]}***, message_id: {result.message_id}")
            audit_logger.info(f"SMS notification sent: recipient={mobile[:5]}***, title={title}, message_id={result.message_id}")
            return result
        except Exception as e:
            error_logger.error(f"Failed to send SMS notification to {mobile[:5]}***: {str(e)}")
            return SMSResult(False, error_message=str(e))


def get_sms_service():
    return ExternalSMSService()
