import os
import yaml

DEFAULT_CONFIG = {
    "backend": {
        "url": "http://127.0.0.1:8000",
        "timeout": 30000,
    }
}


def load_config():
    config_path = os.path.join(os.getcwd(), "config.yaml")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            if raw:
                backend = {**DEFAULT_CONFIG["backend"], **(raw.get("backend") or {})}
                return {**raw, "backend": backend}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def get_project_root():
    return os.getcwd().replace("\\", "/")
