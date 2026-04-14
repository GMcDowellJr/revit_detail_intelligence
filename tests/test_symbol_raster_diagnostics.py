import importlib
import sys
import types

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
        "_collect_points_for_element",
        lambda *_args, **_kwargs: (7, [[0.0, 1.0]]),
    )

    out = symbol_raster.collect_raster_points_for_view(_View(), diagnostic_callback=lambda row: calls.append(row))

    assert out == {7: [[0.0, 1.0]]}
    assert calls == []


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
