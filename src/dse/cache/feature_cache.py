"""
Disk-backed JSON cache for ViewFeatures.

Cache key: (view_id, element_count)
  - view_id  is stable across a Revit session.
  - element_count is a cheap proxy for "has the view changed".
    It does not catch element edits that preserve count; callers can
    call invalidate(view_id) or clear() when they know a view changed.

Storage layout  (one JSON file per cache directory):
  <cache_dir>/feature_cache.json
  {
    "<view_id>:<element_count>": {
      "view_id": int,
      "view_kind": str,
      "tokens": {str: float, ...},
      "geom_fingerprint": [float, ...],
      "fine_metrics": {str: float},
      "debug": {...}
    },
    ...
  }
"""

import json
import os
import tempfile


_DEFAULT_CACHE_DIR = os.path.join(tempfile.gettempdir(), "dse_feature_cache")
_CACHE_FILE_NAME = "feature_cache.json"


class FeatureCache:
    """In-process + disk-backed cache for extracted ViewFeatures dicts.

    Parameters
    ----------
    cache_dir : str, optional
        Directory for the JSON cache file.  Created on first write.
        Defaults to ``%TEMP%/dse_feature_cache``.
    max_entries : int, optional
        Evict oldest entries (by insertion order) when the cache exceeds
        this size.  0 = unlimited.
    """

    def __init__(self, cache_dir=None, max_entries=2000):
        self._cache_dir = cache_dir or _DEFAULT_CACHE_DIR
        self._max_entries = max_entries
        self._memory: dict = {}       # {cache_key: features_dict}
        self._loaded = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, view_id, element_count):
        """Return cached features dict or None."""
        self._ensure_loaded()
        return self._memory.get(self._key(view_id, element_count))

    def put(self, view_id, element_count, features_dict):
        """Store features dict and flush to disk."""
        self._ensure_loaded()
        key = self._key(view_id, element_count)
        self._memory[key] = features_dict
        self._evict_if_needed()
        self._flush()

    def invalidate(self, view_id):
        """Remove all entries for a given view_id (any element_count)."""
        self._ensure_loaded()
        prefix = "{view_id}:".format(view_id=view_id)
        stale = [k for k in self._memory if k.startswith(prefix)]
        for key in stale:
            del self._memory[key]
        if stale:
            self._flush()

    def clear(self):
        """Wipe the entire cache (memory + disk)."""
        self._memory = {}
        self._flush()

    def size(self):
        return len(self._memory)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _key(view_id, element_count):
        return "{}:{}".format(int(view_id), int(element_count))

    def _cache_path(self):
        return os.path.join(self._cache_dir, _CACHE_FILE_NAME)

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True
        path = self._cache_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, "r") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                self._memory = data
        except Exception:
            # Corrupt or unreadable cache: start fresh.
            self._memory = {}

    def _flush(self):
        try:
            os.makedirs(self._cache_dir, exist_ok=True)
            path = self._cache_path()
            tmp = path + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(self._memory, fh)
            os.replace(tmp, path)
        except Exception:
            # Disk write failures must not crash the pipeline.
            pass

    def _evict_if_needed(self):
        if self._max_entries <= 0:
            return
        overflow = len(self._memory) - self._max_entries
        if overflow <= 0:
            return
        # dict is insertion-ordered in Python 3.7+
        evict_keys = list(self._memory.keys())[:overflow]
        for key in evict_keys:
            del self._memory[key]


# Module-level singleton so all pipeline calls share one cache instance.
_DEFAULT_CACHE = FeatureCache()


def get_default_cache():
    return _DEFAULT_CACHE
