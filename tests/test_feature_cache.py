"""Tests for src/dse/cache/feature_cache.py"""

import json
import os
import tempfile

import pytest

from dse.cache.feature_cache import FeatureCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cache(tmp_path, max_entries=100):
    return FeatureCache(cache_dir=str(tmp_path), max_entries=max_entries)


def _sample_features(view_id=1):
    return {
        "view_id": view_id,
        "view_kind": "DRAFTING",
        "tokens": {"detail_component:Bracket|Standard": 2.0},
        "geom_fingerprint": [0.5, 0.5, 0.0],
        "fine_metrics": {"pt_count": 4.0, "bbox_aspect": 1.2, "linework_density": 0.3},
        "debug": {"scale": 0.1, "pt_count": 4},
    }


# ---------------------------------------------------------------------------
# Basic get/put round-trip
# ---------------------------------------------------------------------------

def test_get_miss_returns_none(tmp_path):
    cache = _make_cache(tmp_path)
    assert cache.get(view_id=99, element_count=10) is None


def test_put_then_get_returns_features(tmp_path):
    cache = _make_cache(tmp_path)
    feat = _sample_features(view_id=1)
    cache.put(view_id=1, element_count=5, features_dict=feat)
    result = cache.get(view_id=1, element_count=5)
    assert result == feat


def test_wrong_element_count_misses(tmp_path):
    cache = _make_cache(tmp_path)
    feat = _sample_features(view_id=1)
    cache.put(view_id=1, element_count=5, features_dict=feat)
    assert cache.get(view_id=1, element_count=6) is None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_persists_to_disk(tmp_path):
    cache = _make_cache(tmp_path)
    feat = _sample_features(view_id=42)
    cache.put(42, 10, feat)

    # A new cache instance pointing at the same dir should load the file.
    cache2 = _make_cache(tmp_path)
    assert cache2.get(42, 10) == feat


def test_disk_file_is_valid_json(tmp_path):
    cache = _make_cache(tmp_path)
    cache.put(1, 3, _sample_features(1))
    path = os.path.join(str(tmp_path), "feature_cache.json")
    with open(path) as fh:
        data = json.load(fh)
    assert isinstance(data, dict)
    assert len(data) == 1


def test_corrupt_cache_file_starts_fresh(tmp_path):
    path = os.path.join(str(tmp_path), "feature_cache.json")
    os.makedirs(str(tmp_path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write("not valid json {{{{")

    cache = _make_cache(tmp_path)
    assert cache.get(1, 1) is None  # should not raise


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------

def test_invalidate_removes_view(tmp_path):
    cache = _make_cache(tmp_path)
    cache.put(1, 5, _sample_features(1))
    cache.put(2, 8, _sample_features(2))

    cache.invalidate(1)

    assert cache.get(1, 5) is None
    assert cache.get(2, 8) is not None


def test_invalidate_nonexistent_view_is_noop(tmp_path):
    cache = _make_cache(tmp_path)
    cache.put(1, 5, _sample_features(1))
    cache.invalidate(999)  # should not raise
    assert cache.get(1, 5) is not None


def test_clear_wipes_all_entries(tmp_path):
    cache = _make_cache(tmp_path)
    for i in range(5):
        cache.put(i, i, _sample_features(i))
    cache.clear()
    assert cache.size() == 0
    for i in range(5):
        assert cache.get(i, i) is None


# ---------------------------------------------------------------------------
# Eviction
# ---------------------------------------------------------------------------

def test_max_entries_evicts_oldest(tmp_path):
    cache = _make_cache(tmp_path, max_entries=3)
    for i in range(5):
        cache.put(i, 0, _sample_features(i))

    # Only 3 entries should remain; the first two inserted should be gone.
    assert cache.size() == 3
    assert cache.get(0, 0) is None
    assert cache.get(1, 0) is None
    assert cache.get(4, 0) is not None


def test_unlimited_max_entries(tmp_path):
    cache = _make_cache(tmp_path, max_entries=0)
    for i in range(50):
        cache.put(i, 0, _sample_features(i))
    assert cache.size() == 50


# ---------------------------------------------------------------------------
# Size
# ---------------------------------------------------------------------------

def test_size_reflects_entries(tmp_path):
    cache = _make_cache(tmp_path)
    assert cache.size() == 0
    cache.put(1, 1, _sample_features(1))
    assert cache.size() == 1
    cache.put(2, 1, _sample_features(2))
    assert cache.size() == 2