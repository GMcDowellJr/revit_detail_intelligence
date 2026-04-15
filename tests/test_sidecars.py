import json
import os
import sys
import types

from dse.models import ViewFeatureBundle, ViewPresentationSummary, ViewSearchFeatures, ViewStateSignature
from dse.diagnostics.sidecars import (
    INDEX_SIDECAR_SCHEMA,
    INDEX_VIEWS_JSONL_SCHEMA,
    SEARCH_SIDECAR_SCHEMA,
    IndexDiagnosticAccumulator,
    SearchDiagnosticBuilder,
    ViewSymbolRasterPerfAccumulator,
    classify_cache_temperature,
    distribution_stats,
    normalize_stage_timings,
    write_json_sidecar,
)


def _install_revit_stubs():
    if "clr" not in sys.modules:
        clr_mod = types.ModuleType("clr")
        clr_mod.AddReference = lambda *_args, **_kwargs: None
        sys.modules["clr"] = clr_mod

    if "Autodesk.Revit.DB" in sys.modules:
        return

    autodesk_mod = types.ModuleType("Autodesk")
    revit_mod = types.ModuleType("Autodesk.Revit")
    db_mod = types.ModuleType("Autodesk.Revit.DB")

    for name in (
        "BuiltInParameter",
        "CategoryType",
        "CurveElement",
        "DetailCurve",
        "DetailLine",
        "Dimension",
        "ElementId",
        "FamilyInstance",
        "FilledRegion",
        "FilteredElementCollector",
        "TextNote",
        "View",
        "ViewType",
        "GeometryInstance",
        "Options",
    ):
        setattr(db_mod, name, type(name, (), {}))

    sys.modules["Autodesk"] = autodesk_mod
    sys.modules["Autodesk.Revit"] = revit_mod
    sys.modules["Autodesk.Revit.DB"] = db_mod


_install_revit_stubs()

from dse.pipelines import search  # noqa: E402


def _bundle(view_id, *, tokens_stable=None, tokens_context=None, geom=None, symbols=None, name=None):
    return ViewFeatureBundle(
        state_signature=ViewStateSignature(view_id=view_id, view_kind="DRAFTING", state_hash="s{}".format(view_id)),
        search_features=ViewSearchFeatures(
            view_id=view_id,
            view_kind="DRAFTING",
            source_doc_id="doc-{}".format(view_id),
            tokens_stable=tokens_stable or {},
            tokens_context=tokens_context or {},
            geom_hist_knn_endpoints=geom or [],
            symbol_multiset=symbols or {},
        ),
        presentation_summary=ViewPresentationSummary(
            view_id=view_id,
            display_name=name or "View {}".format(view_id),
            debug={"cache_status": "rebuilt"},
        ),
    )


def test_write_json_sidecar_is_atomic_and_valid_json(tmp_path):
    target = tmp_path / "diag" / "search_diagnostic.json"
    payload = {"z": 1, "a": {"b": 2}}

    write_json_sidecar(str(target), payload)

    with open(target, "r", encoding="utf-8") as handle:
        saved = json.load(handle)
    assert saved == payload
    assert not os.path.exists("{}.tmp".format(target))


def test_distribution_stats_non_empty_and_empty():
    stats = distribution_stats([1.0, 2.0, 3.0, 4.0])
    assert set(stats.keys()) == {"count", "min", "max", "mean", "p25", "p50", "p75", "p95"}
    assert stats["count"] == 4
    assert stats["mean"] == 2.5

    empty = distribution_stats([])
    assert empty["count"] == 0
    assert empty["min"] is None
    assert empty["max"] is None
    assert empty["mean"] is None
    assert empty["p25"] is None
    assert empty["p50"] is None
    assert empty["p75"] is None
    assert empty["p95"] is None


def test_normalize_stage_timings_filters_invalid_rows():
    out = normalize_stage_timings(
        {
            " token_collection_ms ": 1.25,
            "bad": "x",
            "neg": -3.0,
            "": 9.0,
            None: 2.0,
        }
    )
    assert out == {"neg": 0.0, "token_collection_ms": 1.25}


