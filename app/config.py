from __future__ import annotations

import os
from pathlib import Path

import yaml


BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, current_value=False) -> bool:
    raw = os.getenv(name)

    if raw is None:
        return bool(current_value)

    return str(raw).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
        "enable",
        "enabled",
    }


def _normalize_recipients(value) -> list[str]:
    if not value:
        return []

    if isinstance(value, str):
        # Support both comma-separated env value and single number.
        return [
            item.strip()
            for item in value.split(",")
            if item.strip()
        ]

    if isinstance(value, list):
        return [
            str(item).strip()
            for item in value
            if item is not None and str(item).strip()
        ]

    return [str(value).strip()] if str(value).strip() else []


def load_config(path: str | Path | None = None) -> dict:
    config_path = Path(
        path or os.getenv("DIGIKALA_CONFIG", BASE_DIR / "config.yaml")
    )

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    # ---------------------------------------------------------
    # Top-level defaults
    # ---------------------------------------------------------

    config.setdefault("app", {})
    config.setdefault("notifications", {})
    config.setdefault("web", {})
    config.setdefault("defaults", {})

    config["defaults"].setdefault("conditions", {})

    app_cfg = config["app"]
    notif = config["notifications"]

    notif.setdefault("console", {})
    notif.setdefault("telegram", {})
    notif.setdefault("sms", {})
    notif.setdefault("bale", {})

    sms_config = notif["sms"]
    sms_config.setdefault("melipayamak", {})

    melipayamak_config = sms_config["melipayamak"]

    # ---------------------------------------------------------
    # App config from env
    # ---------------------------------------------------------

    app_cfg["database_url"] = os.getenv(
        "DATABASE_URL",
        app_cfg.get("database_url", ""),
    )

    # Optional runtime/network settings used by monitor/web.
    # If not present in config.yaml, these defaults are safe.
    app_cfg["request_timeout_seconds"] = int(
        os.getenv(
            "REQUEST_TIMEOUT_SECONDS",
            app_cfg.get("request_timeout_seconds", 20),
        )
    )

    app_cfg["poll_delay_min_seconds"] = float(
        os.getenv(
            "POLL_DELAY_MIN_SECONDS",
            app_cfg.get("poll_delay_min_seconds", 2),
        )
    )

    app_cfg["poll_delay_max_seconds"] = float(
        os.getenv(
            "POLL_DELAY_MAX_SECONDS",
            app_cfg.get("poll_delay_max_seconds", 5),
        )
    )

    # ---------------------------------------------------------
    # Cron/API secret
    # ---------------------------------------------------------

    config["cron_secret"] = os.getenv(
        "CRON_SECRET",
        config.get("cron_secret", ""),
    )

    # ---------------------------------------------------------
    # Console notification
    # ---------------------------------------------------------

    notif["console"]["enabled"] = _env_bool(
        "CONSOLE_ENABLED",
        notif["console"].get("enabled", True),
    )

    # ---------------------------------------------------------
    # Telegram notification
    # ---------------------------------------------------------

    notif["telegram"]["enabled"] = _env_bool(
        "TELEGRAM_ENABLED",
        notif["telegram"].get("enabled", False),
    )

    notif["telegram"]["bot_token"] = os.getenv(
        "TELEGRAM_BOT_TOKEN",
        notif["telegram"].get("bot_token", ""),
    )

    notif["telegram"]["chat_id"] = os.getenv(
        "TELEGRAM_CHAT_ID",
        notif["telegram"].get("chat_id", ""),
    )

    # ---------------------------------------------------------
    # Bale notification
    # ---------------------------------------------------------

    notif["bale"]["enabled"] = _env_bool(
        "BALE_ENABLED",
        notif["bale"].get("enabled", False),
    )

    notif["bale"]["bot_token"] = os.getenv(
        "BALE_BOT_TOKEN",
        notif["bale"].get("bot_token", ""),
    )

    notif["bale"]["chat_id"] = os.getenv(
        "BALE_CHAT_ID",
        notif["bale"].get("chat_id", ""),
    )

    # ---------------------------------------------------------
    # SMS notification - shared config
    # ---------------------------------------------------------

    sms_config["enabled"] = _env_bool(
        "SMS_ENABLED",
        sms_config.get("enabled", False),
    )

    sms_config["provider"] = os.getenv(
        "SMS_PROVIDER",
        sms_config.get("provider", "melipayamak"),
    )

    sms_config["sender"] = os.getenv(
        "SMS_SENDER",
        sms_config.get("sender", ""),
    )

    # Kavenegar compatibility
    sms_config["api_key"] = os.getenv(
        "SMS_API_KEY",
        sms_config.get("api_key", ""),
    )

    sms_config["receptor"] = os.getenv(
        "SMS_RECEPTOR",
        sms_config.get("receptor", ""),
    )

    # ---------------------------------------------------------
    # Melipayamak config
    # ---------------------------------------------------------

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
        melipayamak_config["recipients"] = _normalize_recipients(raw_recipients)
    else:
        melipayamak_config["recipients"] = _normalize_recipients(
            melipayamak_config.get("recipients", [])
        )

    return config
