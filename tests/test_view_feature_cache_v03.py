from dse.cache.view_feature_cache import ViewFeatureCache, ViewFeatureCacheEntry
from dse.models import (
    ViewFeatureBundle,
    ViewPresentationSummary,
    ViewSearchFeatures,
    ViewStateSignature,
    legacy_view_features_from_search,
)


def _bundle(view_id=10, state_hash="abc"):
    return ViewFeatureBundle(
        state_signature=ViewStateSignature(
            view_id=view_id,
            view_kind="DRAFTING",
            state_hash=state_hash,
        ),
        search_features=ViewSearchFeatures(
            view_id=view_id,
            view_kind="DRAFTING",
            tokens_stable={"type_sig:A|B": 1.5},
            tokens_context={"line_style:Thin": 1.0},
            geom_hist_knn_endpoints=[0.2, 0.8],
            fine_metrics={"pt_count": 4.0},
        ),
        presentation_summary=ViewPresentationSummary(
            view_id=view_id,
            display_name="View A",
        ),
    )


def test_cache_requires_state_hash_pipeline_and_schema_match():
    cache = ViewFeatureCache(schema_version="view_feature_cache.v0.3")
    bundle = _bundle()
    cache.put(
        ViewFeatureCacheEntry(
            view_id=10,
            state_hash="abc",
            schema_version="view_search_features.v0.3",
            pipeline_version="p1",
            payload=bundle,
        )
    )

    assert cache.get_if_current(10, "abc", pipeline_version="p1", schema_version="view_search_features.v0.3") is bundle
    assert cache.get_if_current(10, "different", pipeline_version="p1", schema_version="view_search_features.v0.3") is None
    assert cache.get_if_current(10, "abc", pipeline_version="p2", schema_version="view_search_features.v0.3") is None
    assert cache.get_if_current(10, "abc", pipeline_version="p1", schema_version="other") is None


def test_legacy_adapter_merges_stable_and_context_tokens():
    bundle = _bundle()
    legacy = legacy_view_features_from_search(bundle.search_features)

    assert legacy.view_id == bundle.search_features.view_id
    assert legacy.tokens["type_sig:A|B"] == 1.5
    assert legacy.tokens["line_style:Thin"] == 1.0
    assert legacy.geom_fingerprint == [0.2, 0.8]