def test_index_diagnostic_accumulator_finalize_with_flags_and_stopwords():
    accum = IndexDiagnosticAccumulator()
    accum.accumulate(
        _bundle(
            1,
            tokens_stable={},
            tokens_context={},
            geom=[0.0, 0.0],
            symbols={"door": 3, "tag": 1},
            name="Zero",
        ),
        "rebuilt",
    )
    accum.accumulate_symbol_raster_lookup(
        {"symbol_type_key": "Door|Single", "cache_hit": True, "miss_reason": None, "elapsed_ms": 1.2}
    )
    accum.accumulate_symbol_raster_lookup(
        {
            "symbol_type_key": "Tag|A",
            "cache_hit": False,
            "miss_reason": "file not found",
            "elapsed_ms": 6.5,
        }
    )
    accum.accumulate_view_timing(1, "Zero", 12.0)
    accum.accumulate_view_stage_timings({"symbol_raster_ms": 3.0, "token_collection_ms": 2.0})
    accum.accumulate_view_timing(2, "Sparse", 22.0)
    accum.accumulate_view_stage_timings({"symbol_raster_ms": 4.0, "token_collection_ms": 1.0})
    accum.accumulate(
        _bundle(
            2,
            tokens_stable={"a": 1.0},
            tokens_context={},
            geom=[0.0, 1.0, 0.0],
            symbols={"door": 2},
            name="Sparse",
        ),
        "hit_disk",
    )

    payload = accum.finalize(
        token_idf={"the": 0.1, "rare": 3.0},
        token_df={"the": 2, "rare": 1},
        config={"diagnostics": {"stopword_idf_floor": 0.5}},
    )

    assert payload["schema_version"] == INDEX_SIDECAR_SCHEMA
    assert payload["corpus_id"]
    assert payload["token_health"]["stopword_candidates"] == [["the", 0.1]]
    flagged = {row["view_id"]: row["flags"] for row in payload["flag_summary"]["flags"]}
    assert "zero_tokens" in flagged[1]
    assert "empty_fingerprint" in flagged[1]
    assert payload["symbol_coverage"]["top_10_most_common_symbols"][0] == ["door", 5]
    assert payload["symbol_raster_summary"]["lookups_total"] == 2
    assert payload["symbol_raster_summary"]["miss_reasons"] == {"file not found": 1}
    assert payload["miss_reason_summary"] == {"file not found": 1}
    assert payload["unique_symbol_type_totals"] == {"total": 2, "hit": 1, "miss": 1}
    assert payload["timing"]["slowest_views"][0]["view_id"] == 2
    assert payload["timing"]["mean_view_ms"] == 17.0
    assert payload["timing_summary"]["mean_view_ms"] == 17.0
    assert payload["stage_timing_summary"]["stages"]["symbol_raster_ms"]["total_ms"] == 7.0
    assert payload["stage_timing_summary"]["stages"]["token_collection_ms"]["timing_ms"]["p50"] == 1.5
    assert payload["stage_timing_summary"]["internal_stage_total_ms"] == 10.0


def test_search_diagnostic_builder_builds_schema_and_tiers():
    query = _bundle(10, tokens_stable={"t": 1.0}, geom=[1.0, 0.0])
    query.presentation_summary.debug["cache_status"] = "hit_memory"

    builder = SearchDiagnosticBuilder(run_id="run-123")
    builder.timings["state_context_build"] = 10.0

    all_scored = [
        {"score_total": 0.9, "confidence_tier": "HIGH"},
        {"score_total": 0.7, "confidence_tier": "MEDIUM"},
        {"score_total": 0.2, "confidence_tier": "LOW"},
    ]
    top_results = [
        {
            "candidate_view_id": 99,
            "score_total": 0.9,
            "score_tokens": 0.8,
            "score_geom": 0.9,
            "score_fine": 0.7,
            "confidence_tier": "HIGH",
            "presentation_summary": {"display_name": "Candidate 99"},
            "explanation": {"top_shared_tokens": ["a"], "top_shared_geom_bins": [1]},
        }
    ]

    payload = builder.build(
        query_bundle=query,
        corpus_size=3,
        corpus_errors=0,
        cache_statuses={"hit_disk": 3},
        config_snapshot={"weights": {}},
        token_idf={"a": 1.0},
        default_idf=0.5,
        all_scored=all_scored,
        top_results=top_results,
        stage2_available=False,
    )

    assert payload["schema_version"] == SEARCH_SIDECAR_SCHEMA
    assert payload["score_distribution"]["tier_counts"] == {"HIGH": 1, "MEDIUM": 1, "LOW": 1}


