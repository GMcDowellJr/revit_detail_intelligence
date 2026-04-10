import json
import os
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from dse.io_paths import ensure_dir, resolve_cache_root
from dse.models import (
    ViewFeatureBundle,
    ViewPresentationSummary,
    ViewSearchFeatures,
    ViewStateSignature,
)


@dataclass
class ViewFeatureCacheEntry:
    view_id: int
    state_hash: str
    schema_version: str
    pipeline_version: str
    payload: ViewFeatureBundle


@dataclass
class ViewFeatureCache:
    schema_version: str = "view_feature_cache.v0.3"
    entries: Dict[int, ViewFeatureCacheEntry] = field(default_factory=dict)

    def get_if_current(
        self,
        view_id: int,
        state_hash: str,
        pipeline_version: str,
        schema_version: Optional[str] = None,
    ):
        expected_schema = schema_version or self.schema_version
        entry = self.entries.get(int(view_id))
        if entry is None:
            return None
        if (
            entry.state_hash != state_hash
            or entry.pipeline_version != pipeline_version
            or entry.schema_version != expected_schema
        ):
            return None
        return entry.payload

    def put(self, entry: ViewFeatureCacheEntry):
        self.entries[int(entry.view_id)] = entry


def _bundle_to_dict(bundle: ViewFeatureBundle) -> Dict[str, object]:
    return {
        "state_signature": bundle.state_signature.__dict__,
        "search_features": bundle.search_features.__dict__,
        "presentation_summary": bundle.presentation_summary.__dict__,
    }


def _bundle_from_dict(payload: Dict[str, object]) -> ViewFeatureBundle:
    return ViewFeatureBundle(
        state_signature=ViewStateSignature(**payload["state_signature"]),
        search_features=ViewSearchFeatures(**payload["search_features"]),
        presentation_summary=ViewPresentationSummary(**payload["presentation_summary"]),
    )


def serialize_cache_entry(entry: ViewFeatureCacheEntry) -> str:
    return json.dumps(
        {
            "view_id": entry.view_id,
            "state_hash": entry.state_hash,
            "schema_version": entry.schema_version,
            "pipeline_version": entry.pipeline_version,
            "payload": _bundle_to_dict(entry.payload),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def deserialize_cache_entry(payload_txt: str) -> ViewFeatureCacheEntry:
    raw = json.loads(payload_txt)
    return ViewFeatureCacheEntry(
        view_id=int(raw["view_id"]),
        state_hash=str(raw["state_hash"]),
        schema_version=str(raw["schema_version"]),
        pipeline_version=str(raw["pipeline_version"]),
        payload=_bundle_from_dict(raw["payload"]),
    )


def cache_file_for_view(cache_root: str, view_id: int) -> str:
    return os.path.join(cache_root, "view_features", "view_{}.json".format(int(view_id)))


def read_cache_record(cache_root: str, view_id: int) -> Optional[ViewFeatureCacheEntry]:
    path = cache_file_for_view(cache_root, view_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return deserialize_cache_entry(handle.read())
    except Exception as exc:
        raise RuntimeError("DSE: failed to read cache record in read_cache_record") from exc


def write_cache_record(cache_root: str, entry: ViewFeatureCacheEntry) -> str:
    path = cache_file_for_view(cache_root, entry.view_id)
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(serialize_cache_entry(entry))
    return path


def invalidate_cache_record(cache_root: str, view_id: int) -> bool:
    path = cache_file_for_view(cache_root, view_id)
    if not os.path.exists(path):
        return False
    os.remove(path)
    return True


def get_cached_bundle_with_diagnostics(
    *,
    in_memory_cache: ViewFeatureCache,
    cache_root: str,
    view_id: int,
    state_hash: str,
    pipeline_version: str,
    schema_version: str,
) -> Tuple[Optional[ViewFeatureBundle], str]:
    payload = in_memory_cache.get_if_current(view_id, state_hash, pipeline_version, schema_version)
    if payload is not None:
        return payload, "hit_memory"

    disk_entry = read_cache_record(cache_root, view_id)
    if disk_entry is None:
        return None, "miss"

    if (
        disk_entry.state_hash != state_hash
        or disk_entry.pipeline_version != pipeline_version
        or disk_entry.schema_version != schema_version
    ):
        invalidate_cache_record(cache_root, view_id)
        return None, "invalidated"

    in_memory_cache.put(disk_entry)
    return disk_entry.payload, "hit_disk"


def put_bundle_in_caches(
    *,
    in_memory_cache: ViewFeatureCache,
    cache_root: str,
    view_id: int,
    state_hash: str,
    pipeline_version: str,
    schema_version: str,
    payload: ViewFeatureBundle,
):
    entry = ViewFeatureCacheEntry(
        view_id=view_id,
        state_hash=state_hash,
        schema_version=schema_version,
        pipeline_version=pipeline_version,
        payload=payload,
    )
    in_memory_cache.put(entry)
    write_cache_record(cache_root, entry)


def resolve_view_cache_root(config: Dict[str, object]) -> str:
    return ensure_dir(resolve_cache_root(config))


GLOBAL_VIEW_FEATURE_CACHE = ViewFeatureCache()
