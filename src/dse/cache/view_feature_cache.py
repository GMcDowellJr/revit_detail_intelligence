import json
from dataclasses import dataclass, field
from typing import Dict, Optional

from dse.models import ViewFeatureBundle


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


GLOBAL_VIEW_FEATURE_CACHE = ViewFeatureCache()


def serialize_cache_entry(entry: ViewFeatureCacheEntry) -> str:
    return json.dumps(
        {
            "view_id": entry.view_id,
            "state_hash": entry.state_hash,
            "schema_version": entry.schema_version,
            "pipeline_version": entry.pipeline_version,
            "payload": {
                "state_signature": entry.payload.state_signature.__dict__,
                "search_features": entry.payload.search_features.__dict__,
                "presentation_summary": entry.payload.presentation_summary.__dict__,
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )
