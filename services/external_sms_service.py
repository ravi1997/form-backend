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
        return SMSResult(True, "stub_msg_id")

    def send_otp(self, mobile, otp):
        return SMSResult(True, "stub_otp_id")

    def send_notification(self, mobile, title, body):
        return SMSResult(True, "stub_notify_id")


def get_sms_service():
    return ExternalSMSService()
