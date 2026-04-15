import importlib
import os
import sys
import types

import pytest

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


@pytest.fixture(autouse=True)
def _clear_symbol_raster_memory_cache():
    symbol_raster = _load_symbol_raster()
    symbol_raster._RUN_MEMORY_SYMBOL_RASTER_CACHE.clear()


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
    monkeypatch.setattr(
        symbol_raster,
        "_instance_pose_in_view_2d",
        lambda *_args, **_kwargs: ((0.0, 0.0), (1.0, 0.0), False, 0.0),
    )
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

    class _Elem(object):
        Symbol = None

        def __init__(self, tid):
            self._tid = tid

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
    key_b = symbol_raster._symbol_cache_key(elem_b, view, obb_width=10.0, obb_height=0.1)[0]

    assert key_a != key_b
    assert "tid101" in key_a
    assert "tid202" in key_b
    assert "line1" in key_a
    assert "line1" in key_b


def test_curve_overload_uses_canonical_line_length_and_direction(monkeypatch):
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

    view = type("View", (), {"Scale": 100})()

    monkeypatch.setattr(symbol_raster, "_get_drafting_view_family_type_id", lambda _doc: 1)
    monkeypatch.setattr(symbol_raster, "scoped_transaction", lambda *_args, **_kwargs: _Scope())
    monkeypatch.setattr(symbol_raster, "_write_diag_json", lambda *_args, **_kwargs: None)

    tmp_view = symbol_raster._create_fresh_view_with_symbol(doc, view, _Elem(), obb_width=2.0, obb_height=0.5)

    assert tmp_view is not None
    assert create.line is not None
    assert abs(float(create.line.end.X) - 1.0) < 1e-9
    assert abs(float(create.line.end.Y)) < 1e-9


def test_apply_canonical_instance_transform_handles_rotation_mirror_and_translation():
    symbol_raster = _load_symbol_raster()
    canonical_points = [[1.0, 2.0]]
    out = symbol_raster._apply_canonical_instance_transform(
        canonical_points,
        placement_point=(10.0, 20.0),
        axis_x=(0.0, 1.0),  # +90 deg
        mirrored=True,
        length_scale_x=2.0,
    )
    # x' = 10 + 2*0 + 2*1 = 12 ; y' = 20 + 2*1 + 2*0 = 22
    assert len(out) == 1
    assert abs(out[0][0] - 12.0) < 1e-9
    assert abs(out[0][1] - 22.0) < 1e-9


