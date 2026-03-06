import os
import struct

from dse.io_paths import ensure_dir


def _preview_file_path(preview_root, view_id):
    return os.path.join(preview_root, "view_{}.png".format(int(view_id)))


def _png_size(path):
    try:
        with open(path, "rb") as handle:
            head = handle.read(24)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        if head[12:16] != b"IHDR":
            return None
        width = struct.unpack("!I", head[16:20])[0]
        height = struct.unpack("!I", head[20:24])[0]
        return (width, height)
    except Exception:
        return None


def _has_required_resolution(path, required_longest_side):
    size = _png_size(path)
    if size is None:
        return False
    longest = max(size[0], size[1])
    return int(longest) >= int(required_longest_side)




def _find_exported_preview_file(preview_root, view_id):
    prefix = "view_{}".format(int(view_id))
    candidates = []
    try:
        for name in os.listdir(preview_root):
            if name.lower().endswith(".png") and name.startswith(prefix):
                path = os.path.join(preview_root, name)
                if os.path.exists(path):
                    candidates.append(path)
    except Exception:
        return None
    if not candidates:
        return None
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def get_or_create_view_preview(view, config):
    """Return cached full-resolution preview PNG path for a view."""

    preview_root = ensure_dir(
        config.get("preview_root", r"C:\temp\revit_detail_intelligence\cache\previews")
    )
    view_id = getattr(getattr(view, "Id", None), "IntegerValue", None)
    if view_id is None:
        return None

    required_side = int(config.get("preview_longest_side", 2400))
    out_path = _preview_file_path(preview_root, view_id)
    if os.path.exists(out_path) and _has_required_resolution(out_path, required_side):
        return out_path

    existing = _find_exported_preview_file(preview_root, view_id)
    if existing and _has_required_resolution(existing, required_side):
        if existing != out_path:
            try:
                os.replace(existing, out_path)
            except Exception:
                return existing
        return out_path

    try:
        import clr

        clr.AddReference("RevitAPI")
        from Autodesk.Revit.DB import (
            ExportRange,
            FitDirectionType,
            ImageExportOptions,
            ImageFileType,
            ImageResolution,
            ZoomFitType,
        )

        opts = ImageExportOptions()
        opts.ExportRange = ExportRange.SetOfViews
        opts.HLRandWFViewsFileType = ImageFileType.PNG
        opts.ShadowViewsFileType = ImageFileType.PNG
        opts.ImageResolution = ImageResolution.DPI_600
        opts.FitDirection = FitDirectionType.Horizontal
        opts.ZoomType = ZoomFitType.FitToPage
        opts.PixelSize = required_side
        opts.FilePath = os.path.splitext(out_path)[0]
        opts.SetViewsAndSheets([view.Id])

        view.Document.ExportImage(opts)

        exported_default = None
        try:
            exported_default = opts.GetFileName(view.Document, view.Id)
        except Exception:
            exported_default = None

        if exported_default and os.path.exists(exported_default):
            if exported_default != out_path:
                try:
                    os.replace(exported_default, out_path)
                except Exception:
                    return exported_default
            return out_path

        if os.path.exists(out_path):
            return out_path

        exported_fallback = _find_exported_preview_file(preview_root, view_id)
        if exported_fallback and os.path.exists(exported_fallback):
            if exported_fallback != out_path:
                try:
                    os.replace(exported_fallback, out_path)
                except Exception:
                    return exported_fallback
            return out_path
    except Exception:
        return None

    return None
