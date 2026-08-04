from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml


try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # python-dotenv is optional.
    # On Render or other hosting platforms, environment variables
    # are already available through os.environ.
    pass


BASE_DIR = Path(__file__).resolve().parent.parent


TRUE_VALUES = {
    "1",
    "true",
    "yes",
    "y",
    "on",
    "enable",
    "enabled",
}

FALSE_VALUES = {
    "0",
    "false",
    "no",
    "n",
    "off",
    "disable",
    "disabled",
}


def _env_bool(name: str, current_value: Any = False) -> bool:
    raw = os.getenv(name)

    if raw is None:
        return bool(current_value)

    normalized = str(raw).strip().lower()

    if normalized in TRUE_VALUES:
        return True

    if normalized in FALSE_VALUES:
        return False

    return bool(current_value)


def _env_int(name: str, current_value: Any = 0) -> int:
    raw = os.getenv(name)

    if raw is None or str(raw).strip() == "":
        try:
            return int(current_value)
        except (TypeError, ValueError):
            return 0

    return int(str(raw).strip())


def _env_float(name: str, current_value: Any = 0.0) -> float:
    raw = os.getenv(name)

    if raw is None or str(raw).strip() == "":
        try:
            return float(current_value)
        except (TypeError, ValueError):
            return 0.0

    return float(str(raw).strip())


def _env_str(name: str, current_value: Any = "") -> str:
    raw = os.getenv(name)

    if raw is None:
        return "" if current_value is None else str(current_value)

    return str(raw).strip()


def _normalize_recipients(value: Any) -> list[str]:
    if not value:
        return []

    if isinstance(value, str):
        # Supports:
        #   "09121234567"
        #   "09121234567,09351234567"
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


