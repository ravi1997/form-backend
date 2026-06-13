import os
from typing import Any, Dict, Optional

import requests

from logger.unified_logger import app_logger, error_logger, audit_logger


class SMSResult:
    def __init__(self, success, message_id=None, status_code=200, error_message=None):
        self.success = success
        self.message_id = message_id
        self.status_code = status_code
        self.error_message = error_message


class ExternalSMSService:
    def __init__(self):
        self.api_url = (
            os.getenv("AIIMS_SMS_API_URL")
            or os.getenv("SMS_API_URL")
            or ""
        ).rstrip("/")
        self.api_token = os.getenv("AIIMS_SMS_API_TOKEN") or os.getenv("SMS_API_TOKEN")
        self.sms_path = os.getenv("AIIMS_SMS_SEND_PATH", "/sms")
        self.otp_path = os.getenv("AIIMS_SMS_OTP_PATH", "/otp")
        self.notification_path = os.getenv("AIIMS_SMS_NOTIFICATION_PATH", "/notify")

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def _post(self, path: str, payload: Dict[str, Any]) -> requests.Response:
        if not self.api_url:
            raise RuntimeError(
                "SMS API URL is not configured. Set AIIMS_SMS_API_URL or SMS_API_URL."
            )
        url = f"{self.api_url}{path}"
        app_logger.info(f"Calling AIIMS SMS endpoint: POST {url}")
        response = requests.post(
            url,
            json=payload,
            headers=self._build_headers(),
            timeout=15,
        )
        response.raise_for_status()
        return response

    @staticmethod
    def _extract_message_id(response: requests.Response) -> Optional[str]:
        try:
            data = response.json()
        except ValueError:
            return None

        if isinstance(data, dict):
            for key in ("message_id", "messageId", "id", "request_id", "requestId"):
                value = data.get(key)
                if value:
                    return str(value)
        return None

    def send_sms(self, mobile, message):
        app_logger.info(f"Sending SMS to {mobile[:5]}***")
        try:
            response = self._post(
                self.sms_path,
                {"mobile": str(mobile).strip(), "message": message},
            )
            result = SMSResult(
                True,
                self._extract_message_id(response),
                status_code=response.status_code,
            )
            app_logger.info(
                f"SMS sent successfully to {mobile[:5]}***, message_id: {result.message_id}"
            )
            audit_logger.info(
                f"SMS sent: recipient={mobile[:5]}***, message_id={result.message_id}"
            )
            return result
        except requests.RequestException as e:
            error_logger.error(f"Failed to send SMS to {mobile[:5]}***: {str(e)}", exc_info=True)
            status_code = getattr(getattr(e, "response", None), "status_code", 500)
            return SMSResult(False, status_code=status_code, error_message=str(e))
        except Exception as e:
            error_logger.error(f"Failed to send SMS to {mobile[:5]}***: {str(e)}", exc_info=True)
            return SMSResult(False, status_code=500, error_message=str(e))

    def send_otp(self, mobile, otp):
        app_logger.info(f"Sending OTP to {mobile[:5]}***")
        try:
            response = self._post(
                self.otp_path,
                {"mobile": str(mobile).strip(), "otp": otp},
            )
            result = SMSResult(
                True,
                self._extract_message_id(response),
                status_code=response.status_code,
            )
            app_logger.info(
                f"OTP sent successfully to {mobile[:5]}***, message_id: {result.message_id}"
            )
            audit_logger.info(
                f"OTP sent: recipient={mobile[:5]}***, message_id={result.message_id}"
            )
            return result
        except requests.RequestException as e:
            error_logger.error(f"Failed to send OTP to {mobile[:5]}***: {str(e)}", exc_info=True)
            status_code = getattr(getattr(e, "response", None), "status_code", 500)
            return SMSResult(False, status_code=status_code, error_message=str(e))
        except Exception as e:
            error_logger.error(f"Failed to send OTP to {mobile[:5]}***: {str(e)}", exc_info=True)
            return SMSResult(False, status_code=500, error_message=str(e))

    def send_notification(self, mobile, title, body):
        app_logger.info(f"Sending SMS notification to {mobile[:5]}***, title: {title}")
        try:
            response = self._post(
                self.notification_path,
                {
                    "mobile": str(mobile).strip(),
                    "title": title,
                    "body": body,
                },
            )
            result = SMSResult(
                True,
                self._extract_message_id(response),
                status_code=response.status_code,
            )
            app_logger.info(
                f"SMS notification sent successfully to {mobile[:5]}***, message_id: {result.message_id}"
            )
            audit_logger.info(
                f"SMS notification sent: recipient={mobile[:5]}***, title={title}, message_id={result.message_id}"
            )
            return result
        except requests.RequestException as e:
            error_logger.error(
                f"Failed to send SMS notification to {mobile[:5]}***: {str(e)}",
                exc_info=True,
            )
            status_code = getattr(getattr(e, "response", None), "status_code", 500)
            return SMSResult(False, status_code=status_code, error_message=str(e))
        except Exception as e:
            error_logger.error(
                f"Failed to send SMS notification to {mobile[:5]}***: {str(e)}",
                exc_info=True,
            )
            return SMSResult(False, status_code=500, error_message=str(e))


def get_sms_service():
    return ExternalSMSService()
