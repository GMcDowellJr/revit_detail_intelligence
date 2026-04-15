import glob
import hashlib
import json
import os
import warnings
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


def _doc_scope_from_source(source_doc_id: Optional[str], source_doc_name: Optional[str]) -> Optional[str]:
    source_doc_id = None if source_doc_id is None else str(source_doc_id).strip() or None
    source_doc_name = None if source_doc_name is None else str(source_doc_name).strip() or None
    payload = {
        "source_doc_id": source_doc_id,
        "source_doc_name": source_doc_name,
    }
    if payload["source_doc_id"] is None and payload["source_doc_name"] is None:
        payload = {"source_scope": "<no-doc>"}
    txt = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha1(txt.encode("utf-8")).hexdigest()[:16]


def _doc_scope_from_bundle(bundle: ViewFeatureBundle) -> Optional[str]:
    search_features = getattr(bundle, "search_features", None)
    return _doc_scope_from_source(
        getattr(search_features, "source_doc_id", None),
        getattr(search_features, "source_doc_name", None),
    )


def cache_file_for_view(cache_root: str, view_id: int, doc_scope: Optional[str] = None) -> str:
    view_dir = os.path.join(cache_root, "view_features")
    if doc_scope:
        filename = "view_{}__doc_{}.json".format(int(view_id), doc_scope)
        return os.path.join(view_dir, filename)
    pattern = os.path.join(view_dir, "view_{}__doc_*.json".format(int(view_id)))
    matches = sorted(glob.glob(pattern))
    if matches:
        return matches[0]
    return os.path.join(view_dir, "view_{}.json".format(int(view_id)))


def read_cache_record(
    cache_root: str,
    view_id: int,
    source_doc_id: Optional[str] = None,
    source_doc_name: Optional[str] = None,
) -> Optional[ViewFeatureCacheEntry]:
    doc_scope = _doc_scope_from_source(source_doc_id, source_doc_name)
    path = cache_file_for_view(cache_root, view_id, doc_scope=doc_scope)
    if not os.path.exists(path):
        if doc_scope is None:
            return None
        path = cache_file_for_view(cache_root, view_id)
        if not os.path.exists(path):
            return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return deserialize_cache_entry(handle.read())
    except Exception as exc:
        warnings.warn(
            "DSE: failed to read cache record in read_cache_record: {}".format(exc),
            RuntimeWarning,
            stacklevel=2,
        )
        return None


def write_cache_record(cache_root: str, entry: ViewFeatureCacheEntry) -> str:
    doc_scope = _doc_scope_from_bundle(entry.payload)
    path = cache_file_for_view(cache_root, entry.view_id, doc_scope=doc_scope)
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(serialize_cache_entry(entry))
    return path


def invalidate_cache_record(
    cache_root: str,
    view_id: int,
    source_doc_id: Optional[str] = None,
    source_doc_name: Optional[str] = None,
) -> bool:
    doc_scope = _doc_scope_from_source(source_doc_id, source_doc_name)
    path = cache_file_for_view(cache_root, view_id, doc_scope=doc_scope)
    if not os.path.exists(path) and doc_scope is not None:
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
    source_doc_id: Optional[str] = None,
    source_doc_name: Optional[str] = None,
) -> Tuple[Optional[ViewFeatureBundle], str]:
    payload = in_memory_cache.get_if_current(view_id, state_hash, pipeline_version, schema_version)
    if payload is not None:
        return payload, "hit_memory"

    disk_entry = read_cache_record(cache_root, view_id, source_doc_id=source_doc_id, source_doc_name=source_doc_name)
    if disk_entry is None:
        return None, "miss"

    if (
        disk_entry.state_hash != state_hash
        or disk_entry.pipeline_version != pipeline_version
        or disk_entry.schema_version != schema_version
    ):
        invalidate_cache_record(cache_root, view_id, source_doc_id=source_doc_id, source_doc_name=source_doc_name)
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
    write_disk: bool = True,
):
    entry = ViewFeatureCacheEntry(
        view_id=view_id,
        state_hash=state_hash,
        schema_version=schema_version,
        pipeline_version=pipeline_version,
        payload=payload,
    )
    in_memory_cache.put(entry)
    if write_disk:
        write_cache_record(cache_root, entry)


def resolve_view_cache_root(config: Dict[str, object]) -> str:
    return ensure_dir(resolve_cache_root(config))


GLOBAL_VIEW_FEATURE_CACHE = ViewFeatureCache()