def test_extract_bundle_with_cache_returns_tuple(monkeypatch):
    class FakeViewId:
        IntegerValue = 42

    class FakeView:
        Id = FakeViewId()

    bundle = _bundle(42)

    monkeypatch.setattr(
        search,
        "_build_state_context",
        lambda _view, symbol_raster_lookup_callback=None: {"state_hash": "abc"},
    )
    monkeypatch.setattr(search, "resolve_view_cache_root", lambda _cfg: "/tmp/cache")
    monkeypatch.setattr(
        search,
        "get_cached_bundle_with_diagnostics",
        lambda **_kwargs: (bundle, "hit_memory"),
    )

    result = search._extract_bundle_with_cache(FakeView())
    assert isinstance(result, tuple)
    returned_bundle, status = result
    assert returned_bundle.search_features.view_id == 42
    assert status == "hit_memory"


def _jsonl_bundle(
    view_id,
    *,
    extraction_ms=1.5,
    pt_count=7,
    symbol_instances=3,
    curve_count=9,
    name=None,
):
    bundle = _bundle(view_id, name=name or "V{}".format(view_id))
    bundle.presentation_summary.debug = {"extraction_ms": extraction_ms}
    bundle.search_features.debug = {"pt_count": pt_count}
    bundle.presentation_summary.feature_summary = {
        "symbol_instances": symbol_instances,
        "curve_count": curve_count,
    }
    return bundle


def test_flush_view_record_creates_jsonl(tmp_path):
    accum = IndexDiagnosticAccumulator()
    path = tmp_path / "diag" / "index_views.jsonl"

    accum.flush_view_record(str(path), _jsonl_bundle(1, name="One"), "rebuilt")
    accum.flush_view_record(
        str(path),
        _jsonl_bundle(2, name="Two"),
        "hit_disk",
        view_perf={
            "stage_timings_ms": {"symbol_raster_ms": 1.0, "token_collection_ms": 2.0},
            "internal_stage_total_ms": 3.0,
            "internal_stage_coverage_ratio": 0.5,
            "extraction_minus_internal_stage_ms": 3.0,
        },
    )

    with open(path, "r", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle.read().splitlines()]

    assert len(rows) == 2
    assert rows[0]["schema_version"] == INDEX_VIEWS_JSONL_SCHEMA
    assert rows[0]["view_id"] == 1
    assert rows[0]["cache_status"] == "rebuilt"
    assert rows[0]["symbol_lookups_total"] == 0
    assert rows[0]["cache_temperature"] == "none"
    assert rows[0]["ts_utc"].endswith("Z")
    assert rows[1]["view_id"] == 2
    assert rows[1]["cache_status"] == "hit_disk"
    assert rows[1]["ts_utc"].endswith("Z")
    assert rows[1]["stage_timings_ms"] == {"symbol_raster_ms": 1.0, "token_collection_ms": 2.0}
    assert rows[1]["internal_stage_total_ms"] == 3.0
    assert rows[1]["internal_stage_coverage_ratio"] == 0.5
    assert rows[1]["extraction_minus_internal_stage_ms"] == 3.0


def test_flush_view_record_appends_across_calls(tmp_path):
    accum = IndexDiagnosticAccumulator()
    path = tmp_path / "diag" / "index_views.jsonl"

    accum.flush_view_record(str(path), _jsonl_bundle(10), "rebuilt")
    accum.flush_view_record(str(path), _jsonl_bundle(11), "hit_memory")
    accum.flush_view_record(str(path), _jsonl_bundle(12), "hit_disk")

    with open(path, "r", encoding="utf-8") as handle:
        assert len(handle.read().splitlines()) == 3


def test_flush_view_record_survives_missing_optional_fields(tmp_path):
    accum = IndexDiagnosticAccumulator()
    path = tmp_path / "diag" / "index_views.jsonl"

    bundle = _bundle(99, name="No Optional")
    bundle.presentation_summary.debug = {}
    bundle.search_features.debug = {}
    bundle.presentation_summary.feature_summary = {}

    accum.flush_view_record(str(path), bundle, "rebuilt")

    with open(path, "r", encoding="utf-8") as handle:
        row = json.loads(handle.read().splitlines()[0])

    assert row["view_id"] == 99
    assert row["schema_version"] == INDEX_VIEWS_JSONL_SCHEMA
    assert row["cache_status"] == "rebuilt"
    assert row["extraction_ms"] is None
    assert row["pt_count"] is None
    assert row["symbol_instances"] is None
    assert row["curve_count"] is None
    assert row["symbol_lookups_total"] == 0
    assert row["symbol_cache_miss_reasons"] == {}
    assert row["cache_temperature"] == "none"


def test_classify_cache_temperature_deterministic():
    assert classify_cache_temperature(0, 0, 0) == "none"
    assert classify_cache_temperature(1, 0, 1) == "cold"
    assert classify_cache_temperature(2, 2, 0) == "warm"
    assert classify_cache_temperature(2, 1, 1) == "mixed"


