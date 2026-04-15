import importlib
import sys
import types

from dse.diagnostics.sidecars import IndexDiagnosticAccumulator

sys.modules.setdefault("clr", types.SimpleNamespace(AddReference=lambda *_args, **_kwargs: None))
if "Autodesk.Revit.DB" not in sys.modules:
    db_mod = types.ModuleType("Autodesk.Revit.DB")
    for name in [
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
    ]:
        setattr(db_mod, name, type(name, (), {}))
    db_mod.__getattr__ = lambda name: type(name, (), {})
    autodesk_mod = types.ModuleType("Autodesk")
    revit_mod = types.ModuleType("Autodesk.Revit")
    autodesk_mod.Revit = revit_mod
    revit_mod.DB = db_mod
    sys.modules["Autodesk"] = autodesk_mod
    sys.modules["Autodesk.Revit"] = revit_mod
    sys.modules["Autodesk.Revit.DB"] = db_mod


def _load_symbol_raster():
    if "dse.revit_api.symbol_raster" in sys.modules:
        return sys.modules["dse.revit_api.symbol_raster"]
    return importlib.import_module("dse.revit_api.symbol_raster")


def test_collect_raster_points_accepts_diagnostic_callback(monkeypatch):
    symbol_raster = _load_symbol_raster()
    calls = []

    class _View(object):
        Document = object()

    class _Elem(object):
        pass

    monkeypatch.setattr(symbol_raster, "get_view_elements", lambda _view: [_Elem()])
    monkeypatch.setattr(symbol_raster, "is_family_instance", lambda _elem: True)
    monkeypatch.setattr(
        symbol_raster,
        "_build_symbol_instance_context",
        lambda *_args, **_kwargs: {
            "elem_id": 7,
            "cache_key": "k",
            "placement_point": (0.0, 0.0),
            "axis_x": (1.0, 0.0),
            "is_mirrored": False,
            "length_scale_x": 1.0,
        },
    )
    monkeypatch.setattr(symbol_raster, "_collect_canonical_points_for_context", lambda **_kwargs: [[0.0, 1.0]])

    out = symbol_raster.collect_raster_points_for_view(_View(), diagnostic_callback=lambda row: calls.append(row))

    assert out == {7: [[0.0, 1.0]]}
    assert calls == []


def test_collect_raster_points_uses_caller_supplied_elements(monkeypatch):
    symbol_raster = _load_symbol_raster()

    class _View(object):
        Document = object()

    class _Elem(object):
        pass

    source_elements = [_Elem()]

    def _boom(_view):
        raise AssertionError("get_view_elements should not run when elements are supplied")

    monkeypatch.setattr(symbol_raster, "get_view_elements", _boom)
    monkeypatch.setattr(symbol_raster, "is_family_instance", lambda _elem: True)
    monkeypatch.setattr(
        symbol_raster,
        "_build_symbol_instance_context",
        lambda *_args, **_kwargs: {
            "elem_id": 9,
            "cache_key": "k",
            "placement_point": (0.0, 0.0),
            "axis_x": (1.0, 0.0),
            "is_mirrored": False,
            "length_scale_x": 1.0,
        },
    )
    monkeypatch.setattr(symbol_raster, "_collect_canonical_points_for_context", lambda **_kwargs: [[2.0, 3.0]])

    out = symbol_raster.collect_raster_points_for_view(_View(), elements=source_elements)

    assert out == {9: [[2.0, 3.0]]}


def test_collect_points_emits_cache_lookup_summary(monkeypatch):
    symbol_raster = _load_symbol_raster()
    events = []

    class _Vec(object):
        def __init__(self, x=0.0, y=0.0):
            self.X = x
            self.Y = y

    class _Transform(object):
        Origin = _Vec(0.0, 0.0)
        BasisX = _Vec(1.0, 0.0)
        Determinant = 1.0

    class _BBox(object):
        Min = _Vec(0.0, 0.0)
        Max = _Vec(1.0, 1.0)

    class _Elem(object):
        Symbol = object()

        def GetTotalTransform(self):
            return _Transform()

        def get_BoundingBox(self, _view):
            return _BBox()

        def GetTypeId(self):
            return type("TID", (), {"IntegerValue": 42})()

    class _View(object):
        Scale = 100
        DetailLevel = 2
        Document = type("D", (), {"PathName": "doc.rvt"})()

    monkeypatch.setattr(symbol_raster, "_safe_int_element_id", lambda _e: 99)
    monkeypatch.setattr(symbol_raster, "_safe_type_sig_parts", lambda _e: ("Fam", "Type"))
    monkeypatch.setattr(symbol_raster, "to_view_local_2d", lambda pts, _view: [[0.0, 0.0] for _ in pts])
    monkeypatch.setattr(
        symbol_raster,
        "_instance_pose_in_view_2d",
        lambda *_args, **_kwargs: ((0.0, 0.0), (1.0, 0.0), False, 0.0),
    )
    monkeypatch.setattr(symbol_raster, "_cache_file_path", lambda _cfg, _fam, _key: "/tmp/cache.json")
    monkeypatch.setattr(symbol_raster, "_read_cache_entry", lambda _path: ({}, None))
    monkeypatch.setattr(symbol_raster, "_validate_cache_entry", lambda _cached, _expected: ([[0.0, 0.0]], None))

    elem_id, points = symbol_raster._collect_points_for_element(
        _View(), object(), _Elem(), {}, diagnostic_callback=lambda payload: events.append(payload)
    )

    assert elem_id == 99
    assert points
    assert len(events) == 1
    assert events[0]["symbol_type_key"] == "Fam|Type"
    assert events[0]["cache_hit"] is True
    assert events[0]["miss_reason"] is None
    assert events[0]["elapsed_ms"] >= 0.0


