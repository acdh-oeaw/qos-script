import asyncio
import logging
from typing import Any, Dict, List, Optional

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


class ThrottledK8sClient:
    def __init__(self, requests_per_second: float = 5.0):
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.networking_v1 = client.NetworkingV1Api()
        self._cache: Dict[str, Any] = {}
        self._rps = requests_per_second
        self._min_interval = 1.0 / requests_per_second
        self._last_call = 0.0

    async def _throttle(self):
        import time
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

    async def get_all_ingresses(self) -> List[Any]:
        cache_key = "ingresses"
        if cache_key in self._cache:
            return self._cache[cache_key]

        ingresses = []
        _continue = None

        while True:
            await self._throttle()
            try:
                resp = self.networking_v1.list_ingress_for_all_namespaces(
                    limit=100,
                    _continue=_continue,
                )
                ingresses.extend(resp.items)
                _continue = resp.metadata._continue
                if not _continue:
                    break
            except ApiException as e:
                if e.status == 429:
                    retry_after = int(e.headers.get("Retry-After", 5))
                    logger.warning(f"K8s API throttled, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue
                raise

        self._cache[cache_key] = ingresses
        logger.info(f"Fetched {len(ingresses)} ingresses")
        return ingresses

    async def get_all_deployments(self) -> List[Any]:
        cache_key = "deployments"
        if cache_key in self._cache:
            return self._cache[cache_key]

        deployments = []
        _continue = None

        while True:
            await self._throttle()
            try:
                resp = self.apps_v1.list_deployment_for_all_namespaces(
                    limit=100,
                    _continue=_continue,
                )
                deployments.extend(resp.items)
                _continue = resp.metadata._continue
                if not _continue:
                    break
            except ApiException as e:
                if e.status == 429:
                    retry_after = int(e.headers.get("Retry-After", 5))
                    logger.warning(f"K8s API throttled, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue
                raise

        self._cache[cache_key] = deployments
        logger.info(f"Fetched {len(deployments)} deployments")
        return deployments

    def clear_cache(self):
        self._cache.clear()
