"""
Simple in-memory sliding-window rate limiter middleware.

No external dependencies — uses a defaultdict of deque to track request
timestamps per (IP, path-prefix). This is intentionally lightweight for
a single-process development / demo deployment; replace with Redis-backed
limits before running multiple workers.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# (requests, window_seconds) per path prefix
_LIMITS: dict[str, tuple[int, int]] = {
    "/api/cv/upload":       (10, 60),    # 10 uploads / minute
    "/api/workflow/run":    (20, 60),    # 20 workflow runs / minute
    "/api/alerts":          (60, 60),    # 60 alert API calls / minute
}

_DEFAULT_LIMIT = (120, 60)  # 120 requests / minute for everything else

# {(ip, prefix): deque of timestamps}
_buckets: dict[tuple[str, str], deque] = defaultdict(deque)


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        ip = _get_client_ip(request)

        # Find the most specific matching prefix
        limit, window = _DEFAULT_LIMIT
        for prefix, (lim, win) in _LIMITS.items():
            if path.startswith(prefix):
                limit, window = lim, win
                break

        key = (ip, path.split("/")[-1] if "/" in path else path)
        now = time.monotonic()
        bucket = _buckets[key]

        # Evict old timestamps outside the sliding window
        while bucket and bucket[0] < now - window:
            bucket.popleft()

        if len(bucket) >= limit:
            return Response(
                content='{"detail":"Too many requests. Please slow down."}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(window)},
            )

        bucket.append(now)
        return await call_next(request)
