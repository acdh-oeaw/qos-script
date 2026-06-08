import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from checks import check_acdh_logo, check_helpdesk_email, check_accessibility, check_imprint_page
from utils.http_client import ResilientHttpClient
from utils.k8s_client import ThrottledK8sClient

logger = logging.getLogger(__name__)


@dataclass
class QoSConfig:
    http_requests_per_second: float = 2.0
    max_concurrent_http: int = 5
    http_timeout: int = 15
    k8s_requests_per_second: float = 5.0
    batch_size: int = 10
    batch_delay: float = 2.0


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


async def run_checks_for_service(
    http_client: ResilientHttpClient,
    url: str,
    service_name: str,
) -> Dict[str, Any]:
    result = {"service": service_name, "url": url, "checks": []}
    response = await http_client.get(url)

    if response["skipped"]:
        result["checks"].append({
            "check": "All",
            "status": "SKIP",
            "details": f"Skipped: {response['error']}",
        })
        return result

    if response["error"]:
        result["checks"].append({
            "check": "Reachability",
            "status": "FAIL",
            "details": response["error"],
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
    config = QoSConfig()
    k8s = ThrottledK8sClient(requests_per_second=config.k8s_requests_per_second)
    ingresses = await k8s.get_all_ingresses()

    services = []
    for ingress in ingresses:
        annotations = getattr(ingress.metadata, "annotations", {}) or {}
        for rule in getattr(ingress.spec, "rules", []) or []:
            if getattr(rule, "host", None):
                services.append({
                    "name": ingress.metadata.name,
                    "namespace": ingress.metadata.namespace,
                    "url": f"https://{rule.host}",
                    "annotations": annotations,
                })

    logger.info(f"Found {len(services)} services to check")

    async with ResilientHttpClient(
        requests_per_second=config.http_requests_per_second,
        max_concurrent=config.max_concurrent_http,
        timeout_seconds=config.http_timeout,
    ) as http_client:
        all_results = []
        for i in range(0, len(services), config.batch_size):
            batch = services[i : i + config.batch_size]
            batch_num = i // config.batch_size + 1
            total_batches = (len(services) + config.batch_size - 1) // config.batch_size
            logger.info(f"Processing batch {batch_num}/{total_batches}")

            tasks = [
                run_checks_for_service(http_client, svc["url"], svc["name"])
                for svc in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                if isinstance(r, Exception):
                    logger.error(f"Batch task failed: {r}")
                else:
                    all_results.append(r)

            if i + config.batch_size < len(services):
                logger.info(f"Batch delay: {config.batch_delay}s")
                await asyncio.sleep(config.batch_delay)

    logger.info("QoS check run finished")
    for result in all_results:
        logger.info("%s\n%s", result["service"], format_checks_for_redmine(result["checks"]))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