def _normalize_args(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        return [
            str(item)
            for item in value
            if item is not None
        ]

    if isinstance(value, str):
        raw = value.strip()

        if not raw:
            return []

        # Supports JSON array:
        #   ["arg1","arg2"]
        try:
            parsed = json.loads(raw)

            if isinstance(parsed, list):
                return [
                    str(item)
                    for item in parsed
                    if item is not None
                ]

            return [str(parsed)]

        except json.JSONDecodeError:
            # Supports comma-separated:
            #   arg1,arg2
            return [
                item.strip()
                for item in raw.split(",")
                if item.strip()
            ]

    return [str(value)]


def load_config(path: str | Path | None = None) -> dict:
    config_path = Path(
        path
        or os.getenv("DIGIKALA_CONFIG")
        or os.getenv("CONFIG_PATH")
        or BASE_DIR / "config.yaml"
    )

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

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

    app_cfg["database_url"] = _env_str(
        "DATABASE_URL",
        app_cfg.get("database_url", ""),
    )

    app_cfg["request_timeout_seconds"] = _env_int(
        "REQUEST_TIMEOUT_SECONDS",
        app_cfg.get("request_timeout_seconds", 20),
    )

    app_cfg["poll_delay_min_seconds"] = _env_float(
        "POLL_DELAY_MIN_SECONDS",
        app_cfg.get("poll_delay_min_seconds", 2),
    )

    app_cfg["poll_delay_max_seconds"] = _env_float(
        "POLL_DELAY_MAX_SECONDS",
        app_cfg.get("poll_delay_max_seconds", 5),
    )

    # اگر در config.yaml از نام قبلی استفاده کرده باشید، حفظش می‌کنیم.
    if "poll_interval_seconds" in app_cfg:
        app_cfg["poll_interval_seconds"] = _env_int(
            "POLL_INTERVAL_SECONDS",
            app_cfg.get("poll_interval_seconds", 900),
        )

    if "min_delay_between_requests_seconds" in app_cfg:
        app_cfg["min_delay_between_requests_seconds"] = _env_float(
            "MIN_DELAY_BETWEEN_REQUESTS_SECONDS",
            app_cfg.get("min_delay_between_requests_seconds", 2),
        )

    if "max_delay_between_requests_seconds" in app_cfg:
        app_cfg["max_delay_between_requests_seconds"] = _env_float(
            "MAX_DELAY_BETWEEN_REQUESTS_SECONDS",
            app_cfg.get("max_delay_between_requests_seconds", 7),
        )

    # ---------------------------------------------------------
    # Cron/API secret
    # ---------------------------------------------------------

    config["cron_secret"] = _env_str(
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

    notif["telegram"]["bot_token"] = _env_str(
        "TELEGRAM_BOT_TOKEN",
        notif["telegram"].get("bot_token", ""),
    )

    notif["telegram"]["chat_id"] = _env_str(
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

    notif["bale"]["bot_token"] = _env_str(
        "BALE_BOT_TOKEN",
        notif["bale"].get("bot_token", ""),
    )

    notif["bale"]["chat_id"] = _env_str(
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

    sms_config["provider"] = _env_str(
        "SMS_PROVIDER",
        sms_config.get("provider", "melipayamak"),
    ).lower()

    sms_config["sender"] = _env_str(
        "SMS_SENDER",
        sms_config.get("sender", ""),
    )

    # Kavenegar compatibility
    sms_config["api_key"] = _env_str(
        "SMS_API_KEY",
        sms_config.get("api_key", ""),
    )

    sms_config["receptor"] = _env_str(
        "SMS_RECEPTOR",
        sms_config.get("receptor", ""),
    )

    # ---------------------------------------------------------
    # Melipayamak config - old REST compatibility
    # ---------------------------------------------------------

    melipayamak_config["username"] = _env_str(
        "MELIPAYAMAK_USERNAME",
        melipayamak_config.get("username", ""),
    )

    melipayamak_config["password"] = _env_str(
        "MELIPAYAMAK_PASSWORD",
        melipayamak_config.get("password", ""),
    )

    # ---------------------------------------------------------
    # Melipayamak config - new Console API
    # ---------------------------------------------------------

    melipayamak_config["token"] = _env_str(
        "MELIPAYAMAK_TOKEN",
        melipayamak_config.get("token", ""),
    )

    # اگر token داخل melipayamak نبود ولی SMS_API_KEY تنظیم شده بود،
    # برای سازگاری می‌تواند به‌عنوان fallback استفاده شود.
    if not melipayamak_config.get("token") and sms_config.get("api_key"):
        melipayamak_config["token"] = sms_config["api_key"]

    melipayamak_config["mode"] = _env_str(
        "MELIPAYAMAK_MODE",
        melipayamak_config.get("mode", "advanced"),
    ).lower()

    melipayamak_config["udh"] = _env_str(
        "MELIPAYAMAK_UDH",
        melipayamak_config.get("udh", ""),
    )

    raw_recipients = os.getenv("MELIPAYAMAK_RECIPIENTS")

    if raw_recipients is not None:
        melipayamak_config["recipients"] = _normalize_recipients(
            raw_recipients
        )
    else:
        melipayamak_config["recipients"] = _normalize_recipients(
            melipayamak_config.get("recipients", [])
        )

    # ---------------------------------------------------------
    # Melipayamak schedule mode
    # ---------------------------------------------------------

    melipayamak_config.setdefault("schedule", {})
    schedule_config = melipayamak_config["schedule"]

    schedule_config["date"] = _env_str(
        "MELIPAYAMAK_SCHEDULE_DATE",
        schedule_config.get(
            "date",
            melipayamak_config.get("date", ""),
        ),
    )

    schedule_config["period"] = _env_int(
        "MELIPAYAMAK_SCHEDULE_PERIOD",
        schedule_config.get(
            "period",
            melipayamak_config.get("period", 365),
        ),
    )

    # برای سازگاری با کدهایی که date/period را مستقیم
    # زیر melipayamak می‌خوانند.
    melipayamak_config["date"] = schedule_config["date"]
    melipayamak_config["period"] = schedule_config["period"]

    # ---------------------------------------------------------
    # Melipayamak shared/service mode
    # ---------------------------------------------------------

    body_id_env = os.getenv("MELIPAYAMAK_BODY_ID")

    if body_id_env is not None and body_id_env.strip():
        melipayamak_config["body_id"] = int(body_id_env.strip())
    else:
        current_body_id = (
            melipayamak_config.get("body_id")
            or melipayamak_config.get("bodyId")
        )

        if current_body_id not in {None, ""}:
            melipayamak_config["body_id"] = int(current_body_id)
        else:
            melipayamak_config["body_id"] = None

    # برای سازگاری با payload رسمی که bodyId می‌خواهد.
    melipayamak_config["bodyId"] = melipayamak_config["body_id"]

    args_env = os.getenv("MELIPAYAMAK_ARGS")

    if args_env is not None:
        melipayamak_config["args"] = _normalize_args(args_env)
    else:
        melipayamak_config["args"] = _normalize_args(
            melipayamak_config.get("args", [])
        )

    return config
