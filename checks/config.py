import pathlib

import yaml

DEFAULTS = {
    "helpdesk_email": "acdh-ch-helpdesk@oeaw.ac.at",
    "logo_patterns": [
        "acdh-logo",
        "acdh_logo",
        "acdh-ch-logo",
        "acdh.oeaw.ac.at/assets/logo",
    ],
    "imprint_keywords": [
        "imprint",
        "impressum",
        "legal-notice",
        "legal_notice",
    ],
}

config = DEFAULTS.copy()

config_path = pathlib.Path(__file__).resolve().parent.parent / "config.yaml"
if config_path.exists():
    try:
        with config_path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
        if isinstance(data, dict) and "checks" in data:
            config.update(data["checks"])
    except Exception:
        pass
