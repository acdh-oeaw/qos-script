import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """Token bucket rate limiter."""
    requests_per_second: float = 2.0
    burst: int = 5
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)

    def __post_init__(self):
        self._tokens = float(self.burst)
        self._last_refill = time.monotonic()

    async def acquire(self):
        while True:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self.burst, self._tokens + elapsed * self.requests_per_second)
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return

            wait = (1.0 - self._tokens) / self.requests_per_second
            await asyncio.sleep(wait)
