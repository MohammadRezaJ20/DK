from __future__ import annotations

import os
from pathlib import Path

import yaml


BASE_DIR = Path(__file__).resolve().parent.parent


def load_config(path: str | Path | None = None) -> dict:
    config_path = Path(
        path or os.getenv("DIGIKALA_CONFIG", BASE_DIR / "config.yaml")
    )

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    config.setdefault("app", {})
    config.setdefault("notifications", {})
    config.setdefault("web", {})
    config.setdefault("defaults", {})
    config["notifications"].setdefault("console", {})
    config["notifications"].setdefault("telegram", {})
    config["notifications"].setdefault("sms", {})
    config["notifications"].setdefault("bale", {})
    config["defaults"].setdefault("conditions", {})
    
    sms_config = config["notifications"].setdefault("sms", {})
    melipayamak_config = sms_config.setdefault("melipayamak", {})
    
    sms_config["provider"] = os.getenv(
        "SMS_PROVIDER",
        sms_config.get("provider", "kavenegar"),
    )
    
    sms_config["sender"] = os.getenv(
        "SMS_SENDER",
        sms_config.get("sender", ""),
    )
    
    melipayamak_config["username"] = os.getenv(
        "MELIPAYAMAK_USERNAME",
        melipayamak_config.get("username", ""),
    )
    
    melipayamak_config["password"] = os.getenv(
        "MELIPAYAMAK_PASSWORD",
        melipayamak_config.get("password", ""),
    )
    
    raw_recipients = os.getenv("MELIPAYAMAK_RECIPIENTS")
    
    if raw_recipients:
        melipayamak_config["recipients"] = [
            number.strip()
            for number in raw_recipients.split(",")
            if number.strip()
        ]
    else:
        recipients = melipayamak_config.get("recipients", [])
        if isinstance(recipients, str):
            recipients = [recipients]
        melipayamak_config["recipients"] = [
            number.strip()
            for number in recipients
            if number and number.strip()
        ]

    
    app_cfg = config["app"]
    notif = config["notifications"]

    app_cfg["database_url"] = os.getenv(
        "DATABASE_URL",
        app_cfg.get("database_url", ""),
    )

    notif["telegram"]["bot_token"] = os.getenv(
        "TELEGRAM_BOT_TOKEN",
        notif["telegram"].get("bot_token", ""),
    )
    notif["telegram"]["chat_id"] = os.getenv(
        "TELEGRAM_CHAT_ID",
        notif["telegram"].get("chat_id", ""),
    )

    notif["sms"]["api_key"] = os.getenv(
        "SMS_API_KEY",
        notif["sms"].get("api_key", ""),
    )
    notif["sms"]["sender"] = os.getenv(
        "SMS_SENDER",
        notif["sms"].get("sender", ""),
    )
    notif["sms"]["receptor"] = os.getenv(
        "SMS_RECEPTOR",
        notif["sms"].get("receptor", ""),
    )

    notif["bale"]["bot_token"] = os.getenv(
        "BALE_BOT_TOKEN",
        notif["bale"].get("bot_token", ""),
    )
    notif["bale"]["chat_id"] = os.getenv(
        "BALE_CHAT_ID",
        notif["bale"].get("chat_id", ""),
    )

    config["cron_secret"] = os.getenv(
        "CRON_SECRET",
        config.get("cron_secret", ""),
    )

    return config
