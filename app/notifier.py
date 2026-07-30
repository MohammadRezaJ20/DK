import httpx


class Notifier:
    def __init__(self, config: dict):
        self.config = config

    def send_console(self, message: str) -> bool:
        if not self.config["notifications"]["console"]["enabled"]:
            return False
        print("\n" + "=" * 100)
        print(message)
        print("=" * 100 + "\n")
        return True

    def send_telegram(self, message: str) -> bool:
        tg = self.config["notifications"]["telegram"]
        if not tg["enabled"]:
            return False

        token = tg["bot_token"]
        chat_id = tg["chat_id"]
        if not token or not chat_id:
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            r = httpx.post(url, data={"chat_id": chat_id, "text": message}, timeout=20)
            r.raise_for_status()
            return True
        except Exception:
            return False

    def send_sms(self, message: str) -> bool:
        sms = self.config["notifications"]["sms"]
        if not sms["enabled"]:
            return False

        provider = sms["provider"]

        if provider == "kavenegar":
            api_key = sms["api_key"]
            receptor = sms["receptor"]
            sender = sms["sender"]
            if not api_key or not receptor:
                return False

            try:
                url = f"https://api.kavenegar.com/v1/{api_key}/sms/send.json"
                payload = {
                    "receptor": receptor,
                    "sender": sender,
                    "message": message[:450],
                }
                r = httpx.post(url, data=payload, timeout=20)
                r.raise_for_status()
                return True
            except Exception:
                return False

        return False

    def notify_all(self, message: str) -> dict:
        return {
            "console": self.send_console(message),
            "telegram": self.send_telegram(message),
            "sms": self.send_sms(message),
        }
