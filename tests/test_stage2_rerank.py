from dse.cache.symbol_cache import (
    DescriptorVariant,
    SymbolCacheModel,
    SymbolDescriptor,
    SymbolKey,
    stable_cache_key,
)
from dse.ranking.stage2_rerank import Stage1Result, select_rerank_pool, stage2_rerank


def _symbol_descriptor(key, vec):
    return SymbolDescriptor(
        schema="symbol_descriptor.v1",
        key=key,
        build_method="family_doc",
        build_time_utc="now",
        validity_token="token",
        source_fingerprint={},
        variants={
            "uniform": DescriptorVariant(
                variant_name="uniform",
                descriptor_kind="zernike_mag",
                descriptor_vector=vec,
            )
        },
    )


def test_select_rerank_pool_supports_delta_and_top_k():
    rows = [
        Stage1Result(1, 0.9, 0, 0, 0, "HIGH"),
        Stage1Result(2, 0.85, 0, 0, 0, "HIGH"),
        Stage1Result(3, 0.6, 0, 0, 0, "MEDIUM"),
    ]
    assert len(select_rerank_pool(rows, {"band_mode": "top_k", "pool_top_k": 2})) == 2
    delta_pool = select_rerank_pool(
        rows,
        {"band_mode": "score_delta", "score_delta": 0.1},
    )
    assert [r.candidate_view_id for r in delta_pool] == [1, 2]


def test_stage2_rerank_respects_stage1_threshold_and_adds_support_flags():
    query_key = SymbolKey("Fam", "T", "h1")
    candidate_key = SymbolKey("Fam", "T", "h1")

    symbol_cache = SymbolCacheModel(
        schema="symbol_cache.v1", corpus_id="c", pipeline_version="v"
    )
    symbol_cache.descriptors[stable_cache_key(query_key)] = _symbol_descriptor(
        query_key, [1.0, 0.0]
    )

    stage1 = [
        Stage1Result(101, 0.2, 0, 0, 0, "LOW"),
        Stage1Result(102, 0.8, 0, 0, 0, "HIGH"),
    ]

    views = {
        100: {"id": 100, "symbols": {query_key: 1}},
        101: {"id": 101, "symbols": {candidate_key: 1}},
        102: {"id": 102, "symbols": {candidate_key: 1}},
    }

    config = {
        "stage2_rerank": {
            "pool_top_k": 5,
            "band_mode": "top_k",
            "require_min_stage1_score": 0.25,
            "min_symbol_coverage": 0.7,
            "min_view_raster_available": True,
        },
        "confidence_policy": {"raster_support_threshold": 0.9},
    }

    view_raster_cache = {100: "query_sig", 102: "cand_sig"}

    out = stage2_rerank(
        stage1_results=stage1,
        query_view_id=100,
        query_symbols=views[100]["symbols"],
        symbol_cache=symbol_cache,
        view_raster_cache=view_raster_cache,
        config=config,
        resolve_view=lambda vid: views[vid],
        extract_view_symbol_multiset=lambda view: view["symbols"],
        view_raster_similarity=lambda a, b: 0.95,
        build_view_raster_signature=lambda view: "generated_sig",
    )

    by_id = {row.candidate_view_id: row for row in out}
    assert by_id[101].notes == ["stage1_below_min; no rerank"]
    assert by_id[102].confidence_raster_support == "STRONG"


def test_stage2_rerank_sorts_pool_and_keeps_non_pooled_candidates():
    query_key = SymbolKey("Fam", "T", "h1")

    symbol_cache = SymbolCacheModel(
        schema="symbol_cache.v1", corpus_id="c", pipeline_version="v"
    )
    symbol_cache.descriptors[stable_cache_key(query_key)] = _symbol_descriptor(
        query_key, [1.0, 0.0]
    )

    stage1 = [
        Stage1Result(201, 0.90, 0, 0, 0, "HIGH"),
        Stage1Result(202, 0.80, 0, 0, 0, "HIGH"),
        Stage1Result(203, 0.70, 0, 0, 0, "MEDIUM"),
    ]

    views = {
        200: {"id": 200, "symbols": {query_key: 1}},
        201: {"id": 201, "symbols": {query_key: 1}},
        202: {"id": 202, "symbols": {query_key: 1}},
        203: {"id": 203, "symbols": {query_key: 1}},
    }

    config = {
        "stage2_rerank": {
            "pool_top_k": 2,
            "band_mode": "top_k",
            "require_min_stage1_score": 0.25,
            "min_symbol_coverage": 0.7,
            "min_view_raster_available": True,
        },
        "confidence_policy": {"raster_support_threshold": 0.9},
    }

    view_raster_cache = {200: "query_sig"}

    def _raster_similarity(_a, candidate_sig):
        if candidate_sig == "sig_201":
            return 0.10
        return 0.99

    out = stage2_rerank(
        stage1_results=stage1,
        query_view_id=200,
        query_symbols=views[200]["symbols"],
        symbol_cache=symbol_cache,
        view_raster_cache=view_raster_cache,
        config=config,
        resolve_view=lambda vid: views[vid],
        extract_view_symbol_multiset=lambda view: view["symbols"],
        view_raster_similarity=_raster_similarity,
        build_view_raster_signature=lambda view: "sig_{}".format(view["id"]),
    )

    assert [row.candidate_view_id for row in out] == [202, 201, 203]
    assert out[0].score_combined > out[1].score_combined
    assert out[2].score_combined == stage1[2].score_total
    assert out[2].score_raster is None
