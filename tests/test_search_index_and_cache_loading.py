import os
import sys
import types

from dse.cache.view_feature_cache import ViewFeatureCacheEntry, serialize_cache_entry
from dse.models import ViewFeatureBundle, ViewPresentationSummary, ViewSearchFeatures, ViewStateSignature
from dse.config import CONFIG


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


def _bundle(view_id, cache_status="rebuilt", source_doc_id="doc-a", state_hash=None):
    shash = state_hash or "s{}".format(view_id)
    return ViewFeatureBundle(
        state_signature=ViewStateSignature(
            view_id=view_id,
            view_kind="DRAFTING",
            source_doc_id=source_doc_id,
            state_hash=shash,
        ),
        search_features=ViewSearchFeatures(
            view_id=view_id,
            view_kind="DRAFTING",
            source_doc_id=source_doc_id,
            tokens_stable={"type_sig:A|B": 1.0},
            tokens_context={"line_style:Thin": 1.0},
            geom_hist_knn_endpoints=[1.0, 0.0],
            fine_metrics={"pt_count": 1.0},
        ),
        presentation_summary=ViewPresentationSummary(
            view_id=view_id,
            display_name="V{}".format(view_id),
            debug={"cache_status": cache_status},
        ),
    )


def test_index_views_empty_input():
    summary = search.index_views([])
    assert summary == {"indexed": 0, "skipped": 0, "cache_statuses": {}}


def test_index_views_all_invalid(monkeypatch):
    monkeypatch.setattr(search, "is_view", lambda _: False)
    summary = search.index_views([object(), object()])
    assert summary["indexed"] == 0
    assert summary["skipped"] == 2
    assert summary["cache_statuses"] == {}


def test_index_views_mixed_cache_hit_and_miss(monkeypatch):
    class FakeId(object):
        def __init__(self, value):
            self.IntegerValue = value

    class FakeView(object):
        def __init__(self, value):
            self.Id = FakeId(value)

    views = [FakeView(1), FakeView(2), object()]
    monkeypatch.setattr(search, "is_view", lambda value: hasattr(value, "Id"))

    def fake_extract(view):
        status = "hit_disk" if view.Id.IntegerValue == 1 else "rebuilt"
        return _bundle(view.Id.IntegerValue, cache_status=status)

    monkeypatch.setattr(search, "_extract_bundle_with_cache", fake_extract)

    summary = search.index_views(views)
    assert summary["indexed"] == 2
    assert summary["skipped"] == 1
    assert summary["cache_statuses"] == {1: "hit_disk", 2: "rebuilt"}


def test_index_views_writes_doc_scoped_cache_files(monkeypatch, tmp_path):
    class FakeId(object):
        def __init__(self, value):
            self.IntegerValue = value

    class FakeView(object):
        def __init__(self, value):
            self.Id = FakeId(value)

    monkeypatch.setattr(search, "is_view", lambda value: hasattr(value, "Id"))
    monkeypatch.setattr(search, "resolve_view_cache_root", lambda _cfg: str(tmp_path / "cache"))
    monkeypatch.setattr(
        search,
        "_extract_bundle_with_cache",
        lambda view: _bundle(view.Id.IntegerValue, source_doc_id="doc-x"),
    )

    summary = search.index_views([FakeView(9)])
    assert summary["indexed"] == 1
    out_dir = tmp_path / "cache" / "view_features"
    files = sorted([name for name in os.listdir(str(out_dir)) if name.startswith("view_9__doc_")])
    assert len(files) == 1


def test_load_all_cached_bundles_empty_dir(tmp_path):
    cache_root = str(tmp_path / "cache")
    os.makedirs(os.path.join(cache_root, "view_features"), exist_ok=True)
    assert search._load_all_cached_bundles(cache_root) == []


def test_load_all_cached_bundles_skips_corrupt_and_returns_valid(tmp_path):
    cache_root = str(tmp_path / "cache")
    view_dir = os.path.join(cache_root, "view_features")
    os.makedirs(view_dir, exist_ok=True)

    for view_id in (11, 12):
        entry = ViewFeatureCacheEntry(
            view_id=view_id,
            state_hash="s{}".format(view_id),
            schema_version=search.SEARCH_SCHEMA_VERSION,
            pipeline_version=CONFIG["pipeline_version"],
            payload=_bundle(view_id, source_doc_id="doc-{}".format(view_id)),
        )
        with open(os.path.join(view_dir, "view_{}.json".format(view_id)), "w", encoding="utf-8") as handle:
            handle.write(serialize_cache_entry(entry))

    stale = ViewFeatureCacheEntry(
        view_id=13,
        state_hash="s13",
        schema_version="view_search_features.v0.1",
        pipeline_version=CONFIG["pipeline_version"],
        payload=_bundle(13, source_doc_id="doc-stale-schema"),
    )
    with open(os.path.join(view_dir, "view_13.json"), "w", encoding="utf-8") as handle:
        handle.write(serialize_cache_entry(stale))

    stale_pipeline = ViewFeatureCacheEntry(
        view_id=14,
        state_hash="s14",
        schema_version=search.SEARCH_SCHEMA_VERSION,
        pipeline_version="old-pipeline-version",
        payload=_bundle(14, source_doc_id="doc-stale-pipeline"),
    )
    with open(os.path.join(view_dir, "view_14.json"), "w", encoding="utf-8") as handle:
        handle.write(serialize_cache_entry(stale_pipeline))

    with open(os.path.join(view_dir, "view_broken.json"), "w", encoding="utf-8") as handle:
        handle.write("{broken")

    loaded = search._load_all_cached_bundles(cache_root)
    assert sorted(bundle.search_features.view_id for bundle in loaded) == [11, 12]


def test_load_all_cached_bundles_includes_doc_scoped_view_id_collisions(tmp_path):
    cache_root = str(tmp_path / "cache")
    view_dir = os.path.join(cache_root, "view_features")
    os.makedirs(view_dir, exist_ok=True)

    b1 = _bundle(77, source_doc_id="doc-one", state_hash="s-1")
    b2 = _bundle(77, source_doc_id="doc-two", state_hash="s-2")

    for idx, bundle in enumerate((b1, b2), start=1):
        entry = ViewFeatureCacheEntry(
            view_id=77,
            state_hash=bundle.state_signature.state_hash,
            schema_version=search.SEARCH_SCHEMA_VERSION,
            pipeline_version=CONFIG["pipeline_version"],
            payload=bundle,
        )
        path = os.path.join(view_dir, "view_77__doc_{}.json".format(idx))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(serialize_cache_entry(entry))

    # Duplicate payload in legacy non-scoped file should be de-duped by source+view+state key.
    duplicate = ViewFeatureCacheEntry(
        view_id=77,
        state_hash=b1.state_signature.state_hash,
        schema_version=search.SEARCH_SCHEMA_VERSION,
        pipeline_version=CONFIG["pipeline_version"],
        payload=b1,
    )
    with open(os.path.join(view_dir, "view_77.json"), "w", encoding="utf-8") as handle:
        handle.write(serialize_cache_entry(duplicate))

    loaded = search._load_all_cached_bundles(cache_root)
    assert len(loaded) == 2
    assert sorted((b.search_features.source_doc_id, b.state_signature.state_hash) for b in loaded) == [
        ("doc-one", "s-1"),
        ("doc-two", "s-2"),
    ]
