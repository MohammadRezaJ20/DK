import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)

MELIPAYAMAK_CONSOLE_BASE = "https://console.melipayamak.com/api/send"


class Notifier:
    def __init__(self, config: dict):
        self.config = config or {}
        self.notifications_config = (
            self.config.get("notifications", {}) or {}
        )

    # ------------------------------------------------------------------
    # Console
    # ------------------------------------------------------------------

    def send_console(self, message: str) -> bool:
        console_config = (
            self.notifications_config.get("console", {}) or {}
        )

        if not console_config.get("enabled", False):
            return False

        print("\n" + "=" * 100)
        print(message)
        print("=" * 100 + "\n")

        return True

    # ------------------------------------------------------------------
    # Telegram
    # ------------------------------------------------------------------

    def send_telegram(self, message: str) -> bool:
        telegram_config = (
            self.notifications_config.get("telegram", {}) or {}
        )

        if not telegram_config.get("enabled", False):
            return False

        bot_token = str(
            telegram_config.get("bot_token", "") or ""
        ).strip()

        chat_id = telegram_config.get("chat_id", "")

        if not bot_token or not chat_id:
            logger.error("Telegram config is incomplete")
            return False

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

        try:
            response = httpx.post(
                url,
                data={
                    "chat_id": chat_id,
                    "text": message,
                },
                timeout=20,
            )
            response.raise_for_status()

            data = self._safe_json_response(response)

            if isinstance(data, dict) and data.get("ok") is False:
                logger.error(
                    "Telegram API rejected message. response=%s",
                    data,
                )
                return False

            return True

        except httpx.HTTPStatusError as exc:
            logger.error(
                "Telegram HTTP error. status=%s body=%s",
                exc.response.status_code,
                exc.response.text[:500],
                exc_info=True,
            )
            return False

        except httpx.RequestError as exc:
            logger.error(
                "Telegram network error: %s",
                exc,
                exc_info=True,
            )
            return False

        except Exception:
            logger.exception("Telegram notification failed")
            return False

    # ------------------------------------------------------------------
    # Bale
    # ------------------------------------------------------------------

    def send_bale(self, message: str) -> bool:
        bale_config = (
            self.notifications_config.get("bale", {}) or {}
        )

        if not bale_config.get("enabled", False):
            return False

        bot_token = str(
            bale_config.get("bot_token", "") or ""
        ).strip()

        chat_id = bale_config.get("chat_id", "")

        if not bot_token or not chat_id:
            logger.error("Bale config is incomplete")
            return False

        url = f"https://tapi.bale.ai/bot{bot_token}/sendMessage"

        try:
            response = httpx.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": message,
                },
                timeout=20,
            )
            response.raise_for_status()

            data = self._safe_json_response(response)

            if isinstance(data, dict) and data.get("ok") is False:
                logger.error(
                    "Bale API rejected message. response=%s",
                    data,
                )
                return False

            return True

        except httpx.HTTPStatusError as exc:
            logger.error(
                "Bale HTTP error. status=%s body=%s",
                exc.response.status_code,
                exc.response.text[:500],
                exc_info=True,
            )
            return False

        except httpx.RequestError as exc:
            logger.error(
                "Bale network error: %s",
                exc,
                exc_info=True,
            )
            return False

        except Exception:
            logger.exception("Bale notification failed")
            return False

    # ------------------------------------------------------------------
    # SMS dispatcher
    # ------------------------------------------------------------------

    def send_sms(self, message: str) -> bool:
        sms_config = (
            self.notifications_config.get("sms", {}) or {}
        )

        if not sms_config.get("enabled", False):
            return False

        provider = str(
            sms_config.get("provider", "") or ""
        ).lower().strip()

        sender = str(
            sms_config.get("sender", "") or ""
        ).strip()

        try:
            if provider == "kavenegar":
                return self._send_sms_kavenegar(
                    sms_config=sms_config,
                    sender=sender,
                    message=message,
                )

            if provider == "melipayamak":
                return self._send_sms_melipayamak(
                    sms_config=sms_config,
                    sender=sender,
                    message=message,
                )

            logger.error("Unknown SMS provider: %s", provider)
            return False

        except httpx.HTTPStatusError as exc:
            logger.error(
                "SMS HTTP error. provider=%s status=%s body=%s",
                provider,
                exc.response.status_code,
                exc.response.text[:500],
                exc_info=True,
            )
            return False

        except httpx.RequestError as exc:
            logger.error(
                "SMS network error. provider=%s error=%s",
                provider,
                exc,
                exc_info=True,
            )
            return False

        except ValueError:
            logger.exception(
                "SMS provider returned invalid JSON. provider=%s",
                provider,
            )
            return False

        except Exception:
            logger.exception(
                "SMS notification failed. provider=%s",
                provider,
            )
            return False

    # ------------------------------------------------------------------
    # Kavenegar
    # ------------------------------------------------------------------

    def _send_sms_kavenegar(
        self,
        sms_config: dict,
        sender: str,
        message: str,
    ) -> bool:
        api_key = str(
            sms_config.get("api_key", "") or ""
        ).strip()

        receptor = sms_config.get("receptor", "")

        if not api_key or not receptor or not sender:
            logger.error("Kavenegar SMS config is incomplete")
            return False

        url = (
            f"https://api.kavenegar.com/v1/"
            f"{api_key}/sms/send.json"
        )

        payload = {
            "receptor": receptor,
            "sender": sender,
            "message": message,
        }

        response = httpx.post(
            url,
            data=payload,
            timeout=20,
        )
        response.raise_for_status()

        logger.info(
            "Kavenegar SMS sent successfully. receptor=%s",
            receptor,
        )

        return True

    # ------------------------------------------------------------------
    # Melipayamak dispatcher
    # ------------------------------------------------------------------

    def _send_sms_melipayamak(
        self,
        sms_config: dict,
        sender: str,
        message: str,
    ) -> bool:
        melipayamak_config = (
            sms_config.get("melipayamak", {}) or {}
        )

        mode = str(
            melipayamak_config.get("mode", "advanced")
            or "advanced"
        ).lower().strip()

        if mode in {
            "simple",
            "console-simple",
            "simple-token",
            "token-simple",
        }:
            return self._send_sms_melipayamak_simple(
                sms_config=sms_config,
                melipayamak_config=melipayamak_config,
                sender=sender,
                message=message,
            )

        if mode in {
            "advanced",
            "console-advanced",
            "token-advanced",
        }:
            return self._send_sms_melipayamak_advanced(
                sms_config=sms_config,
                melipayamak_config=melipayamak_config,
                sender=sender,
                message=message,
            )

        if mode in {
            "schedule",
            "scheduled",
            "console-schedule",
            "time",
        }:
            return self._send_sms_melipayamak_schedule(
                sms_config=sms_config,
                melipayamak_config=melipayamak_config,
                sender=sender,
                message=message,
            )

        if mode in {
            "shared",
            "console-shared",
            "service",
            "service-line",
        }:
            return self._send_sms_melipayamak_shared(
                sms_config=sms_config,
                melipayamak_config=melipayamak_config,
            )

        if mode in {
            "otp",
            "one-time-password",
        }:
            return self._send_sms_melipayamak_otp(
                sms_config=sms_config,
                melipayamak_config=melipayamak_config,
            )

        logger.error("Unknown Melipayamak mode: %s", mode)
        return False

    # ------------------------------------------------------------------
    # Melipayamak simple
    # ------------------------------------------------------------------

    def _send_sms_melipayamak_simple(
        self,
        sms_config: dict,
        melipayamak_config: dict,
        sender: str,
        message: str,
    ) -> bool:
        token = self._get_melipayamak_token(
            sms_config,
            melipayamak_config,
        )

        recipients = self._get_recipients(
            sms_config,
            melipayamak_config,
        )

        if not token or not sender or not recipients:
            logger.error(
                "Melipayamak simple config is incomplete. "
                "Required: token, sender, recipients"
            )
            return False

        url = f"{MELIPAYAMAK_CONSOLE_BASE}/simple/{token}"

        all_sent = True

        for recipient in recipients:
            payload = {
                "from": sender,
                "to": recipient,
                "text": message,
            }

            response = httpx.post(
                url,
                json=payload,
                timeout=20,
            )
            response.raise_for_status()

            data = self._safe_json_response(response)

            if not self._is_success_response(
                data,
                expected="recId",
            ):
                all_sent = False
                logger.error(
                    "Melipayamak simple SMS failed. "
                    "recipient=%s response=%s",
                    recipient,
                    data,
                )
                continue

            logger.info(
                "Melipayamak simple SMS sent. "
                "recipient=%s recId=%s",
                recipient,
                data.get("recId"),
            )

        return all_sent

    # ------------------------------------------------------------------
    # Melipayamak advanced
    # ------------------------------------------------------------------

    def _send_sms_melipayamak_advanced(
        self,
        sms_config: dict,
        melipayamak_config: dict,
        sender: str,
        message: str,
    ) -> bool:
        token = self._get_melipayamak_token(
            sms_config,
            melipayamak_config,
        )

        recipients = self._get_recipients(
            sms_config,
            melipayamak_config,
        )

        udh = melipayamak_config.get("udh", "") or ""

        if not token or not sender or not recipients:
            logger.error(
                "Melipayamak advanced config is incomplete. "
                "Required: token, sender, recipients"
            )
            return False

        url = f"{MELIPAYAMAK_CONSOLE_BASE}/advanced/{token}"

        payload = {
            "from": sender,
            "to": recipients,
            "text": message,
            "udh": udh,
        }

        response = httpx.post(
            url,
            json=payload,
            timeout=20,
        )
        response.raise_for_status()

        data = self._safe_json_response(response)

        if not self._is_success_response(
            data,
            expected="recIds",
        ):
            logger.error(
                "Melipayamak advanced SMS failed. response=%s",
                data,
            )
            return False

        logger.info(
            "Melipayamak advanced SMS sent. recIds=%s",
            data.get("recIds"),
        )

        return True

    # ------------------------------------------------------------------
    # Melipayamak scheduled
    # ------------------------------------------------------------------

    def _send_sms_melipayamak_schedule(
        self,
        sms_config: dict,
        melipayamak_config: dict,
        sender: str,
        message: str,
    ) -> bool:
        token = self._get_melipayamak_token(
            sms_config,
            melipayamak_config,
        )

        recipients = self._get_recipients(
            sms_config,
            melipayamak_config,
        )

        schedule_config = (
            melipayamak_config.get("schedule", {}) or {}
        )

        date = (
            schedule_config.get("date")
            or melipayamak_config.get("date")
            or ""
        )

        period = (
            schedule_config.get("period")
            or melipayamak_config.get("period")
            or 365
        )

        if not token or not sender or not recipients or not date:
            logger.error(
                "Melipayamak schedule config is incomplete. "
                "Required: token, sender, recipients, date"
            )
            return False

        url = f"{MELIPAYAMAK_CONSOLE_BASE}/schedule/{token}"

        all_scheduled = True

        for recipient in recipients:
            payload = {
                "message": message,
                "from": sender,
                "to": recipient,
                "date": date,
                "period": period,
            }

            response = httpx.post(
                url,
                json=payload,
                timeout=20,
            )
            response.raise_for_status()

            data = self._safe_json_response(response)

            if not self._is_success_response(
                data,
                expected="id",
            ):
                all_scheduled = False
                logger.error(
                    "Melipayamak scheduled SMS failed. "
                    "recipient=%s response=%s",
                    recipient,
                    data,
                )
                continue

            logger.info(
                "Melipayamak SMS scheduled. "
                "recipient=%s id=%s",
                recipient,
                data.get("id"),
            )

        return all_scheduled

    # ------------------------------------------------------------------
    # Melipayamak shared/service
    # ------------------------------------------------------------------

    def _send_sms_melipayamak_shared(
        self,
        sms_config: dict,
        melipayamak_config: dict,
    ) -> bool:
        token = self._get_melipayamak_token(
            sms_config,
            melipayamak_config,
        )

        recipients = self._get_recipients(
            sms_config,
            melipayamak_config,
        )

        body_id = (
            melipayamak_config.get("body_id")
            or melipayamak_config.get("bodyId")
        )

        args = melipayamak_config.get("args", []) or []

        if isinstance(args, str):
            args = [args]

        if not token or not body_id or not recipients:
            logger.error(
                "Melipayamak shared config is incomplete. "
                "Required: token, body_id, recipients"
            )
            return False

        try:
            body_id = int(body_id)
        except (TypeError, ValueError):
            logger.error("Melipayamak body_id must be an integer")
            return False

        url = f"{MELIPAYAMAK_CONSOLE_BASE}/shared/{token}"

        all_sent = True

        for recipient in recipients:
            payload = {
                "bodyId": body_id,
                "to": recipient,
                "args": args,
            }

            response = httpx.post(
                url,
                json=payload,
                timeout=20,
            )
            response.raise_for_status()

            data = self._safe_json_response(response)

            if not self._is_success_response(
                data,
                expected="recId",
            ):
                all_sent = False
                logger.error(
                    "Melipayamak shared SMS failed. "
                    "recipient=%s response=%s",
                    recipient,
                    data,
                )
                continue

            logger.info(
                "Melipayamak shared SMS sent. "
                "recipient=%s recId=%s",
                recipient,
                data.get("recId"),
            )

        return all_sent

    # ------------------------------------------------------------------
    # Melipayamak OTP
    # ------------------------------------------------------------------

    def _send_sms_melipayamak_otp(
        self,
        sms_config: dict,
        melipayamak_config: dict,
    ) -> bool:
        token = self._get_melipayamak_token(
            sms_config,
            melipayamak_config,
        )

        recipients = self._get_recipients(
            sms_config,
            melipayamak_config,
        )

        if not token or not recipients:
            logger.error(
                "Melipayamak OTP config is incomplete. "
                "Required: token and recipients"
            )
            return False

        url = f"{MELIPAYAMAK_CONSOLE_BASE}/otp/{token}"

        all_sent = True

        for recipient in recipients:
            payload = {
                "to": recipient,
            }

            response = httpx.post(
                url,
                json=payload,
                timeout=20,
            )
            response.raise_for_status()

            data = self._safe_json_response(response)

            if not self._is_success_response(
                data,
                expected="recId",
            ):
                all_sent = False
                logger.error(
                    "Melipayamak OTP failed. "
                    "recipient=%s response=%s",
                    recipient,
                    data,
                )
                continue

            logger.info(
                "Melipayamak OTP sent. "
                "recipient=%s recId=%s",
                recipient,
                data.get("recId"),
            )

        return all_sent

    # ------------------------------------------------------------------
    # Melipayamak helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_melipayamak_token(
        sms_config: dict,
        melipayamak_config: dict,
    ) -> str:
        token = (
            melipayamak_config.get("token")
            or melipayamak_config.get("api_key")
            or sms_config.get("api_key")
            or ""
        )

        return str(token).strip()

    @staticmethod
    def _get_recipients(
        sms_config: dict,
        melipayamak_config: dict,
    ) -> list[str]:
        recipients = melipayamak_config.get("recipients")

        if not recipients:
            recipients = sms_config.get("receptor", [])

        if isinstance(recipients, str):
            recipients = [recipients]

        if recipients is None:
            recipients = []

        normalized = []

        for recipient in recipients:
            value = str(recipient).strip()

            if value:
                normalized.append(value)

        return normalized

    @staticmethod
    def _safe_json_response(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            logger.error(
                "Provider returned non-JSON response. "
                "status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
            return None

    @staticmethod
    def _is_success_response(
        data: Any,
        expected: str,
    ) -> bool:
        """
        Melipayamak Console success is checked based on send ID:

        Simple, Shared and OTP:
            {"recId": 123, "status": "..."}

        Advanced:
            {"recIds": [123, 456], "status": "..."}

        Schedule:
            {"id": 2244, "status": "..."}
        """

        if not isinstance(data, dict):
            return False

        if expected == "recId":
            rec_id = data.get("recId")
            return (
                rec_id is not None
                and str(rec_id).strip() != ""
            )

        if expected == "recIds":
            rec_ids = data.get("recIds")

            return (
                isinstance(rec_ids, list)
                and len(rec_ids) > 0
                and all(
                    item is not None
                    and str(item).strip() != ""
                    for item in rec_ids
                )
            )

        if expected == "id":
            schedule_id = data.get("id")
            return (
                schedule_id is not None
                and str(schedule_id).strip() != ""
            )

        return False

    # ------------------------------------------------------------------
    # All notification channels
    # ------------------------------------------------------------------

    def notify_all(
        self,
        full_message: str,
        sms_message: str | None = None,
    ) -> dict:
        """
        full_message:
            Used for console, telegram and bale.
            It can contain product URL and full report.

        sms_message:
            Used only for SMS.
            It should be short and should not contain product URL.
        """

        if sms_message is None:
            sms_message = full_message

        return {
            "console": self.send_console(full_message),
            "telegram": self.send_telegram(full_message),
            "bale": self.send_bale(full_message),
            "sms": self.send_sms(sms_message),
        }
