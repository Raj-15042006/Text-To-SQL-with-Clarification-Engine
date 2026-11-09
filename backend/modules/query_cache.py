import re
import time
import hashlib
from typing import Optional, Dict, Any

class QueryCache:
    """
    In-memory LRU/TTL cache for Text-to-SQL results.
    Eliminates redundant LLM round-trips for common questions, suggestions, and repeated queries.
    """
    def __init__(self, ttl_seconds: int = 900, max_size: int = 300):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache: Dict[str, Dict[str, Any]] = {}

    def normalize_query(self, query: str) -> str:
        """Normalizes user query by lowercasing, stripping punctuation, and collapsing whitespace."""
        q = query.strip().lower()
        q = re.sub(r'[^\w\s]', '', q)
        q = re.sub(r'\s+', ' ', q).strip()
        return q

    def _make_key(self, query: str, catalog: str, context_key: Optional[str] = None) -> str:
        norm_q = self.normalize_query(query)
        base = f"{catalog.strip().lower()}::{norm_q}"
        if context_key:
            base += f"::{context_key}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def get(self, query: str, catalog: str = "default", context_key: Optional[str] = None) -> Optional[Any]:
        key = self._make_key(query, catalog, context_key)
        entry = self._cache.get(key)
        if not entry:
            return None
        # Check TTL
        if time.time() - entry["timestamp"] > self.ttl_seconds:
            self._cache.pop(key, None)
            return None
        return entry["data"]

    def set(self, query: str, data: Any, catalog: str = "default", context_key: Optional[str] = None):
        if len(self._cache) >= self.max_size:
            # Evict oldest entry
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k]["timestamp"])
            self._cache.pop(oldest_key, None)

        key = self._make_key(query, catalog, context_key)
        self._cache[key] = {
            "timestamp": time.time(),
            "data": data
        }

    def clear(self):
        self._cache.clear()

query_cache = QueryCache()
