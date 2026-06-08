import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional

import aiohttp

from utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    recovery_timeout: float = 60.0
    _failure_count: int = field(default=0, init=False)
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _last_failure_time: float = field(default=0.0, init=False)

    def record_success(self):
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self):
        import time
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(f"Circuit breaker OPEN after {self._failure_count} failures")

    def can_proceed(self) -> bool:
        import time
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time > self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                return True
            return False
        return True


class ResilientHttpClient:
    def __init__(
        self,
        requests_per_second: float = 2.0,
        max_concurrent: int = 5,
        timeout_seconds: int = 15,
        max_retries: int = 2,
    ):
        self.rate_limiter = RateLimiter(requests_per_second=requests_per_second)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.max_retries = max_retries
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_circuit_breaker(self, host: str) -> CircuitBreaker:
        if host not in self._circuit_breakers:
            self._circuit_breakers[host] = CircuitBreaker()
        return self._circuit_breakers[host]

    async def __aenter__(self):
        # Note: 'max_redirects' is not supported in this aiohttp version,
        # so we rely on aiohttp's default redirect behavior.
        self._session = aiohttp.ClientSession(
            timeout=self.timeout,
            headers={"User-Agent": "ACDH-QoS-Check/1.0"},
        )
        return self

    async def __aexit__(self, *args):
        if self._session:
            await self._session.close()

    async def get(self, url: str) -> Dict[str, Any]:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or url

        cb = self._get_circuit_breaker(host)

        if not cb.can_proceed():
            logger.info(f"Circuit breaker OPEN for {host}, skipping {url}")
            return {"status": 0, "text": "", "error": "circuit_breaker_open", "skipped": True}

        async with self.semaphore:
            for attempt in range(self.max_retries + 1):
                await self.rate_limiter.acquire()
                try:
                    async with self._session.get(url, ssl=False) as resp:
                        text = await resp.text()
                        if resp.status >= 400:
                            if resp.status in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                                wait = int(resp.headers.get("Retry-After", 2 ** attempt))
                                logger.warning(
                                    f"Transient HTTP {resp.status} for {url}, retrying after {wait}s"
                                )
                                cb.record_failure()
                                await asyncio.sleep(wait)
                                continue

                            cb.record_failure()
                            return {
                                "status": resp.status,
                                "text": text,
                                "error": f"HTTP {resp.status}",
                                "skipped": False,
                            }

                        cb.record_success()
                        return {
                            "status": resp.status,
                            "text": text,
                            "error": None,
                            "skipped": False,
                        }
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout for {url} (attempt {attempt + 1})")
                    cb.record_failure()
                except aiohttp.ClientError as e:
                    logger.warning(f"Client error for {url}: {e} (attempt {attempt + 1})")
                    cb.record_failure()
                except Exception as e:
                    logger.error(f"Unexpected error for {url}: {e}")
                    cb.record_failure()
                    break

                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)

        return {"status": 0, "text": "", "error": "max_retries_exceeded", "skipped": False}
