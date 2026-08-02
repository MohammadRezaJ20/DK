import os
from pathlib import Path
import yaml

BASE_DIR = Path(__file__).resolve().parent.parent

def load_config(path: str | Path | None = None) -> dict:
    if path is None:
        config_path = BASE_DIR / "config.yaml"
    else:
        config_path = Path(path)
        if not config_path.is_absolute():
            config_path = BASE_DIR / config_path

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    app_cfg = config.setdefault("app", {})

    if os.getenv("DATABASE_URL"):
        app_cfg["database_url"] = os.getenv("DATABASE_URL")

    if os.getenv("CRON_SECRET"):
        config["cron_secret"] = os.getenv("CRON_SECRET")

    return config
