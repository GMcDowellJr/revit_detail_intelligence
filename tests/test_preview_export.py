from dse.outputs.contact_sheet import _save_png
from dse.revit_api.preview_export import get_cached_view_preview


def _write_png(path, width, height):
    _save_png(path, width, height, bytes((255, 0, 0) * (width * height)))


def test_get_cached_view_preview_returns_path_when_present_and_resolution_ok(tmp_path):
    preview_root = tmp_path / "previews"
    preview_root.mkdir(parents=True, exist_ok=True)
    out_path = preview_root / "view_42.png"
    _write_png(str(out_path), 128, 64)

    cfg = {"preview_root": str(preview_root), "preview_longest_side": 120}
    assert get_cached_view_preview(42, cfg) == str(out_path)


def test_get_cached_view_preview_returns_none_when_resolution_too_small(tmp_path):
    preview_root = tmp_path / "previews"
    preview_root.mkdir(parents=True, exist_ok=True)
    out_path = preview_root / "view_77.png"
    _write_png(str(out_path), 64, 32)

    cfg = {"preview_root": str(preview_root), "preview_longest_side": 128}
    assert get_cached_view_preview(77, cfg) is None


def test_get_cached_view_preview_returns_none_when_absent(tmp_path):
    preview_root = tmp_path / "previews"
    preview_root.mkdir(parents=True, exist_ok=True)

    cfg = {"preview_root": str(preview_root), "preview_longest_side": 10}
    assert get_cached_view_preview(88, cfg) is None