def test_collect_points_emits_miss_summary_on_rebuild_export_failure(monkeypatch):
    symbol_raster = _load_symbol_raster()
    events = []

    class _Vec(object):
        def __init__(self, x=0.0, y=0.0):
            self.X = x
            self.Y = y

    class _Transform(object):
        Origin = _Vec(0.0, 0.0)
        BasisX = _Vec(1.0, 0.0)
        Determinant = 1.0

    class _BBox(object):
        Min = _Vec(0.0, 0.0)
        Max = _Vec(1.0, 1.0)

    class _Elem(object):
        Symbol = object()

        def GetTotalTransform(self):
            return _Transform()

        def get_BoundingBox(self, _view):
            return _BBox()

        def GetTypeId(self):
            return type("TID", (), {"IntegerValue": 42})()

    class _View(object):
        Scale = 100
        DetailLevel = 2
        Document = type("D", (), {"PathName": "doc.rvt"})()

    monkeypatch.setattr(symbol_raster, "_safe_int_element_id", lambda _e: 99)
    monkeypatch.setattr(symbol_raster, "_safe_type_sig_parts", lambda _e: ("Fam", "Type"))
    monkeypatch.setattr(
        symbol_raster,
        "_instance_pose_in_view_2d",
        lambda *_args, **_kwargs: ((0.0, 0.0), (1.0, 0.0), False, 0.0),
    )
    monkeypatch.setattr(symbol_raster, "_cache_file_path", lambda _cfg, _fam, _key: "/tmp/cache.json")
    monkeypatch.setattr(symbol_raster, "_read_cache_entry", lambda _path: (None, "file not found"))
    monkeypatch.setattr(
        symbol_raster,
        "_create_fresh_view_with_symbol",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("export boom")),
    )

    elem_id, points = symbol_raster._collect_points_for_element(
        _View(), object(), _Elem(), {}, diagnostic_callback=lambda payload: events.append(payload)
    )

    assert elem_id is None
    assert points is None
    assert len(events) == 1
    assert events[0]["cache_hit"] is False
    assert events[0]["symbol_type_key"] == "Fam|Type"
    assert events[0]["miss_reason"].startswith("rebuild_export_failure:")


def test_cache_entry_validation_requires_schema_and_pipeline_version():
    symbol_raster = _load_symbol_raster()
    expected = {
        "cache_key": "k",
        "doc_scope": "d",
        "family_name": "f",
        "view_scale": 100,
        "detail_level": "2",
        "is_line_based": False,
    }
    entry = dict(expected)
    entry.update(
        {
            "cache_schema": "symbol_raster.v1",
            "pipeline_version": symbol_raster._SYMBOL_RASTER_PIPELINE_VERSION,
            "obb_width": 1.0,
            "obb_height": 2.0,
            "points": [[0.0, 1.0]],
        }
    )

    points, reason = symbol_raster._validate_cache_entry(entry, expected)
    assert reason is None
    assert points == [[0.0, 1.0]]

    bad_schema = dict(entry, cache_schema="old")
    _, reason = symbol_raster._validate_cache_entry(bad_schema, expected)
    assert reason == "wrong schema"

    bad_version = dict(entry, pipeline_version="old-version")
    _, reason = symbol_raster._validate_cache_entry(bad_version, expected)
    assert reason == "version mismatch"


