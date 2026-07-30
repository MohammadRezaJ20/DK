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
        return yaml.safe_load(f)
