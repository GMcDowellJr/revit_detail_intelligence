import os

from dse.cache.view_feature_cache import (
    ViewFeatureCache,
    ViewFeatureCacheEntry,
    get_cached_bundle_with_diagnostics,
    put_bundle_in_caches,
)
from dse.outputs.contact_sheet import _save_png, write_contact_sheet_png
from dse.pipelines.many_to_many import build_many_to_many_edges, write_many_to_many_outputs
from dse.models import ViewFeatureBundle, ViewPresentationSummary, ViewSearchFeatures, ViewStateSignature




def _write_tiny_png(path):
    _save_png(path, 2, 2, bytes((255, 0, 0) * 4))


def _bundle(view_id=10, state_hash="abc"):
    return ViewFeatureBundle(
        state_signature=ViewStateSignature(view_id=view_id, view_kind="DRAFTING", state_hash=state_hash),
        search_features=ViewSearchFeatures(
            view_id=view_id,
            view_kind="DRAFTING",
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


def test_contact_sheet_png_emission(tmp_path):
    cfg = {"contact_sheets_dir": str(tmp_path / "sheets")}
    _write_tiny_png(str(tmp_path / "p_seed.png"))
    _write_tiny_png(str(tmp_path / "p1.png"))
    _write_tiny_png(str(tmp_path / "p2.png"))

    path = write_contact_sheet_png(
        {"view_id": 100, "display_name": "Seed", "source_doc_name": "doc", "preview_path": str(tmp_path / "p_seed.png")},
        [
            {"view_id": 101, "display_name": "Cand 1", "score_total": 0.91, "preview_path": str(tmp_path / "p1.png")},
            {"view_id": 102, "display_name": "Cand 2", "score_total": 0.84, "preview_path": str(tmp_path / "p2.png")},
        ],
        cfg,
        run_id="sheet",
    )
    assert os.path.exists(path)
    with open(path, "rb") as handle:
        assert handle.read(8) == b"\x89PNG\r\n\x1a\n"