def test_cache_entry_validation_rejects_invalid_points_payload():
    symbol_raster = _load_symbol_raster()
    expected = {
        "cache_key": "k",
        "doc_scope": "d",
        "family_name": "f",
        "view_scale": 100,
        "detail_level": "2",
        "is_line_based": False,
    }
    entry = dict(expected)
    entry.update(
        {
            "cache_schema": "symbol_raster.v1",
            "pipeline_version": symbol_raster._SYMBOL_RASTER_PIPELINE_VERSION,
            "obb_width": 1.0,
            "obb_height": 2.0,
            "points": [[0.0, "bad"]],
        }
    )

    _, reason = symbol_raster._validate_cache_entry(entry, expected)
    assert reason == "invalid points payload"


def test_collect_raster_points_groups_same_type_lookup_once(monkeypatch):
    symbol_raster = _load_symbol_raster()
    lookup_calls = []

    class _View(object):
        Document = object()

    class _Elem(object):
        def __init__(self, name):
            self.name = name

    elem_a = _Elem("a")
    elem_b = _Elem("b")

    contexts = {
        "a": {
            "elem_id": 101,
            "cache_key": "fam|type|k",
            "placement_point": (10.0, 0.0),
            "axis_x": (1.0, 0.0),
            "is_mirrored": False,
            "length_scale_x": 1.0,
        },
        "b": {
            "elem_id": 102,
            "cache_key": "fam|type|k",
            "placement_point": (20.0, 0.0),
            "axis_x": (1.0, 0.0),
            "is_mirrored": False,
            "length_scale_x": 1.0,
        },
    }

    monkeypatch.setattr(symbol_raster, "get_view_elements", lambda _view: [elem_a, elem_b])
    monkeypatch.setattr(symbol_raster, "is_family_instance", lambda _elem: True)
    monkeypatch.setattr(symbol_raster, "_build_symbol_instance_context", lambda _view, e: dict(contexts[e.name]))
    monkeypatch.setattr(
        symbol_raster,
        "_collect_canonical_points_for_context",
        lambda **kwargs: lookup_calls.append(kwargs["context"]["cache_key"]) or [[1.0, 0.0]],
    )

    out = symbol_raster.collect_raster_points_for_view(_View())
    assert lookup_calls == ["fam|type|k"]
    assert out[101] == [[11.0, 0.0]]
    assert out[102] == [[21.0, 0.0]]


def test_collect_raster_points_applies_per_instance_transforms_after_group_lookup(monkeypatch):
    symbol_raster = _load_symbol_raster()

    class _View(object):
        Document = object()

    class _Elem(object):
        def __init__(self, name):
            self.name = name

    elem_a = _Elem("a")
    elem_b = _Elem("b")
    monkeypatch.setattr(symbol_raster, "get_view_elements", lambda _view: [elem_a, elem_b])
    monkeypatch.setattr(symbol_raster, "is_family_instance", lambda _elem: True)
    monkeypatch.setattr(
        symbol_raster,
        "_build_symbol_instance_context",
        lambda _view, e: {
            "elem_id": 201 if e.name == "a" else 202,
            "cache_key": "fam|type|k",
            "placement_point": (0.0, 0.0) if e.name == "a" else (0.0, 5.0),
            "axis_x": (1.0, 0.0) if e.name == "a" else (0.0, 1.0),
            "is_mirrored": False,
            "length_scale_x": 1.0 if e.name == "a" else 2.0,
        },
    )
    monkeypatch.setattr(symbol_raster, "_collect_canonical_points_for_context", lambda **_kwargs: [[1.0, 0.0]])

    out = symbol_raster.collect_raster_points_for_view(_View())
    assert out[201] == [[1.0, 0.0]]
    assert out[202] == [[0.0, 7.0]]


def test_same_view_repeats_of_first_seen_type_remain_cold_for_temperature():
    accum = IndexDiagnosticAccumulator()

    view1 = accum.create_view_symbol_perf_accumulator()
    view1.accumulate(
        {"symbol_type_key": "Door|36x84", "cache_hit": False, "miss_reason": "file not found", "elapsed_ms": 2.0}
    )
    view1_summary = accum.finalize_view_symbol_perf(view1)
    assert view1_summary["cache_temperature"] == "cold"
    assert view1_summary["new_symbol_types_built_in_view"] == 1
    assert view1_summary["reused_symbol_types_in_view"] == 0

    view2 = accum.create_view_symbol_perf_accumulator()
    view2.accumulate({"symbol_type_key": "Door|36x84", "cache_hit": True, "elapsed_ms": 1.0})
    view2_summary = accum.finalize_view_symbol_perf(view2)
    assert view2_summary["cache_temperature"] == "warm"
    assert view2_summary["new_symbol_types_built_in_view"] == 0
    assert view2_summary["reused_symbol_types_in_view"] == 1
