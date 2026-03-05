import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional


@dataclass(frozen=True)
class SymbolKey:
    family_name: str
    type_name: str
    symbol_identity_hash: str
    family_id: Optional[int] = None
    symbol_id: Optional[int] = None

    @property
    def display_key(self) -> str:
        return "{}|{}".format(self.family_name, self.type_name)


@dataclass
class DescriptorVariant:
    variant_name: str
    descriptor_kind: str
    descriptor_vector: List[float]
    descriptor_vector_mirror: Optional[List[float]] = None
    bbox_aspect: float = 0.0
    bbox_area_norm: float = 0.0
    pixel_density: float = 0.0
    cc_stats: Dict[str, float] = field(default_factory=dict)


@dataclass
class SymbolDescriptor:
    schema: str
    key: SymbolKey
    build_method: str
    build_time_utc: str
    validity_token: str
    source_fingerprint: Dict[str, object]
    variants: Dict[str, DescriptorVariant]
    debug_preview_path: Optional[str] = None


@dataclass
class SymbolCacheEntry:
    symbol_id: int
    family_name: str
    type_name: str
    metadata: Dict[str, str]


@dataclass
class SymbolCacheModel:
    schema: str
    corpus_id: str
    pipeline_version: str
    descriptors: Dict[str, SymbolDescriptor] = field(default_factory=dict)
    stats: Dict[str, object] = field(default_factory=dict)


class SymbolCache(object):
    """In-memory symbol cache for the detail search pipeline."""

    def __init__(self):
        self._entries: Dict[int, SymbolCacheEntry] = {}

    def get(self, symbol_id) -> Optional[SymbolCacheEntry]:
        return self._entries.get(symbol_id)

    def put(self, entry: SymbolCacheEntry):
        self._entries[entry.symbol_id] = entry

    def clear(self):
        self._entries = {}


def stable_cache_key(symbol_key: SymbolKey) -> str:
    return "sym:{}|{}".format(symbol_key.symbol_identity_hash, symbol_key.display_key)


def _stable_json_dumps(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def hash_config(obj: object) -> str:
    data = _stable_json_dumps(obj).encode("utf-8")
    return hashlib.sha1(data).hexdigest()


def build_validity_token(identity_hash: str, export_config_hash: str, pipeline_version: str) -> str:
    payload = "{}|{}|{}".format(identity_hash, export_config_hash, pipeline_version)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def build_symbol_descriptor(
    symbol_key: SymbolKey,
    variants: Dict[str, DescriptorVariant],
    export_config_hash: str,
    pipeline_version: str,
    build_method: str,
    source_fingerprint: Optional[Dict[str, object]] = None,
    debug_preview_path: Optional[str] = None,
) -> SymbolDescriptor:
    validity = build_validity_token(
        identity_hash=symbol_key.symbol_identity_hash,
        export_config_hash=export_config_hash,
        pipeline_version=pipeline_version,
    )
    return SymbolDescriptor(
        schema="symbol_descriptor.v1",
        key=symbol_key,
        build_method=build_method,
        build_time_utc=datetime.now(timezone.utc).isoformat(),
        validity_token=validity,
        source_fingerprint=source_fingerprint or {},
        variants=variants,
        debug_preview_path=debug_preview_path,
    )


def cosine_sim(a: List[float], b: List[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(a[index] * b[index] for index in range(len(a)))
    n1 = math.sqrt(sum(x * x for x in a))
    n2 = math.sqrt(sum(y * y for y in b))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return dot / (n1 * n2)


def descriptor_similarity_variant(a: DescriptorVariant, b: DescriptorVariant) -> float:
    sim_primary = cosine_sim(a.descriptor_vector, b.descriptor_vector)
    if a.descriptor_vector_mirror is None or b.descriptor_vector_mirror is None:
        return sim_primary
    sim_mirror = cosine_sim(a.descriptor_vector, b.descriptor_vector_mirror)
    return max(sim_primary, sim_mirror)


def descriptor_similarity_best_of_variants(
    a_variants: Mapping[str, DescriptorVariant], b_variants: Mapping[str, DescriptorVariant]
) -> float:
    best = -1.0
    for va in a_variants.values():
        for vb in b_variants.values():
            best = max(best, descriptor_similarity_variant(va, vb))
    return max(best, 0.0)


def aggregate_symbol_descriptors(
    view_symbols: Mapping[SymbolKey, int],
    cache: SymbolCacheModel,
) -> Optional[List[float]]:
    vectors: List[List[float]] = []
    weights: List[int] = []
    for symbol_key, count in view_symbols.items():
        descriptor = cache.descriptors.get(stable_cache_key(symbol_key))
        if descriptor is None:
            continue
        variant = descriptor.variants.get("uniform")
        if variant is None and descriptor.variants:
            variant = next(iter(descriptor.variants.values()))
        if variant is None:
            continue
        vectors.append(variant.descriptor_vector)
        weights.append(count)

    if not vectors:
        return None

    length = len(vectors[0])
    if any(len(v) != length for v in vectors):
        return None

    weight_sum = float(sum(weights))
    out = [0.0] * length
    for idx, vector in enumerate(vectors):
        weight = weights[idx]
        for index, value in enumerate(vector):
            out[index] += value * weight
    return [value / weight_sum for value in out]


def symbol_multiset_similarity(
    view_a_symbols: Mapping[SymbolKey, int],
    view_b_symbols: Mapping[SymbolKey, int],
    cache: SymbolCacheModel,
) -> Optional[float]:
    vec_a = aggregate_symbol_descriptors(view_a_symbols, cache)
    vec_b = aggregate_symbol_descriptors(view_b_symbols, cache)
    if vec_a is None or vec_b is None:
        return None
    return cosine_sim(vec_a, vec_b)


def symbol_coverage_for_view(
    view_symbol_keys: Mapping[SymbolKey, int], cache: SymbolCacheModel
) -> float:
    total = float(sum(view_symbol_keys.values()))
    if total == 0:
        return 1.0

    have = 0
    for symbol_key, count in view_symbol_keys.items():
        if stable_cache_key(symbol_key) in cache.descriptors:
            have += count
    return float(have) / total


def compute_cache_stats(
    corpus_id: str,
    pipeline_version: str,
    export_config_hash: str,
    symbol_keys: Iterable[SymbolKey],
    descriptors: MutableMapping[str, SymbolDescriptor],
    failures: List[Dict[str, str]],
) -> Dict[str, object]:
    symbols_total = len(list(symbol_keys))
    methods = {"family_doc": 0, "isolated_render": 0}
    near_empty = 0

    for descriptor in descriptors.values():
        methods[descriptor.build_method] = methods.get(descriptor.build_method, 0) + 1
        if any(v.pixel_density < 0.001 for v in descriptor.variants.values()):
            near_empty += 1

    return {
        "corpus_id": corpus_id,
        "pipeline_version": pipeline_version,
        "export_config_hash": export_config_hash,
        "symbols_total": symbols_total,
        "symbols_cached": len(descriptors),
        "symbols_built_family_doc": methods.get("family_doc", 0),
        "symbols_built_isolated_render": methods.get("isolated_render", 0),
        "symbols_near_empty": near_empty,
        "failures_count": len(failures),
        "failure_samples": failures[:25],
    }
