import pathlib

import yaml


config_path = pathlib.Path(__file__).resolve().parent / "config.yaml"


def _load_config():
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream)

    if not isinstance(data, dict):
        return {}

    return data.get("checks", {})


config = _load_config()