def test_view_symbol_perf_cohorts_and_zero_symbol_views():
    view1 = ViewSymbolRasterPerfAccumulator()
    view1.accumulate({"symbol_type_key": "A", "cache_hit": False, "miss_reason": "file not found", "elapsed_ms": 4.0})
    view1_summary = view1.finalize()
    assert view1_summary["cache_temperature"] == "cold"
    assert view1_summary["new_symbol_types_built_in_view"] == 1
    assert view1_summary["reused_symbol_types_in_view"] == 0

    view2 = ViewSymbolRasterPerfAccumulator()
    view2.accumulate({"symbol_type_key": "A", "cache_hit": True, "elapsed_ms": 1.0})
    view2.accumulate({"symbol_type_key": "B", "cache_hit": False, "miss_reason": "parse error", "elapsed_ms": 5.0})
    view2_summary = view2.finalize()
    assert view2_summary["cache_temperature"] == "mixed"
    assert view2_summary["symbol_lookups_total"] == 2
    assert view2_summary["symbol_cache_hits"] == 1
    assert view2_summary["symbol_cache_misses"] == 1
    assert view2_summary["new_symbol_types_built_in_view"] == 1
    assert view2_summary["reused_symbol_types_in_view"] == 1

    view3 = ViewSymbolRasterPerfAccumulator()
    view3.accumulate({"symbol_type_key": "A", "cache_hit": True, "elapsed_ms": 2.0})
    view3.accumulate({"symbol_type_key": "A", "cache_hit": False, "miss_reason": "file not found", "elapsed_ms": 3.0})
    view3_summary = view3.finalize()
    assert view3_summary["cache_temperature"] == "mixed"
    assert view3_summary["new_symbol_types_built_in_view"] == 1
    assert view3_summary["reused_symbol_types_in_view"] == 0
    assert view3_summary["unique_symbol_types_in_view"] == 1

    view4 = ViewSymbolRasterPerfAccumulator()
    view4_summary = view4.finalize()
    assert view4_summary["cache_temperature"] == "none"
    assert view4_summary["symbol_lookups_total"] == 0


def test_repeated_type_misses_stay_cold_without_run_seen_bias():
    first = ViewSymbolRasterPerfAccumulator()
    first.accumulate(
        {"symbol_type_key": "Door|A", "cache_hit": False, "miss_reason": "file not found", "elapsed_ms": 2.0}
    )
    second = ViewSymbolRasterPerfAccumulator()
    second.accumulate(
        {"symbol_type_key": "Door|A", "cache_hit": False, "miss_reason": "file not found", "elapsed_ms": 2.0}
    )

    assert first.finalize()["cache_temperature"] == "cold"
    assert second.finalize()["cache_temperature"] == "cold"


def test_cache_temperature_is_unchanged_by_cache_layer_field():
    view = ViewSymbolRasterPerfAccumulator(run_seen_symbol_types=set())
    view.accumulate({"symbol_type_key": "Door|A", "cache_hit": True, "cache_layer": "disk", "elapsed_ms": 1.0})
    view.accumulate({"symbol_type_key": "Door|A", "cache_hit": True, "cache_layer": "memory", "elapsed_ms": 0.1})
    summary = view.finalize()
    assert summary["cache_temperature"] == "warm"
    assert summary["new_symbol_types_built_in_view"] == 0
    assert summary["reused_symbol_types_in_view"] == 0


def test_finalize_cache_temperature_summary():
    accum = IndexDiagnosticAccumulator()

    for view_id, cohort, ms in (
        (1, "cold", 10.0),
        (2, "mixed", 20.0),
        (3, "warm", 30.0),
        (4, "none", 40.0),
    ):
        accum.accumulate(_bundle(view_id, tokens_stable={"x": 1.0}, geom=[1.0], symbols={}), "rebuilt")
        accum.accumulate_view_timing(view_id, "V{}".format(view_id), ms)
        accum.accumulate_cache_temperature(cohort, ms)

    payload = accum.finalize(token_idf={}, token_df={}, config={"diagnostics": {"stopword_idf_floor": 0.5}})
    assert payload["cache_temperature_summary"]["cold"]["view_count"] == 1
    assert payload["cache_temperature_summary"]["mixed"]["timing_ms"]["mean"] == 20.0
    assert payload["cache_temperature_summary"]["warm"]["timing_ms"]["p50"] == 30.0
    assert payload["cache_temperature_summary"]["none"]["timing_ms"]["max"] == 40.0
