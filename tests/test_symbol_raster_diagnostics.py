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
