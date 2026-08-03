import logging

import httpx

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, config: dict):
        self.config = config or {}
        self.notifications_config = self.config.get("notifications", {}) or {}

    def send_console(self, message: str) -> bool:
        console_config = self.notifications_config.get("console", {}) or {}

        if not console_config.get("enabled", False):
            return False

        print("\n" + "=" * 100)
        print(message)
        print("=" * 100 + "\n")
        return True

    def send_telegram(self, message: str) -> bool:
        tg = self.notifications_config.get("telegram", {}) or {}

        if not tg.get("enabled", False):
            return False

        token = tg.get("bot_token", "")
        chat_id = tg.get("chat_id", "")

        if not token or not chat_id:
            logger.error("Telegram config is incomplete")
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"

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

        except Exception as exc:
            logger.error(
                "Telegram notification failed: %s",
                exc,
                exc_info=True,
            )
            return False

    def send_bale(self, message: str) -> bool:
        bale = self.notifications_config.get("bale", {}) or {}

        if not bale.get("enabled", False):
            return False

        token = bale.get("bot_token", "")
        chat_id = bale.get("chat_id", "")

        if not token or not chat_id:
            logger.error("Bale config is incomplete")
            return False

        url = f"https://tapi.bale.ai/bot{token}/sendMessage"

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

        except Exception as exc:
            logger.error(
                "Bale notification failed: %s",
                exc,
                exc_info=True,
            )
            return False

    def send_sms(self, message: str) -> bool:
        sms_config = self.notifications_config.get("sms", {}) or {}

        if not sms_config.get("enabled", False):
            return False

        provider = str(sms_config.get("provider", "") or "").lower().strip()
        sender = sms_config.get("sender", "")

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

    def _send_sms_kavenegar(self, sms_config: dict, sender: str, message: str) -> bool:
        api_key = sms_config.get("api_key", "")
        receptor = sms_config.get("receptor", "")

        if not api_key or not receptor or not sender:
            logger.error("Kavenegar SMS config is incomplete")
            return False

        url = f"https://api.kavenegar.com/v1/{api_key}/sms/send.json"
        payload = {
            "receptor": receptor,
            "sender": sender,
            "message": message,
        }

        response = httpx.post(url, data=payload, timeout=10)
        response.raise_for_status()
        return True

    def _send_sms_melipayamak(self, sms_config: dict, sender: str, message: str) -> bool:
        melipayamak_config = sms_config.get("melipayamak", {}) or {}

        username = melipayamak_config.get("username", "")
        password = melipayamak_config.get("password", "")
        recipients = melipayamak_config.get("recipients", [])

        if isinstance(recipients, str):
            recipients = [recipients]

        recipients = [str(number).strip() for number in recipients if str(number).strip()]

        if not username or not password or not sender or not recipients:
            logger.error("Melipayamak SMS config is incomplete")
            return False

        # Melipayamak REST simple-send endpoint
        url = "https://rest.melipayamak.com/api/send/simple"

        # Keep the current project style:
        # one request containing recipients as a list.
        payload = {
            "username": username,
            "password": password,
            "from": sender,
            "to": recipients,
            "text": message,
        }

        response = httpx.post(url, json=payload, timeout=10)
        response.raise_for_status()

        data = response.json()

        # Common successful RetStatus for Melipayamak is 1.
        if data.get("RetStatus") == 1:
            return True

        logger.error(
            "Melipayamak SMS failed. RetStatus=%s message=%s response=%s",
            data.get("RetStatus"),
            data.get("StrRetStatus"),
            data,
        )
        return False

    def notify_all(self, message: str) -> dict:
        return {
            "console": self.send_console(message),
            "telegram": self.send_telegram(message),
            "bale": self.send_bale(message),
            "sms": self.send_sms(message),
        }
