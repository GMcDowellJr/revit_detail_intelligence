import os

from dse.cache.view_feature_cache import (
    ViewFeatureCache,
    ViewFeatureCacheEntry,
    read_cache_record,
    get_cached_bundle_with_diagnostics,
    put_bundle_in_caches,
    serialize_cache_entry,
)
from dse.outputs.contact_folder import create_contact_folder
from dse.outputs.contact_sheet import _save_png
from dse.pipelines.many_to_many import build_many_to_many_edges, write_many_to_many_outputs
from dse.models import ViewFeatureBundle, ViewPresentationSummary, ViewSearchFeatures, ViewStateSignature




def _write_tiny_png(path):
    _save_png(path, 2, 2, bytes((255, 0, 0) * 4))


def _bundle(view_id=10, state_hash="abc", source_doc_id="doc-a", source_doc_name="Doc A"):
    return ViewFeatureBundle(
        state_signature=ViewStateSignature(
            view_id=view_id,
            view_kind="DRAFTING",
            source_doc_id=source_doc_id,
            source_doc_name=source_doc_name,
            state_hash=state_hash,
        ),
        search_features=ViewSearchFeatures(
            view_id=view_id,
            view_kind="DRAFTING",
            source_doc_id=source_doc_id,
            source_doc_name=source_doc_name,
            tokens_stable={"type_sig:A|B": 1.5},
            tokens_context={"line_style:Thin": 1.0},
            geom_hist_knn_endpoints=[0.2, 0.8],
            fine_metrics={"pt_count": 4.0},
            layout_graph_features={"node_count": 3.0, "edge_density_est": 0.2, "component_count_est": 2.0},
            symbol_multiset={"A|B": 2},
        ),
        presentation_summary=ViewPresentationSummary(view_id=view_id, display_name="View A"),
    )


def test_disk_cache_roundtrip_and_invalidation(tmp_path):
    cache_root = str(tmp_path / "cache")
    mem = ViewFeatureCache()
    bundle = _bundle(view_id=77, state_hash="s1")

    put_bundle_in_caches(
        in_memory_cache=mem,
        cache_root=cache_root,
        view_id=77,
        state_hash="s1",
        pipeline_version="p1",
        schema_version="s.v1",
        payload=bundle,
    )

    mem.entries = {}
    payload, status = get_cached_bundle_with_diagnostics(
        in_memory_cache=mem,
        cache_root=cache_root,
        view_id=77,
        state_hash="s1",
        pipeline_version="p1",
        schema_version="s.v1",
    )
    assert payload is not None
    assert status == "hit_disk"

    payload2, status2 = get_cached_bundle_with_diagnostics(
        in_memory_cache=mem,
        cache_root=cache_root,
        view_id=77,
        state_hash="DIFF",
        pipeline_version="p1",
        schema_version="s.v1",
    )
    assert payload2 is None
    assert status2 == "invalidated"


def test_read_cache_record_finds_doc_scoped_file(tmp_path):
    cache_root = str(tmp_path / "cache")
    view_dir = tmp_path / "cache" / "view_features"
    view_dir.mkdir(parents=True, exist_ok=True)

    entry = ViewFeatureCacheEntry(
        view_id=42,
        state_hash="s42",
        schema_version="s.v1",
        pipeline_version="p1",
        payload=_bundle(view_id=42, state_hash="s42"),
    )
    path = view_dir / "view_42__doc_deadbeefcafe.json"
    path.write_text(serialize_cache_entry(entry), encoding="utf-8")

    loaded = read_cache_record(cache_root, 42)
    assert loaded is not None
    assert loaded.state_hash == "s42"


def test_cache_roundtrip_via_doc_scoped_file(tmp_path):
    cache_root = str(tmp_path / "cache")
    mem = ViewFeatureCache()
    bundle = _bundle(view_id=88, state_hash="s88", source_doc_id="doc-88", source_doc_name="Doc 88")

    put_bundle_in_caches(
        in_memory_cache=mem,
        cache_root=cache_root,
        view_id=88,
        state_hash="s88",
        pipeline_version="p1",
        schema_version="s.v1",
        payload=bundle,
    )

    view_dir = tmp_path / "cache" / "view_features"
    doc_scoped = sorted([name for name in os.listdir(str(view_dir)) if name.startswith("view_88__doc_")])
    assert len(doc_scoped) == 1
    assert not (view_dir / "view_88.json").exists()

    mem.entries = {}
    payload, status = get_cached_bundle_with_diagnostics(
        in_memory_cache=mem,
        cache_root=cache_root,
        view_id=88,
        state_hash="s88",
        pipeline_version="p1",
        schema_version="s.v1",
    )
    assert payload is not None
    assert status == "hit_disk"


