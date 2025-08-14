import os
from pathlib import Path
from typing import Optional

from diskcache import Cache

_cache: Optional[Cache] = None

def get_cache() -> Cache:
    global _cache
    if _cache is not None:
        return _cache
    cache_dir = os.getenv("CHATBOT_CACHE_DIR", ".cache")
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    _cache = Cache(cache_dir)
    return _cache