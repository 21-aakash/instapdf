import time
import threading
from collections import defaultdict
from typing import Dict, Any, Optional, Tuple

class RateLimiter:
    """
    Lightweight, thread-safe in-memory sliding window rate limiter.
    Limits requests per client IP to prevent abuse and denial of service.
    """
    def __init__(self, max_requests: int = 20, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, client_ip: str) -> Tuple[bool, int]:
        """
        Returns (is_allowed, seconds_until_reset).
        """
        now = time.time()
        with self._lock:
            # Clean expired timestamps
            valid_timestamps = [t for t in self.requests[client_ip] if now - t < self.window_seconds]
            self.requests[client_ip] = valid_timestamps

            if len(valid_timestamps) >= self.max_requests:
                earliest = valid_timestamps[0]
                retry_after = int(self.window_seconds - (now - earliest)) + 1
                return False, max(1, retry_after)

            self.requests[client_ip].append(now)
            return True, 0


class TTLCache:
    """
    Thread-safe in-memory cache with Time-To-Live (TTL) and auto-eviction.
    Prevents redundant external requests for recently queried Instagram posts.
    """
    def __init__(self, ttl_seconds: int = 900, max_entries: int = 150):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.cache: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            if key in self.cache:
                timestamp, data = self.cache[key]
                if now - timestamp < self.ttl_seconds:
                    return data
                del self.cache[key]
        return None

    def set(self, key: str, value: Any):
        now = time.time()
        with self._lock:
            # Simple eviction if exceeding max entries
            if len(self.cache) >= self.max_entries:
                oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][0], default=None)
                if oldest_key:
                    del self.cache[oldest_key]
            self.cache[key] = (now, value)
