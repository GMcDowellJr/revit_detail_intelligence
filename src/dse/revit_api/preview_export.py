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

        exported_default = opts.GetFileName(view.Document, view.Id)
        if exported_default and os.path.exists(exported_default):
            if exported_default != out_path:
                try:
                    os.replace(exported_default, out_path)
                except Exception:
                    return exported_default
            return out_path
        if os.path.exists(out_path):
            return out_path
    except Exception:
        return None

    return None
