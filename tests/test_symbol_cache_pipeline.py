from dse.cache.symbol_cache import (
    DescriptorVariant,
    SymbolCacheModel,
    SymbolKey,
    build_validity_token,
    compute_cache_stats,
    descriptor_similarity_best_of_variants,
    stable_cache_key,
    symbol_coverage_for_view,
    symbol_multiset_similarity,
)


def _variant(vector, mirror=None, density=0.1):
    return DescriptorVariant(
        variant_name="uniform",
        descriptor_kind="zernike_mag",
        descriptor_vector=vector,
        descriptor_vector_mirror=mirror,
        pixel_density=density,
    )


def _fake_descriptor(build_method, variant):
    return type("D", (), {"build_method": build_method, "variants": {"u": variant}})()


def test_stable_key_and_validity_token_are_deterministic():
    key = SymbolKey("Door", "Type A", "abc123")
    assert stable_cache_key(key) == "sym:abc123|Door|Type A"

    token = build_validity_token("abc123", "cfghash", "dse.pipeline.v0.2.1")
    assert token == build_validity_token("abc123", "cfghash", "dse.pipeline.v0.2.1")


def test_descriptor_similarity_uses_mirror_variant_when_available():
    a = {"uniform": _variant([1.0, 0.0], mirror=[0.0, 1.0])}
    b = {"uniform": _variant([0.0, 1.0], mirror=[1.0, 0.0])}

    assert descriptor_similarity_best_of_variants(a, b) == 1.0


def test_symbol_multiset_similarity_and_coverage():
    k1 = SymbolKey("FamA", "T1", "h1")
    k2 = SymbolKey("FamB", "T2", "h2")

    cache = SymbolCacheModel(schema="symbol_cache.v1", corpus_id="c", pipeline_version="v")
    cache.descriptors[stable_cache_key(k1)] = _fake_descriptor(
        "family_doc", _variant([1.0, 0.0])
    )

    view_a = {k1: 2, k2: 1}
    view_b = {k1: 1}

    assert symbol_coverage_for_view(view_a, cache) == 2.0 / 3.0
    assert symbol_multiset_similarity(view_a, view_b, cache) == 1.0


def test_compute_cache_stats_counts_near_empty_and_failures():
    k1 = SymbolKey("FamA", "T1", "h1")
    k2 = SymbolKey("FamB", "T2", "h2")

    descriptors = {
        stable_cache_key(k1): _fake_descriptor(
            "family_doc", _variant([1.0], density=0.0001)
        ),
        stable_cache_key(k2): _fake_descriptor(
            "isolated_render", _variant([1.0], density=0.5)
        ),
    }

    stats = compute_cache_stats(
        corpus_id="corpus",
        pipeline_version="v",
        export_config_hash="h",
        symbol_keys=[k1, k2],
        descriptors=descriptors,
        failures=[{"symbol": "x", "reason": "failed"}],
    )

    assert stats["symbols_total"] == 2
    assert stats["symbols_near_empty"] == 1
    assert stats["failures_count"] == 1
