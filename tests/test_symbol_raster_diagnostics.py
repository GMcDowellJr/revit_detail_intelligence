import importlib
import json
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


def test_diag_events_buffer_until_flush(tmp_path, monkeypatch):
    symbol_raster = _load_symbol_raster()
    diag_path = tmp_path / "symbol_raster_diagnostics.json"
    monkeypatch.setattr(symbol_raster, "_DIAG_JSON_PATH", str(diag_path))
    symbol_raster._DIAG_ROWS_BUFFER[:] = []

    symbol_raster._write_diag_json("cache_lookup_started", {"element_id": 1})
    symbol_raster._write_diag_json("cache_hit", {"element_id": 1})

    assert not diag_path.exists()

    symbol_raster._flush_diag_json_buffer()

    rows = json.loads(diag_path.read_text(encoding="utf-8"))
    assert [row["event"] for row in rows] == ["cache_lookup_started", "cache_hit"]


def test_diag_flush_appends_existing_json_array(tmp_path, monkeypatch):
    symbol_raster = _load_symbol_raster()
    diag_path = tmp_path / "symbol_raster_diagnostics.json"
    seed = [{"event": "existing", "ts_utc": "2026-01-01T00:00:00+00:00", "payload": {"ok": True}}]
    diag_path.write_text(json.dumps(seed), encoding="utf-8")
    monkeypatch.setattr(symbol_raster, "_DIAG_JSON_PATH", str(diag_path))
    symbol_raster._DIAG_ROWS_BUFFER[:] = []

    symbol_raster._write_diag_json("cache_miss", {"element_id": 2})
    symbol_raster._flush_diag_json_buffer()

    rows = json.loads(diag_path.read_text(encoding="utf-8"))
    assert len(rows) == 2
    assert rows[0]["event"] == "existing"
    assert rows[1]["event"] == "cache_miss"


def test_collect_raster_points_flushes_diagnostics_once(monkeypatch):
    symbol_raster = _load_symbol_raster()
    calls = {"flush": 0}

    def _flush_spy():
        calls["flush"] += 1

    class _View(object):
        Document = object()

    monkeypatch.setattr(symbol_raster, "_flush_diag_json_buffer", _flush_spy)
    monkeypatch.setattr(symbol_raster, "get_view_elements", lambda _view: [])

    out = symbol_raster.collect_raster_points_for_view(_View())

    assert out == {}
    assert calls["flush"] == 1


def test_collect_points_emits_cache_lookup_diagnostics(monkeypatch):
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
    monkeypatch.setattr(symbol_raster, "_cache_file_path", lambda _cfg, _fam, _key: "/tmp/cache.json")
    monkeypatch.setattr(symbol_raster, "_read_cache_entry", lambda _path: (None, "file not found"))
    monkeypatch.setattr(symbol_raster, "_create_fresh_view_with_symbol", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(symbol_raster, "_write_diag_json", lambda event, payload: events.append((event, payload)))

    elem_id, points = symbol_raster._collect_points_for_element(_View(), object(), _Elem(), {})

    assert elem_id is None
    assert points is None
    assert [event for event, _ in events[:3]] == [
        "cache_lookup_started",
        "cache_miss_reason",
        "cache_miss",
    ]
    payload = events[0][1]
    assert payload["cache_key"]
    assert payload["cache_path"] == "/tmp/cache.json"
    assert payload["doc_scope"]
    assert payload["family_name"] == "Fam"
    assert payload["type_name"] == "Type"
    assert payload["type_id_int"] == 42
    assert payload["view_scale"] == 100


def test_cache_entry_validation_requires_schema_and_pipeline_version():
    symbol_raster = _load_symbol_raster()
    expected = {
        "cache_key": "k",
        "doc_scope": "d",
        "family_name": "f",
        "view_scale": 100,
        "detail_level": "2",
        "orientation_bucket": "r0",
        "length_bucket_in": 12,
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
        "orientation_bucket": "r0",
        "length_bucket_in": 12,
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
