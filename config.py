import copy
import os
import pathlib

import yaml


config_path = pathlib.Path(__file__).resolve().parent / "config.yaml"

DEFAULTS = {
    "checks": {
        "helpdesk_email": "acdh-helpdesk@oeaw.ac.at",
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
    },
    "http": {
        "requests_per_second": 2.0,
        "max_concurrent": 5,
        "timeout_seconds": 15,
        "max_retries": 2,
    },
    "k8s": {
        "requests_per_second": 5.0,
    },
    "runner": {
        "batch_size": 10,
        "batch_delay": 2.0,
        "max_services": 0,
        "dry_run": False,
    },
    "redmine": {
        "url": "http://redmine-prod.redmine.svc.cluster.local:3000",
        "request_interval_seconds": 1.0,
    },
}


def _parse_list(value):
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _int_env(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _float_env(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _bool_env(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _float_env(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _load_yaml_config():
    if not config_path.exists():
        return {}

    try:
        with config_path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _merge_dicts(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _merge_dicts(base[key], value)
        else:
            base[key] = value
    return base


def _apply_env_overrides(config):
    config["checks"]["helpdesk_email"] = os.getenv(
        "QOS_HELPDESK_EMAIL", config["checks"]["helpdesk_email"]
    )

    logo_patterns = os.getenv("QOS_LOGO_PATTERNS")
    if logo_patterns:
        config["checks"]["logo_patterns"] = _parse_list(logo_patterns)

    imprint_keywords = os.getenv("QOS_IMPRINT_KEYWORDS")
    if imprint_keywords:
        config["checks"]["imprint_keywords"] = _parse_list(imprint_keywords)

    config["http"]["requests_per_second"] = _float_env(
        "QOS_HTTP_REQUESTS_PER_SECOND", config["http"]["requests_per_second"]
    )
    config["http"]["max_concurrent"] = _int_env(
        "QOS_HTTP_MAX_CONCURRENT", config["http"]["max_concurrent"]
    )
    config["http"]["timeout_seconds"] = _int_env(
        "QOS_HTTP_TIMEOUT_SECONDS", config["http"]["timeout_seconds"]
    )
    config["http"]["max_retries"] = _int_env(
        "QOS_HTTP_MAX_RETRIES", config["http"]["max_retries"]
    )

    config["k8s"]["requests_per_second"] = _float_env(
        "QOS_K8S_REQUESTS_PER_SECOND", config["k8s"]["requests_per_second"]
    )

    config["runner"]["batch_size"] = _int_env(
        "QOS_BATCH_SIZE", config["runner"]["batch_size"]
    )
    config["runner"]["batch_delay"] = _float_env(
        "QOS_BATCH_DELAY", config["runner"]["batch_delay"]
    )
    config["runner"]["max_services"] = _int_env(
        "QOS_MAX_SERVICES", config["runner"]["max_services"]
    )
    config["runner"]["dry_run"] = _bool_env(
        "QOS_DRY_RUN", config["runner"]["dry_run"]
    )

    config["redmine"]["request_interval_seconds"] = _float_env(
        "QOS_REDMINE_REQUEST_INTERVAL_SECONDS",
        config["redmine"]["request_interval_seconds"],
    )

    return config


config = _apply_env_overrides(_merge_dicts(copy.deepcopy(DEFAULTS), _load_yaml_config()))