def test_legacy_path_fallback_still_readable(tmp_path):
    cache_root = str(tmp_path / "cache")
    view_dir = tmp_path / "cache" / "view_features"
    view_dir.mkdir(parents=True, exist_ok=True)

    entry = ViewFeatureCacheEntry(
        view_id=53,
        state_hash="s53",
        schema_version="s.v1",
        pipeline_version="p1",
        payload=_bundle(view_id=53, state_hash="s53"),
    )
    legacy_path = view_dir / "view_53.json"
    legacy_path.write_text(serialize_cache_entry(entry), encoding="utf-8")

    loaded = read_cache_record(cache_root, 53)
    assert loaded is not None
    assert loaded.view_id == 53


def test_many_to_many_edges_and_output_files(tmp_path):
    rows = [
        {
            "view_id": 1,
            "display_name": "A",
            "source_doc_id": "d1",
            "source_doc_name": "doc",
            "tokens": {"x": 1.0},
            "geom_fingerprint": [1.0, 0.0],
            "fine_metrics": {"pt_count": 1.0},
            "layout_graph_features": {"node_count": 1.0, "edge_density_est": 0.0, "component_count_est": 1.0},
            "symbol_multiset": {"S": 1},
        },
        {
            "view_id": 2,
            "display_name": "B",
            "source_doc_id": "d1",
            "source_doc_name": "doc",
            "tokens": {"x": 1.0},
            "geom_fingerprint": [1.0, 0.0],
            "fine_metrics": {"pt_count": 1.0},
            "layout_graph_features": {"node_count": 1.0, "edge_density_est": 0.0, "component_count_est": 1.0},
            "symbol_multiset": {"S": 1},
        },
    ]
    edges = build_many_to_many_edges(rows, top_k=1, skip_self=True)
    assert len(edges) == 2
    assert edges[0]["rank"] == 1

    cfg = {"many_to_many_output_dir": str(tmp_path / "m2m")}
    out = write_many_to_many_outputs(edges, cfg, run_id="t")
    assert os.path.exists(out["json_path"])
    assert os.path.exists(out["csv_path"])


def test_contact_folder_and_runs_index_emission(tmp_path):
    cfg = {"contacts_dir": str(tmp_path / "contacts")}
    _write_tiny_png(str(tmp_path / "p_seed.png"))
    _write_tiny_png(str(tmp_path / "p1.png"))
    _write_tiny_png(str(tmp_path / "p2.png"))

    out = create_contact_folder(
        {"view_id": 100, "display_name": "Seed", "preview_path": str(tmp_path / "p_seed.png")},
        [
            {
                "candidate_view_id": 101,
                "candidate_display_name": "Cand 1",
                "rank": 1,
                "total_score": 0.91,
                "confidence_level": "high",
                "preview_path": str(tmp_path / "p1.png"),
            },
            {
                "candidate_view_id": 102,
                "candidate_display_name": "Cand 2",
                "rank": 2,
                "total_score": 0.84,
                "confidence_level": "med",
                "preview_path": str(tmp_path / "p2.png"),
            },
        ],
        cfg,
        run_id="run_1",
    )

    assert os.path.exists(out["contact_folder"])
    assert os.path.exists(out["results_path"])
    assert os.path.exists(out["runs_index"])

    with open(out["runs_index"], "r", encoding="utf-8") as handle:
        rows = handle.read().strip().splitlines()
    assert len(rows) == 3


def test_contact_folder_uses_preview_cache_fallback(tmp_path):
    cache_preview_dir = tmp_path / "cache" / "previews"
    cache_preview_dir.mkdir(parents=True, exist_ok=True)
    _write_tiny_png(str(cache_preview_dir / "view_200.png"))
    _write_tiny_png(str(cache_preview_dir / "view_201.png"))

    cfg = {"contacts_dir": str(tmp_path / "contacts"), "preview_root": str(cache_preview_dir)}
    out = create_contact_folder(
        {"view_id": 200, "display_name": "Seed"},
        [
            {
                "candidate_view_id": 201,
                "candidate_display_name": "Cand",
                "rank": 1,
                "total_score": 0.9,
                "confidence_level": "high",
            }
        ],
        cfg,
        run_id="run_2",
    )

    files = sorted([f for f in os.listdir(out["contact_folder"]) if f.lower().endswith(".png")])
    assert len(files) == 2
    with open(out["results_path"], "r", encoding="utf-8") as handle:
        payload = handle.read()
    assert "seed_png_emitted" in payload
    assert "contact_png_emitted" in payload


def test_contact_folder_emits_placeholders_when_preview_missing(tmp_path):
    cfg = {"contacts_dir": str(tmp_path / "contacts"), "preview_root": str(tmp_path / "missing_previews")}
    out = create_contact_folder(
        {"view_id": 300, "display_name": "Seed Missing"},
        [
            {
                "candidate_view_id": 301,
                "candidate_display_name": "Cand Missing",
                "rank": 1,
                "total_score": 0.5,
                "confidence_level": "low",
            }
        ],
        cfg,
        run_id="run_missing",
    )

    pngs = sorted([f for f in os.listdir(out["contact_folder"]) if f.lower().endswith(".png")])
    assert len(pngs) == 2

    with open(out["results_path"], "r", encoding="utf-8") as handle:
        payload = handle.read()
    assert '"seed_png_placeholder": true' in payload
    assert '"contact_png_placeholder": true' in payload
