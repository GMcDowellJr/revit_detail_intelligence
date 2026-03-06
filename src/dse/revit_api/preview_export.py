import os

from dse.io_paths import ensure_dir


def _safe_view_name(view):
    try:
        return str(view.Name)
    except Exception:
        return "view"


def _preview_file_path(preview_root, view_id, state_hash=None):
    suffix = ""
    if state_hash:
        suffix = "_{}".format(str(state_hash)[:12])
    return os.path.join(preview_root, "view_{}{}.png".format(int(view_id), suffix))


def get_or_create_view_preview(view, config, state_hash=None):
    """Return preview PNG path for a view, exporting once and reusing if present."""

    preview_root = ensure_dir(config.get("preview_root", r"C:\temp\revit_detail_intelligence\previews"))
    view_id = getattr(getattr(view, "Id", None), "IntegerValue", None)
    if view_id is None:
        return None

    out_path = _preview_file_path(preview_root, view_id, state_hash=state_hash)
    if os.path.exists(out_path):
        return out_path

    # Fallback: reuse any previously exported preview for this view id even if hash suffix differs.
    prefix = "view_{}".format(int(view_id))
    for fname in os.listdir(preview_root):
        if fname.startswith(prefix) and fname.lower().endswith(".png"):
            candidate = os.path.join(preview_root, fname)
            if os.path.exists(candidate):
                return candidate

    try:
        import clr

        clr.AddReference("RevitAPI")
        from Autodesk.Revit.DB import (
            ExportRange,
            FitDirectionType,
            ImageExportOptions,
            ImageFileType,
            ImageResolution,
        )

        opts = ImageExportOptions()
        opts.ExportRange = ExportRange.SetOfViews
        opts.HLRandWFViewsFileType = ImageFileType.PNG
        opts.ShadowViewsFileType = ImageFileType.PNG
        opts.ImageResolution = ImageResolution.DPI_600
        opts.FitDirection = FitDirectionType.Horizontal
        opts.PixelSize = int(config.get("preview_longest_side", 2048))
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
