import hashlib
import json
import os
import re
import struct

from dse.io_paths import ensure_dir


def _stable_json_hash(payload):
    txt = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha1(txt.encode("utf-8")).hexdigest()


def _source_scope_hash(source_doc_id=None, source_doc_name=None):
    scope_payload = {
        "source_doc_id": None if source_doc_id is None else str(source_doc_id),
        "source_doc_name": None if source_doc_name is None else str(source_doc_name),
    }
    if scope_payload["source_doc_id"] is None and scope_payload["source_doc_name"] is None:
        scope_payload = {"source_scope": "<no-doc>"}
    return _stable_json_hash(scope_payload)[:16]


def _view_doc_provenance(view):
    doc = getattr(view, "Document", None)
    if doc is None:
        return None, None
    source_doc_id = getattr(doc, "PathName", None)
    if not source_doc_id:
        source_doc_id = getattr(getattr(doc, "Application", None), "VersionBuild", None)
    source_doc_name = getattr(doc, "Title", None)
    return source_doc_id, source_doc_name


def _preview_filename(view_id, source_doc_id=None, source_doc_name=None):
    if source_doc_id is None and source_doc_name is None:
        return "view_{}.png".format(int(view_id))
    return "view_{}__doc_{}.png".format(int(view_id), _source_scope_hash(source_doc_id, source_doc_name))


def _preview_file_path(preview_root, view_id, source_doc_id=None, source_doc_name=None):
    return os.path.join(preview_root, _preview_filename(view_id, source_doc_id, source_doc_name))


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




def _find_exported_preview_file(preview_root, stem):
    pattern = re.compile(r"^{}(?:\..*)?\.png$".format(re.escape(str(stem))))
    candidates = []
    try:
        for name in os.listdir(preview_root):
            if name.lower().endswith(".png") and pattern.match(name):
                path = os.path.join(preview_root, name)
                if os.path.exists(path):
                    candidates.append(path)
    except Exception:
        return None
    if not candidates:
        return None
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def generate_and_cache_view_preview(view, config, source_doc_id=None, source_doc_name=None):
    """Return cached full-resolution preview PNG path for a view."""

    preview_root = ensure_dir(
        config.get("preview_root", r"C:\temp\revit_detail_intelligence\cache\previews")
    )
    view_id = getattr(getattr(view, "Id", None), "IntegerValue", None)
    if view_id is None:
        return None

    if source_doc_id is None and source_doc_name is None:
        source_doc_id, source_doc_name = _view_doc_provenance(view)

    required_side = int(config.get("preview_longest_side", 2400))
    out_path = _preview_file_path(preview_root, view_id, source_doc_id, source_doc_name)
    if os.path.exists(out_path) and _has_required_resolution(out_path, required_side):
        return out_path

    out_stem = os.path.splitext(os.path.basename(out_path))[0]
    existing = _find_exported_preview_file(preview_root, out_stem)
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

        exported_fallback = _find_exported_preview_file(preview_root, out_stem)
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


def get_cached_view_preview(view_id, config, source_doc_id=None, source_doc_name=None):
    preview_root = ensure_dir(
        config.get("preview_root", r"C:\temp\revit_detail_intelligence\cache\previews")
    )
    required_side = int(config.get("preview_longest_side", 2400))
    out_path = _preview_file_path(preview_root, view_id, source_doc_id, source_doc_name)
    if os.path.exists(out_path) and _has_required_resolution(out_path, required_side):
        return out_path
    return None
