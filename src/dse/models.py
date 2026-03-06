from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ViewFeatures:
    view_id: int
    view_kind: str
    tokens: Dict[str, float]
    geom_fingerprint: List[float]
    fine_metrics: Dict[str, float]
    debug: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ViewStateSignature:
    """Deterministic extraction-state signature used for cache invalidation."""

    view_id: int
    view_kind: str
    source_doc_id: Optional[str] = None
    source_doc_name: Optional[str] = None
    content_bbox_q: List[float] = field(default_factory=list)
    element_count: int = 0
    type_count: int = 0
    curve_count_est: int = 0
    symbol_instance_count: int = 0
    center_graph_hash: str = ""
    view_settings_sig: str = ""
    state_hash: str = ""
    debug: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ViewSearchFeatures:
    """Richer persisted stage-1 feature set for retrieval/candidate generation."""

    view_id: int
    view_kind: str
    source_doc_id: Optional[str] = None
    source_doc_name: Optional[str] = None
    tokens_stable: Dict[str, float] = field(default_factory=dict)
    tokens_context: Dict[str, float] = field(default_factory=dict)
    token_counts_by_kind: Dict[str, int] = field(default_factory=dict)
    geom_hist_knn_endpoints: List[float] = field(default_factory=list)
    geom_orientation_hist: List[float] = field(default_factory=list)
    geom_length_hist: List[float] = field(default_factory=list)
    layout_graph_features: Dict[str, float] = field(default_factory=dict)
    fine_metrics: Dict[str, float] = field(default_factory=dict)
    symbol_multiset: Dict[str, int] = field(default_factory=dict)
    symbol_counts: Dict[str, int] = field(default_factory=dict)
    debug: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ViewPresentationSummary:
    """Lightweight view summary for future review/contact-sheet outputs."""

    view_id: int
    source_doc_id: Optional[str] = None
    source_doc_name: Optional[str] = None
    display_name: str = ""
    preview_key: str = ""
    top_tokens: List[str] = field(default_factory=list)
    top_symbols: List[str] = field(default_factory=list)
    feature_summary: Dict[str, Any] = field(default_factory=dict)
    debug: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ViewFeatureBundle:
    """Container record for extraction output and cache payloads."""

    state_signature: ViewStateSignature
    search_features: ViewSearchFeatures
    presentation_summary: ViewPresentationSummary


def legacy_view_features_from_search(search_features: ViewSearchFeatures) -> ViewFeatures:
    """Compatibility adapter for the existing stage-1 similarity scorer."""

    merged_tokens: Dict[str, float] = {}
    for token_map in (search_features.tokens_stable, search_features.tokens_context):
        for key, value in token_map.items():
            merged_tokens[key] = merged_tokens.get(key, 0.0) + float(value)

    return ViewFeatures(
        view_id=search_features.view_id,
        view_kind=search_features.view_kind,
        tokens=merged_tokens,
        geom_fingerprint=list(search_features.geom_hist_knn_endpoints),
        fine_metrics=dict(search_features.fine_metrics),
        debug=dict(search_features.debug),
    )
