"""JSON file-based cache for parsed ULog data.

Uses MD5 hash of the .ulg file as cache key. Parsed results are stored
as JSON files to avoid re-parsing large binary logs on every request.
"""

import json
import os
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


# Cache directory (relative to project root)
CACHE_DIR = "data/log_cache"


def _ensure_cache_dir():
    """Ensure cache directory exists."""
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)


def _file_hash(filepath: str) -> str:
    """Compute MD5 hash of file content for cache invalidation."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        # Read in chunks for large files
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_path(file_hash: str) -> str:
    """Get the cache file path for a given hash."""
    return os.path.join(CACHE_DIR, f"{file_hash}.json")


def get_cached(filepath: str) -> Optional[Dict[str, Any]]:
    """Retrieve cached parse result for a log file.

    Args:
        filepath: Absolute path to the .ulg file

    Returns:
        Cached parse result dict, or None if not cached / stale
    """
    _ensure_cache_dir()

    fhash = _file_hash(filepath)
    cache_file = _cache_path(fhash)

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
            # Verify the cached data matches the file
            if data.get("_cache_meta", {}).get("file_hash") == fhash:
                return data
        except (json.JSONDecodeError, KeyError):
            # Corrupt cache file, delete it
            os.remove(cache_file)

    return None


def set_cached(filepath: str, data: Dict[str, Any]) -> str:
    """Store parse result in cache.

    Args:
        filepath: Absolute path to the .ulg file
        data: Parsed log data to cache

    Returns:
        Cache file path
    """
    _ensure_cache_dir()

    fhash = _file_hash(filepath)
    cache_file = _cache_path(fhash)

    # Add cache metadata
    data["_cache_meta"] = {
        "file_hash": fhash,
        "source_file": filepath,
        "cached_at": datetime.now().isoformat(),
        "file_size": os.path.getsize(filepath),
    }

    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2, default=str)

    return cache_file


def is_cached(filepath: str) -> bool:
    """Check if a log file has a valid cache entry."""
    return get_cached(filepath) is not None


def invalidate_cache(filepath: str) -> bool:
    """Remove cache entry for a specific file.

    Returns True if cache was found and removed.
    """
    _ensure_cache_dir()

    fhash = _file_hash(filepath)
    cache_file = _cache_path(fhash)

    if os.path.exists(cache_file):
        os.remove(cache_file)
        return True
    return False


def clear_all_cache() -> int:
    """Remove all cache files. Returns count of files removed."""
    _ensure_cache_dir()

    count = 0
    for f in os.listdir(CACHE_DIR):
        if f.endswith(".json"):
            os.remove(os.path.join(CACHE_DIR, f))
            count += 1
    return count


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    _ensure_cache_dir()

    files = [f for f in os.listdir(CACHE_DIR) if f.endswith(".json")]
    total_size = sum(
        os.path.getsize(os.path.join(CACHE_DIR, f)) for f in files
    )

    return {
        "cached_files": len(files),
        "total_size_mb": round(total_size / 1024 / 1024, 2),
        "cache_dir": os.path.abspath(CACHE_DIR),
    }
