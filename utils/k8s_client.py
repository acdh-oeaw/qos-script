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

    async def _call_api(self, func, **kwargs):
        return await asyncio.to_thread(func, **kwargs)

    async def _stream_resources(self, api_call, **kwargs):
        _continue = None
        backoff = 5
        while True:
            await self._throttle()
            try:
                resp = await self._call_api(api_call, limit=100, _continue=_continue, **kwargs)
                for item in getattr(resp, "items", []):
                    yield item
                _continue = getattr(resp.metadata, "_continue", None)
                if not _continue:
                    break
                backoff = 5
            except ApiException as e:
                if e.status == 429:
                    retry_after = int(e.headers.get("Retry-After", backoff))
                    logger.warning(f"K8s API throttled, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    backoff = min(backoff * 2, 60)
                    continue
                raise

    async def list_ingresses(self):
        async for ingress in self._stream_resources(self.networking_v1.list_ingress_for_all_namespaces):
            yield ingress

    async def get_all_ingresses(self) -> List[Any]:
        ingresses = []
        async for ingress in self.list_ingresses():
            ingresses.append(ingress)
        return ingresses

    async def list_deployments(self):
        async for deployment in self._stream_resources(self.apps_v1.list_deployment_for_all_namespaces):
            yield deployment

    async def get_all_deployments(self) -> List[Any]:
        deployments = []
        async for deployment in self.list_deployments():
            deployments.append(deployment)
        return deployments

    def clear_cache(self):
        self._cache.clear()
