import importlib
import sys
import types

sys.modules.setdefault("clr", types.SimpleNamespace(AddReference=lambda *_args, **_kwargs: None))
if "Autodesk.Revit.DB" not in sys.modules:
    db_mod = types.ModuleType("Autodesk.Revit.DB")
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


def test_repeated_same_key_call_uses_cache_without_fresh_view(monkeypatch):
    symbol_raster = _load_symbol_raster()
    cache_store = {}
    calls = {"fresh_view": 0}

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
            return type("TID", (), {"IntegerValue": 99})()

    class _View(object):
        Scale = 96
        DetailLevel = 2
        Document = type("D", (), {"PathName": "doc.rvt"})()

    monkeypatch.setattr(symbol_raster, "_safe_int_element_id", lambda _e: 11)
    monkeypatch.setattr(symbol_raster, "_safe_type_sig_parts", lambda _e: ("Fam", "Type"))
    monkeypatch.setattr(symbol_raster, "to_view_local_2d", lambda pts, _view: [[0.0, 0.0] for _ in pts])
    monkeypatch.setattr(symbol_raster, "_cache_file_path", lambda _cfg, _fam, _key: "cache.json")
    monkeypatch.setattr(
        symbol_raster,
        "_read_cache_entry",
        lambda path: (cache_store[path], None) if path in cache_store else (None, "file not found"),
    )
    monkeypatch.setattr(
        symbol_raster,
        "_write_cache_entry",
        lambda path, payload: cache_store.__setitem__(path, payload),
    )
    monkeypatch.setattr(symbol_raster, "_export_temp_view_png", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(symbol_raster, "_cleanup_export_tmp_dir", lambda _tmp: None)
    monkeypatch.setattr(symbol_raster, "_delete_temp_view", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(symbol_raster, "_write_diag_json", lambda *_args, **_kwargs: None)

    def _fresh_view(*_args, **_kwargs):
        calls["fresh_view"] += 1
        return object()

    monkeypatch.setattr(symbol_raster, "_create_fresh_view_with_symbol", _fresh_view)

    view = _View()
    elem = _Elem()
    _, points_first = symbol_raster._collect_points_for_element(view, object(), elem, {})
    _, points_second = symbol_raster._collect_points_for_element(view, object(), elem, {})

    assert points_first == []
    assert points_second == []
    assert calls["fresh_view"] == 1


def test_line_based_type_id_is_part_of_symbol_cache_key():
    symbol_raster = _load_symbol_raster()

    class _Vec(object):
        def __init__(self, x=0.0, y=0.0):
            self.X = x
            self.Y = y

    class _Tx(object):
        BasisX = _Vec(1.0, 0.0)
        Determinant = 1.0

    class _Elem(object):
        Symbol = None

        def __init__(self, tid):
            self._tid = tid

        def GetTotalTransform(self):
            return _Tx()

        def GetTypeId(self):
            return type("TID", (), {"IntegerValue": self._tid})()

    class _View(object):
        Scale = 100
        DetailLevel = 2
        Document = type("D", (), {"PathName": "doc.rvt"})()

    view = _View()
    elem_a = _Elem(101)
    elem_b = _Elem(202)
    key_a = symbol_raster._symbol_cache_key(elem_a, view, obb_width=1.0, obb_height=0.1)[0]
    key_b = symbol_raster._symbol_cache_key(elem_b, view, obb_width=1.0, obb_height=0.1)[0]

    assert key_a != key_b
    assert "tid101" in key_a
    assert "tid202" in key_b


def test_curve_overload_projects_direction_using_view_basis(monkeypatch):
    symbol_raster = _load_symbol_raster()

    class _Vec3(object):
        def __init__(self, x=0.0, y=0.0, z=0.0):
            self.X = x
            self.Y = y
            self.Z = z

    class _XYZ(_Vec3):
        pass

    class _Line(object):
        def __init__(self, start, end):
            self.start = start
            self.end = end

        @staticmethod
        def CreateBound(start, end):
            return _Line(start, end)

    class _ViewDrafting(object):
        @staticmethod
        def Create(_doc, _vft_id):
            return type("TmpView", (), {"Id": type("ID", (), {"IntegerValue": 7})(), "Scale": 100})()

    fake_db = sys.modules["Autodesk.Revit.DB"]
    monkeypatch.setattr(fake_db, "XYZ", _XYZ, raising=False)
    monkeypatch.setattr(fake_db, "Line", _Line, raising=False)
    monkeypatch.setattr(fake_db, "ViewDrafting", _ViewDrafting, raising=False)
    monkeypatch.setattr(fake_db, "BoundingBoxXYZ", type("BoundingBoxXYZ", (), {}), raising=False)

    class _Scope(object):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class _Symbol(object):
        IsActive = True
        Family = type("Family", (), {"Name": "LineFam"})()

    class _TempInst(object):
        def get_BoundingBox(self, _view):
            return None

    class _Create(object):
        def __init__(self):
            self.line = None

        def NewFamilyInstance(self, first_arg, symbol, _view):
            if isinstance(first_arg, _XYZ):
                raise RuntimeError("force curve overload")
            self.line = first_arg
            return _TempInst()

    create = _Create()
    doc = type("Doc", (), {"Create": create, "Regenerate": lambda self: None})()

    class _Elem(object):
        Symbol = _Symbol()

        def GetTotalTransform(self):
            return type("TX", (), {"BasisX": _Vec3(0.0, 0.0, 1.0)})()

    view = type(
        "View",
        (),
        {"Scale": 100, "RightDirection": _Vec3(0.0, 1.0, 0.0), "UpDirection": _Vec3(0.0, 0.0, 1.0)},
    )()

    monkeypatch.setattr(symbol_raster, "_get_drafting_view_family_type_id", lambda _doc: 1)
    monkeypatch.setattr(symbol_raster, "scoped_transaction", lambda *_args, **_kwargs: _Scope())
    monkeypatch.setattr(symbol_raster, "_write_diag_json", lambda *_args, **_kwargs: None)

    tmp_view = symbol_raster._create_fresh_view_with_symbol(doc, view, _Elem(), obb_width=2.0, obb_height=0.5)

    assert tmp_view is not None
    assert create.line is not None
    assert abs(float(create.line.end.X)) < 1e-9
    assert float(create.line.end.Y) > 0.0
