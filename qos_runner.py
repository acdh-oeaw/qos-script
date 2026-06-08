import asyncio
import logging
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List

from checks import check_acdh_logo, check_helpdesk_email, check_accessibility, check_imprint_page
from config import config as app_config
from utils.http_client import ResilientHttpClient
from utils.k8s_client import ThrottledK8sClient

logger = logging.getLogger(__name__)


@dataclass
class QoSConfig:
    http_requests_per_second: float
    max_concurrent_http: int
    http_timeout: int
    max_retries: int
    k8s_requests_per_second: float
    batch_size: int
    batch_delay: float
    max_services: int
    dry_run: bool

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]):
        return cls(
            http_requests_per_second=cfg["http"]["requests_per_second"],
            max_concurrent_http=cfg["http"]["max_concurrent"],
            http_timeout=cfg["http"]["timeout_seconds"],
            max_retries=cfg["http"]["max_retries"],
            k8s_requests_per_second=cfg["k8s"]["requests_per_second"],
            batch_size=cfg["runner"]["batch_size"],
            batch_delay=cfg["runner"]["batch_delay"],
            max_services=cfg["runner"]["max_services"],
            dry_run=cfg["runner"]["dry_run"],
        )


def format_checks_for_redmine(checks: List[Dict[str, Any]]) -> str:
    lines = ["|_. Check |_. Status |_. Details |"]
    for c in checks:
        status_icon = {
            "PASS": "✅",
            "FAIL": "❌",
            "WARN": "⚠️",
            "ERROR": "🔧",
        }.get(c.get("status"), "❓")
        details = c.get("details", "")
        if c.get("issues"):
            details += "\n" + "\n".join(f"* {i}" for i in c["issues"])
        lines.append(f"| {c['check']} | {status_icon} {c.get('status', 'UNKNOWN')} | {details} |")
    return "\n".join(lines)


async def fetch_service_page(
    http_client: ResilientHttpClient,
    url: str,
    dry_run: bool,
) -> Dict[str, Any]:
    """Fetch a service page or simulate a response in dry-run mode."""
    if dry_run:
        logger.info("Dry run: simulating fetch for %s", url)
        return {
            "status": 200,
            "text": "<html><head><title>Dry run</title></head><body>Dry run content</body></html>",
            "error": None,
            "skipped": False,
        }
    return await http_client.get(url)


async def run_checks_for_service(
    http_client: ResilientHttpClient,
    url: str,
    service_name: str,
    dry_run: bool,
) -> Dict[str, Any]:
    result = {"service": service_name, "url": url, "checks": []}
    response = await fetch_service_page(http_client, url, dry_run)

    if response["skipped"]:
        result["checks"].append({
            "check": "All",
            "status": "SKIP",
            "details": f"Skipped: {response['error']}",
        })
        return result

    if response["error"] or response["status"] >= 400:
        error_detail = response["error"] or f"HTTP {response['status']}"
        result["checks"].append({
            "check": "Reachability",
            "status": "FAIL",
            "details": error_detail,
        })
        return result

    html = response["text"]

    result["checks"] = [
        check_acdh_logo(html=html, url=url),
        check_helpdesk_email(html=html),
        await check_imprint_page(html=html, url=url, http_client=http_client),
        check_accessibility(html=html, url=url),
    ]
    return result


async def main():
    config = QoSConfig.from_config(app_config)
    logger.info(
        "Starting QoS run: http_rps=%s max_http=%s timeout=%ss batch_size=%s batch_delay=%ss k8s_rps=%s",
        config.http_requests_per_second,
        config.max_concurrent_http,
        config.http_timeout,
        config.batch_size,
        config.batch_delay,
        config.k8s_requests_per_second,
    )
    k8s = ThrottledK8sClient(requests_per_second=config.k8s_requests_per_second)
    logger.info("Starting service discovery")
    service_count = 0

    async def iter_service_batches():
        nonlocal service_count
        batch: List[Dict[str, Any]] = []
        async for ingress in k8s.list_ingresses():
            annotations = getattr(ingress.metadata, "annotations", {}) or {}
            for rule in getattr(ingress.spec, "rules", []) or []:
                if getattr(rule, "host", None):
                    service_count += 1
                    batch.append({
                        "name": f"{ingress.metadata.namespace}/{ingress.metadata.name}",
                        "namespace": ingress.metadata.namespace,
                        "url": f"https://{rule.host}",
                        "annotations": annotations,
                    })
                    if len(batch) >= config.batch_size:
                        yield batch
                        batch = []
                    if config.max_services > 0 and service_count >= config.max_services:
                        if batch:
                            yield batch
                        return
        if batch:
            yield batch

    def _build_failure_result(service: Dict[str, Any], error: Exception) -> Dict[str, Any]:
        return {
            "service": service.get("name", "unknown"),
            "url": service.get("url", ""),
            "checks": [
                {
                    "check": "Service Execution",
                    "status": "ERROR",
                    "details": f"{type(error).__name__}: {error}",
                }
            ],
        }

    async with ResilientHttpClient(
        requests_per_second=config.http_requests_per_second,
        max_concurrent=config.max_concurrent_http,
        timeout_seconds=config.http_timeout,
        max_retries=config.max_retries,
    ) as http_client:
        all_results = []
        batch_num = 0
        async for batch in iter_service_batches():
            batch_num += 1
            logger.info("Processing batch %s", batch_num)
            tasks = [
                run_checks_for_service(
                    http_client,
                    svc["url"],
                    svc["name"],
                    config.dry_run,
                )
                for svc in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for service, result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.error("Service task failed: %s", traceback.format_exception_only(type(result), result)[0].strip())
                    all_results.append(_build_failure_result(service, result))
                else:
                    all_results.append(result)

            logger.info("Batch delay: %ss", config.batch_delay)
            await asyncio.sleep(config.batch_delay)

    logger.info("Discovered %s services", service_count)
    logger.info("QoS check run finished")
    for result in all_results:
        logger.info("%s\n%s", result["service"], format_checks_for_redmine(result["checks"]))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
