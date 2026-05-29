import json
import time
import asyncio
from typing import Any, Dict, List, Optional, Tuple, Union
import redis.asyncio as aioredis
from app.config import settings
from app.utils.logger import logger

class MockRedis:
    def __init__(self):
        self._store: Dict[str, Tuple[bytes, Optional[float]]] = {}
        self._sorted_sets: Dict[str, Dict[str, float]] = {}

    def _is_expired(self, key: str) -> bool:
        if key not in self._store:
            return True
        _, expire_at = self._store[key]
        if expire_at is not None and time.time() > expire_at:
            del self._store[key]
            return True
        return False

    async def get(self, key: str) -> Optional[bytes]:
        if self._is_expired(key):
            return None
        val, _ = self._store[key]
        return val

    async def set(self, key: str, value: Union[str, bytes], ex: Optional[int] = None) -> bool:
        expire_at = None
        if ex is not None:
            expire_at = time.time() + ex
        
        if isinstance(value, str):
            val_bytes = value.encode("utf-8")
        else:
            val_bytes = value
            
        self._store[key] = (val_bytes, expire_at)
        return True

    async def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            if key in self._store:
                del self._store[key]
                count += 1
            if key in self._sorted_sets:
                del self._sorted_sets[key]
                count += 1
        return count

    async def zincrby(self, name: str, amount: float, value: str) -> float:
        if name not in self._sorted_sets:
            self._sorted_sets[name] = {}
        current = self._sorted_sets[name].get(value, 0.0)
        new_score = current + amount
        self._sorted_sets[name][value] = new_score
        return new_score

    async def zrevrange(self, name: str, start: int, end: int, withscores: bool = False) -> List[Union[bytes, Tuple[bytes, float]]]:
        if name not in self._sorted_sets:
            return []
        # Sort items descending by score
        items = list(self._sorted_sets[name].items())
        items.sort(key=lambda x: x[1], reverse=True)
        
        # Paginate (slice)
        sliced = items[start:end+1] if end != -1 else items[start:]
        
        result = []
        for val, score in sliced:
            val_bytes = val.encode("utf-8")
            if withscores:
                result.append((val_bytes, score))
            else:
                result.append(val_bytes)
        return result

    async def keys(self, pattern: str = "*") -> List[bytes]:
        # Simple glob to regex matching
        import re
        regex_pattern = pattern.replace("*", ".*").replace("?", ".")
        regex = re.compile(f"^{regex_pattern}$")
        
        matched_keys = []
        # check basic store
        for k in list(self._store.keys()):
            if not self._is_expired(k) and regex.match(k):
                matched_keys.append(k.encode("utf-8"))
        # check sorted sets
        for k in self._sorted_sets.keys():
            if regex.match(k):
                matched_keys.append(k.encode("utf-8"))
        return matched_keys

    async def flushdb(self) -> bool:
        self._store.clear()
        self._sorted_sets.clear()
        return True


# Setup Cache Clients
_actual_redis: Any = None
is_mock_redis: bool = False

class RedisWrapper:
    def __getattr__(self, name):
        global _actual_redis
        if _actual_redis is None:
            raise RuntimeError("Cache not initialized. Call init_cache() first.")
        return getattr(_actual_redis, name)

redis_client = RedisWrapper()

async def init_cache():
    global _actual_redis, is_mock_redis
    try:
        logger.info(f"Connecting to Redis at: {settings.REDIS_URI}...")
        # Create Redis Client
        client = aioredis.from_url(settings.REDIS_URI, socket_timeout=2.0)
        # Verify connection by running a simple ping
        await client.ping()
        
        _actual_redis = client
        is_mock_redis = False
        logger.info("Successfully connected to Redis cache!")
    except Exception as e:
        logger.warning(f"Could not connect to Redis: {e}. Falling back to In-Memory Mock Cache.")
        _actual_redis = MockRedis()
        is_mock_redis = True
        logger.info("Mock Cache initialized successfully in fallback mode!")