def test_collect_points_cache_hit_applies_line_length_scaling(monkeypatch):
    symbol_raster = _load_symbol_raster()
    monkeypatch.setattr(symbol_raster, "_safe_type_sig_parts", lambda _e: ("Fam", "Type"))

    class _Vec(object):
        def __init__(self, x=0.0, y=0.0):
            self.X = x
            self.Y = y

    class _Transform(object):
        Origin = type("V", (), {"X": 0.0, "Y": 0.0, "Z": 0.0})()
        BasisX = type("V", (), {"X": 1.0, "Y": 0.0, "Z": 0.0})()
        Determinant = 1.0

    class _BBox(object):
        Min = _Vec(0.0, 0.0)
        Max = _Vec(1.0, 0.1)

    class _Elem(object):
        Symbol = None

        def GetTotalTransform(self):
            return _Transform()

        def get_BoundingBox(self, _view):
            return _BBox()

        def GetTypeId(self):
            return type("TID", (), {"IntegerValue": 77})()

    class _View(object):
        Scale = 96
        DetailLevel = 2
        Document = type("D", (), {"PathName": "doc.rvt"})()
        RightDirection = type("V", (), {"X": 1.0, "Y": 0.0, "Z": 0.0})()
        UpDirection = type("V", (), {"X": 0.0, "Y": 1.0, "Z": 0.0})()
        Origin = type("V", (), {"X": 0.0, "Y": 0.0, "Z": 0.0})()

    elem = _Elem()
    view = _View()
    key, fam, _type, scale, dl, is_line, doc_scope, _tid = symbol_raster._symbol_cache_key(elem, view)
    cached_entry = {
        "cache_schema": "symbol_raster.v1",
        "pipeline_version": symbol_raster._SYMBOL_RASTER_PIPELINE_VERSION,
        "cache_key": key,
        "doc_scope": doc_scope,
        "family_name": fam,
        "view_scale": scale,
        "detail_level": dl,
        "is_line_based": is_line,
        "obb_width": 1.0,
        "obb_height": 0.1,
        "points": [[1.0, 0.0]],
    }

    monkeypatch.setattr(symbol_raster, "_safe_int_element_id", lambda _e: 9)
    monkeypatch.setattr(symbol_raster, "_cache_file_path", lambda *_args, **_kwargs: "cache.json")
    monkeypatch.setattr(symbol_raster, "_read_cache_entry", lambda _path: (cached_entry, None))
    monkeypatch.setattr(symbol_raster, "_write_diag_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(symbol_raster, "_actual_instance_length_ft", lambda *_args, **_kwargs: 2.0)
    monkeypatch.setattr(
        symbol_raster,
        "_instance_pose_in_view_2d",
        lambda *_args, **_kwargs: ((5.0, 5.0), (1.0, 0.0), False, 0.0),
    )

    _elem_id, points = symbol_raster._collect_points_for_element(view, object(), elem, {})
    assert points == [[7.0, 5.0]]


def test_collect_points_cache_hit_applies_point_rotation_and_mirror(monkeypatch):
    symbol_raster = _load_symbol_raster()
    monkeypatch.setattr(symbol_raster, "_safe_type_sig_parts", lambda _e: ("Fam", "Type"))

    class _Vec(object):
        def __init__(self, x=0.0, y=0.0):
            self.X = x
            self.Y = y

    class _Transform(object):
        Origin = type("V", (), {"X": 0.0, "Y": 0.0, "Z": 0.0})()
        BasisX = type("V", (), {"X": 1.0, "Y": 0.0, "Z": 0.0})()
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
            return type("TID", (), {"IntegerValue": 88})()

    class _View(object):
        Scale = 96
        DetailLevel = 2
        Document = type("D", (), {"PathName": "doc.rvt"})()
        RightDirection = type("V", (), {"X": 1.0, "Y": 0.0, "Z": 0.0})()
        UpDirection = type("V", (), {"X": 0.0, "Y": 1.0, "Z": 0.0})()
        Origin = type("V", (), {"X": 0.0, "Y": 0.0, "Z": 0.0})()

    elem = _Elem()
    view = _View()
    key, fam, _type, scale, dl, is_line, doc_scope, _tid = symbol_raster._symbol_cache_key(elem, view)
    cached_entry = {
        "cache_schema": "symbol_raster.v1",
        "pipeline_version": symbol_raster._SYMBOL_RASTER_PIPELINE_VERSION,
        "cache_key": key,
        "doc_scope": doc_scope,
        "family_name": fam,
        "view_scale": scale,
        "detail_level": dl,
        "is_line_based": is_line,
        "obb_width": 1.0,
        "obb_height": 1.0,
        "points": [[1.0, 2.0]],
    }

    monkeypatch.setattr(symbol_raster, "_safe_int_element_id", lambda _e: 10)
    monkeypatch.setattr(symbol_raster, "_cache_file_path", lambda *_args, **_kwargs: "cache.json")
    monkeypatch.setattr(symbol_raster, "_read_cache_entry", lambda _path: (cached_entry, None))
    monkeypatch.setattr(symbol_raster, "_write_diag_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        symbol_raster,
        "_instance_pose_in_view_2d",
        lambda *_args, **_kwargs: ((3.0, 4.0), (0.0, 1.0), True, 90.0),
    )

    _elem_id, points = symbol_raster._collect_points_for_element(view, object(), elem, {})
    assert points == [[5.0, 5.0]]


def test_cache_miss_uses_canonical_bounds_not_instance_obb(monkeypatch, tmp_path):
    symbol_raster = _load_symbol_raster()
    monkeypatch.setattr(symbol_raster, "_safe_type_sig_parts", lambda _e: ("Fam", "Type"))

    class _Vec(object):
        def __init__(self, x=0.0, y=0.0):
            self.X = x
            self.Y = y

    class _Transform(object):
        Origin = type("V", (), {"X": 0.0, "Y": 0.0, "Z": 0.0})()
        BasisX = type("V", (), {"X": 1.0, "Y": 0.0, "Z": 0.0})()
        Determinant = 1.0

    class _BBox(object):
        Min = _Vec(0.0, 0.0)
        Max = _Vec(100.0, 50.0)  # Deliberately large instance OBB

    class _Elem(object):
        Symbol = object()

        def GetTotalTransform(self):
            return _Transform()

        def get_BoundingBox(self, _view):
            return _BBox()

        def GetTypeId(self):
            return type("TID", (), {"IntegerValue": 89})()

    class _View(object):
        Scale = 96
        DetailLevel = 2
        Document = type("D", (), {"PathName": "doc.rvt"})()
        RightDirection = type("V", (), {"X": 1.0, "Y": 0.0, "Z": 0.0})()
        UpDirection = type("V", (), {"X": 0.0, "Y": 1.0, "Z": 0.0})()
        Origin = type("V", (), {"X": 0.0, "Y": 0.0, "Z": 0.0})()

    src_png = tmp_path / "src.png"
    src_png.write_bytes(b"png")
    retained_png = tmp_path / "retained.png"
    captured_entry = {}

    monkeypatch.setattr(symbol_raster, "_safe_int_element_id", lambda _e: 11)
    monkeypatch.setattr(symbol_raster, "_cache_file_path", lambda *_args, **_kwargs: "cache.json")
    monkeypatch.setattr(symbol_raster, "_read_cache_entry", lambda _path: (None, "file not found"))
    monkeypatch.setattr(symbol_raster, "_write_diag_json", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        symbol_raster,
        "_instance_pose_in_view_2d",
        lambda *_args, **_kwargs: ((0.0, 0.0), (1.0, 0.0), False, 0.0),
    )
    monkeypatch.setattr(
        symbol_raster,
        "_create_fresh_view_with_symbol",
        lambda *_args, **_kwargs: (
            object(),
            {"min_x": 0.0, "max_x": 1.0, "min_y": 0.0, "max_y": 1.0},
        ),
    )
    monkeypatch.setattr(symbol_raster, "_export_temp_view_png", lambda *_args, **_kwargs: (str(src_png), None))
    monkeypatch.setattr(symbol_raster, "_retained_png_path", lambda *_args, **_kwargs: str(retained_png))
    monkeypatch.setattr(symbol_raster, "_png_to_luminance", lambda *_args, **_kwargs: (10, 10, [0] * 100))
    monkeypatch.setattr(symbol_raster, "_edge_pixels", lambda *_args, **_kwargs: [(0, 0)])
    monkeypatch.setattr(symbol_raster, "_delete_temp_view", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(symbol_raster, "_cleanup_export_tmp_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(symbol_raster, "_write_cache_entry", lambda _path, payload: captured_entry.update(payload))

    _elem_id, points = symbol_raster._collect_points_for_element(_View(), object(), _Elem(), {})

    assert os.path.exists(retained_png)
    assert captured_entry["canonical_bounds"] == {"min_x": 0.0, "max_x": 1.0, "min_y": 0.0, "max_y": 1.0}
    assert points and abs(points[0][0] + 0.25) < 1e-9
    assert points and abs(points[0][1] - 1.25) < 1e-9


def test_collect_canonical_points_uses_memory_after_disk_hit(monkeypatch):
    symbol_raster = _load_symbol_raster()
    context = {
        "cache_key": "k1",
        "family_name": "Fam",
        "type_name": "Type",
        "view_scale": 96,
        "detail_level": "2",
        "is_line_based": False,
        "doc_scope": "doc",
        "obb_width": 1.0,
        "obb_height": 1.0,
    }
    cached_payload = {"payload": "from_disk"}
    points_expected = [[1.0, 2.0]]
    calls = {"read": 0, "validate": 0}
    events = []

    monkeypatch.setattr(symbol_raster, "_cache_file_path", lambda *_args, **_kwargs: "cache.json")

    def _read(_path):
        calls["read"] += 1
        return cached_payload, None

    def _validate(cached, _expected):
        calls["validate"] += 1
        assert cached is cached_payload
        return points_expected, None

    monkeypatch.setattr(symbol_raster, "_read_cache_entry", _read)
    monkeypatch.setattr(symbol_raster, "_validate_cache_entry", _validate)

    out1 = symbol_raster._collect_canonical_points_for_context(
        view=object(),
        doc=object(),
        element=object(),
        context=context,
        config={},
        diagnostic_callback=lambda row: events.append(row),
    )
    out2 = symbol_raster._collect_canonical_points_for_context(
        view=object(),
        doc=object(),
        element=object(),
        context=context,
        config={},
        diagnostic_callback=lambda row: events.append(row),
    )

    assert out1 == points_expected
    assert out2 == points_expected
    assert calls == {"read": 1, "validate": 1}
    assert events[0]["cache_hit"] is True and events[0]["cache_layer"] == "disk"
    assert events[1]["cache_hit"] is True and events[1]["cache_layer"] == "memory"


def test_collect_canonical_points_uses_memory_after_rebuild(monkeypatch):
    symbol_raster = _load_symbol_raster()
    context = {
        "cache_key": "k2",
        "family_name": "Fam",
        "type_name": "Type",
        "view_scale": 96,
        "detail_level": "2",
        "is_line_based": False,
        "doc_scope": "doc",
        "obb_width": 1.0,
        "obb_height": 1.0,
        "elem_id": 1,
    }
    calls = {"read": 0, "fresh_view": 0}

    monkeypatch.setattr(symbol_raster, "_cache_file_path", lambda *_args, **_kwargs: "cache.json")
    monkeypatch.setattr(
        symbol_raster,
        "_read_cache_entry",
        lambda _path: (calls.__setitem__("read", calls["read"] + 1) or (None, "file not found")),
    )
    monkeypatch.setattr(symbol_raster, "_write_cache_entry", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        symbol_raster,
        "_create_fresh_view_with_symbol",
        lambda *_args, **_kwargs: (calls.__setitem__("fresh_view", calls["fresh_view"] + 1) or object()),
    )
    monkeypatch.setattr(symbol_raster, "_export_temp_view_png", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(symbol_raster, "_delete_temp_view", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(symbol_raster, "_cleanup_export_tmp_dir", lambda *_args, **_kwargs: None)

    out1 = symbol_raster._collect_canonical_points_for_context(
        view=object(),
        doc=object(),
        element=object(),
        context=context,
        config={},
    )
    out2 = symbol_raster._collect_canonical_points_for_context(
        view=object(),
        doc=object(),
        element=object(),
        context=context,
        config={},
    )

    assert out1 == []
    assert out2 == []
    assert calls["fresh_view"] == 1
    assert calls["read"] == 1
