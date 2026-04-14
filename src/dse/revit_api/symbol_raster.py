import hashlib
import json
import math
import os
import re
import struct
import tempfile
import warnings
import zlib
from datetime import datetime, timezone

from dse.features.tokens import type_signature
from dse.io_paths import ensure_dir
from dse.revit_api.collect import get_view_elements, is_family_instance
from dse.revit_api.geometry_2d import to_view_local_2d

_DIAG_JSON_PATH = os.path.abspath(
    os.path.join(r"C:\Temp\revit_detail_intelligence\cache", "symbol_raster_diagnostics.json")
)


def _write_diag_json(event, payload):
    row = {
        "event": str(event),
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    try:
        ensure_dir(os.path.dirname(_DIAG_JSON_PATH))
        existing = []
        if os.path.exists(_DIAG_JSON_PATH):
            with open(_DIAG_JSON_PATH, "r", encoding="utf-8") as handle:
                existing = json.load(handle)
            if not isinstance(existing, list):
                existing = []
        existing.append(row)
        with open(_DIAG_JSON_PATH, "w", encoding="utf-8") as handle:
            json.dump(existing, handle, indent=2, ensure_ascii=True)
    except Exception:
        pass


def _safe_int_element_id(element):
    elem_id = getattr(element, "Id", None)
    if elem_id is None:
        return None
    try:
        return int(elem_id.Value)
    except Exception:
        try:
            return int(elem_id.IntegerValue)
        except Exception:
            return None


def _sanitize_path_component(text):
    txt = "" if text is None else str(text).strip()
    txt = re.sub(r"[^A-Za-z0-9._-]+", "_", txt)
    return txt[:96] or "unknown"


def _safe_type_sig_parts(element):
    sig = ""
    try:
        sig = type_signature(element)
    except Exception:
        sig = ""
    if "|" in sig:
        family_name, type_name = sig.split("|", 1)
    else:
        family_name, type_name = ("<no-family>", "<unknown-type>")
    return family_name.strip() or "<no-family>", type_name.strip() or "<unknown-type>"


def _orientation_bucket_from_transform(transform):
    basis_x = getattr(transform, "BasisX", None)
    bx = float(getattr(basis_x, "X", 1.0))
    by = float(getattr(basis_x, "Y", 0.0))
    angle_deg = math.degrees(math.atan2(by, bx)) % 360.0
    bucket = int(round(angle_deg / 45.0)) % 8
    det = float(getattr(transform, "Determinant", 1.0))
    is_mirrored = det < 0.0
    return "r{}{}".format(bucket, "m" if is_mirrored else "")


def _document_identity(doc):
    if doc is None:
        return "<no-doc>"
    path_name = str(getattr(doc, "PathName", "") or "").strip()
    if path_name:
        return path_name
    title = str(getattr(doc, "Title", "") or "").strip()
    if title:
        return title
    build = str(getattr(getattr(doc, "Application", None), "VersionBuild", "") or "").strip()
    if build:
        return build
    try:
        return "doc_hash:{}".format(int(doc.GetHashCode()))
    except Exception:
        return "<no-doc>"


def _symbol_cache_key(element, view, obb_width=0.0, obb_height=0.0):
    family_name, type_name = _safe_type_sig_parts(element)
    view_scale = int(round(float(getattr(view, "Scale", 1))))
    detail_level = str(int(view.DetailLevel))
    transform = element.GetTotalTransform()
    orientation_bucket = _orientation_bucket_from_transform(transform)
    doc_identity = _document_identity(getattr(view, "Document", None))
    doc_scope = hashlib.sha1(doc_identity.encode("utf-8")).hexdigest()[:12]
    length_bucket_in = int(math.ceil(max(obb_width, obb_height) * 12.0))
    # Stable type-id disambiguates Symbol-less instances (line-based families resolved via
    # GetTypeId) that share a placeholder family name, preventing cross-family cache collisions.
    type_id_int = 0
    try:
        raw_type_id = element.GetTypeId()
        if raw_type_id is not None:
            try:
                type_id_int = int(raw_type_id.Value)
            except Exception:
                try:
                    type_id_int = int(raw_type_id.IntegerValue)
                except Exception:
                    type_id_int = 0
    except Exception:
        type_id_int = 0
    # Cache schema note: detail_level, length_bucket_in, and type_id_int were added to the key.
    # Existing symbol_rasters caches built without these fields are intentionally invalidated
    # and will rebuild on misses.
    key = "{}|{}|{}|{}|{}|{}|{}in|tid{}".format(
        doc_scope, family_name, type_name, view_scale, detail_level, orientation_bucket,
        length_bucket_in, type_id_int
    )
    return key, family_name, type_name, view_scale, detail_level, orientation_bucket, doc_scope, length_bucket_in


def _cache_file_path(config, family_name, cache_key):
    cache_root = ensure_dir(config.get("cache_root", r"C:\temp\revit_detail_intelligence\cache"))
    family_dir = ensure_dir(os.path.join(cache_root, "symbol_rasters", _sanitize_path_component(family_name)))
    key_hash = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()[:16]
    return os.path.join(family_dir, "{}.json".format(key_hash))


def _retained_png_path(config, family_name, cache_key):
    cache_root = ensure_dir(config.get("cache_root", r"C:\temp\revit_detail_intelligence\cache"))
    png_root = ensure_dir(os.path.join(cache_root, "symbol_rasters_png", _sanitize_path_component(family_name)))
    key_hash = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()[:16]
    return os.path.join(png_root, "{}.png".format(key_hash))


def _read_cache_entry(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            return payload
    except Exception:
        return None
    return None


def _write_cache_entry(path, payload):
    try:
        ensure_dir(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except Exception as exc:
        warnings.warn(
            "DSE: failed to write symbol raster cache entry: {}".format(exc),
            RuntimeWarning,
            stacklevel=2,
        )


def _png_unfilter(raw_scanlines, width, height, bpp):
    stride = width * bpp
    rows = []
    pos = 0
    prev = [0] * stride
    for _ in range(height):
        filter_type = raw_scanlines[pos]
        pos += 1
        line = list(raw_scanlines[pos : pos + stride])
        pos += stride

        if filter_type == 0:
            pass
        elif filter_type == 1:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + left) & 0xFF
        elif filter_type == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif filter_type == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                up = prev[i]
                line[i] = (line[i] + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa = abs(p - a)
                pb = abs(p - b)
                pc = abs(p - c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        else:
            raise ValueError("Unsupported PNG filter type: {}".format(filter_type))

        rows.append(line)
        prev = line
    return rows


def _png_to_luminance(path):
    with open(path, "rb") as handle:
        blob = handle.read()
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a PNG file")

    width = height = bit_depth = color_type = None
    palette = None
    idat = bytearray()
    pos = 8
    while pos + 8 <= len(blob):
        length = struct.unpack("!I", blob[pos : pos + 4])[0]
        ctype = blob[pos + 4 : pos + 8]
        chunk_data = blob[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width, height, bit_depth, color_type, _, _, _ = struct.unpack("!IIBBBBB", chunk_data)
        elif ctype == b"PLTE":
            palette = chunk_data
        elif ctype == b"IDAT":
            idat.extend(chunk_data)
        elif ctype == b"IEND":
            break

    if width is None or height is None:
        raise ValueError("PNG missing IHDR")
    if bit_depth != 8:
        raise ValueError("Unsupported PNG bit depth: {}".format(bit_depth))

    bpp_map = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    if color_type not in bpp_map:
        raise ValueError("Unsupported PNG color type: {}".format(color_type))
    bpp = bpp_map[color_type]

    raw = zlib.decompress(bytes(idat))
    rows = _png_unfilter(raw, width, height, bpp)

    luminance = [0] * (width * height)
    idx = 0
    for row in rows:
        for col in range(width):
            if color_type == 0:
                lum = row[col]
            elif color_type == 2:
                i = col * 3
                r, g, b = row[i], row[i + 1], row[i + 2]
                lum = int(0.299 * r + 0.587 * g + 0.114 * b)
            elif color_type == 3:
                pal_idx = row[col] * 3
                if palette is None or pal_idx + 2 >= len(palette):
                    lum = 255
                else:
                    r, g, b = palette[pal_idx], palette[pal_idx + 1], palette[pal_idx + 2]
                    lum = int(0.299 * r + 0.587 * g + 0.114 * b)
            elif color_type == 4:
                i = col * 2
                lum = row[i]
            else:  # color_type == 6
                i = col * 4
                r, g, b = row[i], row[i + 1], row[i + 2]
                lum = int(0.299 * r + 0.587 * g + 0.114 * b)
            luminance[idx] = lum
            idx += 1

    return width, height, luminance


def _edge_pixels(width, height, luminance):
    edges = []
    for row in range(height):
        for col in range(width):
            idx = row * width + col
            fg = luminance[idx] < 128
            if not fg:
                continue
            is_edge = False
            for dc, dr in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nc = col + dc
                nr = row + dr
                if nc < 0 or nr < 0 or nc >= width or nr >= height:
                    is_edge = True
                    break
                nidx = nr * width + nc
                if luminance[nidx] >= 128:
                    is_edge = True
                    break
            if is_edge:
                edges.append((col, row))
    return edges


def _subsample_points(points, max_points):
    if max_points <= 0 or len(points) <= max_points:
        return points
    step = int(math.ceil(float(len(points)) / float(max_points)))
    return points[:: max(1, step)]


def _translate_points(points_xy, placement_point):
    px, py = float(placement_point[0]), float(placement_point[1])
    out = []
    for xy in points_xy or []:
        try:
            out.append([float(xy[0]) + px, float(xy[1]) + py])
        except Exception:
            continue
    return out


def _dpi_enum_for_value(target_dpi):
    try:
        import clr

        clr.AddReference("RevitAPI")
        from Autodesk.Revit.DB import ImageResolution

        allowed = [72, 150, 300, 600]
        nearest = min(allowed, key=lambda v: abs(v - int(target_dpi)))
        name = "DPI_{}".format(nearest)
        return getattr(ImageResolution, name, ImageResolution.DPI_150)
    except Exception:
        return None


def _export_temp_view_png(doc, tmp_view, dpi):
    try:
        import clr

        clr.AddReference("RevitAPI")
        from Autodesk.Revit.DB import ExportRange, ImageExportOptions, ImageFileType
    except Exception as exc:
        raise RuntimeError("RevitAPI import unavailable: {}".format(exc)) from exc

    tmp_dir = tempfile.mkdtemp(prefix="dse_symbol_raster_")
    stem = "sym_{}_{}".format(int(tmp_view.Id.IntegerValue), os.getpid())
    file_stem_path = os.path.join(tmp_dir, stem)

    opts = ImageExportOptions()
    opts.ExportRange = ExportRange.SetOfViews
    opts.HLRandWFViewsFileType = ImageFileType.PNG
    opts.ShadowViewsFileType = ImageFileType.PNG
    if hasattr(opts, "FilePath"):
        opts.FilePath = file_stem_path
    if hasattr(opts, "OutputFileName"):
        opts.OutputFileName = file_stem_path
    dpi_enum = _dpi_enum_for_value(dpi)
    if dpi_enum is not None and hasattr(opts, "ImageResolution"):
        opts.ImageResolution = dpi_enum
    if hasattr(opts, "SetViewsAndSheets"):
        opts.SetViewsAndSheets([tmp_view.Id])
    elif hasattr(opts, "ViewName"):
        opts.ViewName = tmp_view.Name

    doc.ExportImage(opts)
    tmp_listing = os.listdir(tmp_dir)
    warnings.warn(
        "DSE: symbol raster export tmp_dir listing after export: tmp_dir={} files={}".format(
            tmp_dir, tmp_listing
        ),
        RuntimeWarning,
        stacklevel=2,
    )
    _write_diag_json("post_export_tmp_dir_listing", {"tmp_dir": tmp_dir, "files": tmp_listing})

    candidates = []
    try:
        resolved = opts.GetFileName(doc, tmp_view.Id)
        if resolved:
            candidates.append(resolved)
            warnings.warn(
                "DSE: symbol raster lookup GetFileName path={} exists={}".format(
                    resolved, os.path.exists(resolved)
                ),
                RuntimeWarning,
                stacklevel=2,
            )
            _write_diag_json(
                "lookup_getfilename",
                {"path": resolved, "exists": bool(os.path.exists(resolved)), "tmp_dir": tmp_dir},
            )
        else:
            warnings.warn(
                "DSE: symbol raster lookup GetFileName returned empty value",
                RuntimeWarning,
                stacklevel=2,
            )
            _write_diag_json("lookup_getfilename_empty", {"tmp_dir": tmp_dir})
    except Exception:
        warnings.warn(
            "DSE: symbol raster lookup GetFileName raised exception",
            RuntimeWarning,
            stacklevel=2,
        )
        _write_diag_json("lookup_getfilename_exception", {"tmp_dir": tmp_dir})
    stem_png = file_stem_path + ".png"
    candidates.append(stem_png)
    warnings.warn(
        "DSE: symbol raster lookup stem path={} exists={}".format(stem_png, os.path.exists(stem_png)),
        RuntimeWarning,
        stacklevel=2,
    )
    _write_diag_json("lookup_stem_png", {"path": stem_png, "exists": bool(os.path.exists(stem_png))})

    for name in os.listdir(tmp_dir):
        if name.lower().endswith(".png"):
            listed = os.path.join(tmp_dir, name)
            candidates.append(listed)
            warnings.warn(
                "DSE: symbol raster lookup listdir path={} exists={}".format(
                    listed, os.path.exists(listed)
                ),
                RuntimeWarning,
                stacklevel=2,
            )
            _write_diag_json("lookup_listdir_png", {"path": listed, "exists": bool(os.path.exists(listed))})

    for cand in candidates:
        if cand and os.path.exists(cand):
            size_bytes = os.path.getsize(cand)
            with open(cand, "rb") as handle:
                head = handle.read(8)
            head_hex = " ".join("{:02X}".format(b) for b in head)
            warnings.warn(
                "DSE: symbol raster resolved export path={} size_bytes={} head8_hex={}".format(
                    cand, size_bytes, head_hex
                ),
                RuntimeWarning,
                stacklevel=2,
            )
            _write_diag_json(
                "resolved_export_png",
                {"path": cand, "size_bytes": int(size_bytes), "head8_hex": head_hex, "tmp_dir": tmp_dir},
            )
            return cand, tmp_dir
    warnings.warn(
        "DSE symbol raster: export file not found tmp_dir={}, view_id={}, stem={}".format(
            tmp_dir, int(tmp_view.Id.IntegerValue), stem
        ),
        RuntimeWarning,
        stacklevel=2,
    )
    _write_diag_json(
        "export_file_not_found",
        {"tmp_dir": tmp_dir, "view_id": int(tmp_view.Id.IntegerValue), "stem": stem},
    )
    return None, tmp_dir


def _cleanup_export_tmp_dir(tmp_dir):
    if not tmp_dir:
        return
    try:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass


def _start_transaction(doc, name):
    import clr

    clr.AddReference("RevitAPI")
    from Autodesk.Revit.DB import Transaction

    tx = Transaction(doc, name)
    tx.Start()
    return tx


class scoped_transaction:
    def __init__(self, doc, name):
        self._tx = _start_transaction(doc, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._tx.Commit()
            return False
        try:
            self._tx.RollBack()
        except Exception:
            pass
        return False


def _get_drafting_view_family_type_id(doc):
    import clr

    clr.AddReference("RevitAPI")
    from Autodesk.Revit.DB import (
        ElementClassFilter,
        FilteredElementCollector,
        ViewFamily,
        ViewFamilyType,
    )

    collector = FilteredElementCollector(doc).WherePasses(ElementClassFilter(ViewFamilyType))
    for view_family_type in collector:
        if getattr(view_family_type, "ViewFamily", None) == ViewFamily.Drafting:
            return view_family_type.Id
    return None


def _create_fresh_view_with_symbol(doc, view, element, obb_width=0.0, obb_height=0.0):
    tmp_view = None
    tmp_inst = None
    symbol = None
    try:
        import clr

        clr.AddReference("RevitAPI")
        from Autodesk.Revit.DB import BoundingBoxXYZ, ViewDrafting, XYZ

        drafting_vft_id = _get_drafting_view_family_type_id(doc)
        if drafting_vft_id is None:
            return None

        symbol = getattr(element, "Symbol", None)
        if symbol is None:
            try:
                type_id = element.GetTypeId()
                if type_id is not None:
                    symbol = doc.GetElement(type_id)
            except Exception:
                pass
        if symbol is None:
            _write_diag_json(
                "symbol_unresolvable",
                {
                    "element_id": _safe_int_element_id(element),
                    "element_class": type(element).__name__,
                    "category": str(getattr(getattr(element, "Category", None), "Name", "unknown")),
                },
            )
            return None

        with scoped_transaction(doc, "DSE: create fresh view for symbol raster"):
            tmp_view = ViewDrafting.Create(doc, drafting_vft_id)
            tmp_view.Scale = view.Scale
            if not symbol.IsActive:
                symbol.Activate()
            try:
                tmp_inst = doc.Create.NewFamilyInstance(XYZ(0, 0, 0), symbol, tmp_view)
            except Exception:
                # Fall back to curve overload for line-based families.
                # Project the element's world-space BasisX onto the source view's RightDirection
                # and UpDirection axes so the driving line is view-relative, not a raw XY world
                # projection. This handles section/elevation views where the driving direction
                # has a significant Z component that the plain bx.X/bx.Y path would drop.
                from Autodesk.Revit.DB import Line

                length_ft = max(obb_width, obb_height)
                length_ft = max(length_ft, 1.0 / 12.0)  # minimum 1 inch
                dx, dy = 1.0, 0.0
                try:
                    tx = element.GetTotalTransform()
                    bx = tx.BasisX
                    right = view.RightDirection
                    up = view.UpDirection
                    raw_dx = (
                        float(bx.X) * float(right.X)
                        + float(bx.Y) * float(right.Y)
                        + float(bx.Z) * float(right.Z)
                    )
                    raw_dy = (
                        float(bx.X) * float(up.X)
                        + float(bx.Y) * float(up.Y)
                        + float(bx.Z) * float(up.Z)
                    )
                    norm = math.sqrt(raw_dx * raw_dx + raw_dy * raw_dy)
                    if norm > 1e-9:
                        dx, dy = raw_dx / norm, raw_dy / norm
                except Exception:
                    pass
                end_pt = XYZ(dx * length_ft, dy * length_ft, 0.0)
                line = Line.CreateBound(XYZ(0, 0, 0), end_pt)
                tmp_inst = doc.Create.NewFamilyInstance(line, symbol, tmp_view)
                _write_diag_json(
                    "curve_overload_used",
                    {
                        "element_id": _safe_int_element_id(element),
                        "length_ft": length_ft,
                        "dx": dx,
                        "dy": dy,
                        "family_name": str(getattr(getattr(symbol, "Family", None), "Name", "unknown")),
                    },
                )
            doc.Regenerate()

        bb = tmp_inst.get_BoundingBox(tmp_view)
        if bb is None:
            return tmp_view

        with scoped_transaction(doc, "DSE: set crop for symbol raster"):
            width = float(bb.Max.X - bb.Min.X)
            height = float(bb.Max.Y - bb.Min.Y)
            pad = max(width, height) * 0.25
            pad = max(pad, 0.1)
            expanded_bbox = BoundingBoxXYZ()
            expanded_bbox.Min = XYZ(bb.Min.X - pad, bb.Min.Y - pad, bb.Min.Z)
            expanded_bbox.Max = XYZ(bb.Max.X + pad, bb.Max.Y + pad, bb.Max.Z)
            tmp_view.CropBoxActive = True
            tmp_view.CropBoxVisible = False
            tmp_view.CropBox = expanded_bbox
            doc.Regenerate()

        return tmp_view
    except Exception as exc:
        family_name_diag = "unknown"
        symbol_name_diag = "unknown"
        try:
            family = getattr(symbol, "Family", None)
            pt = str(getattr(family, "FamilyPlacementType", "unknown")) if family else "no_family"
            family_name_diag = str(getattr(family, "Name", "unknown")) if family else "no_family"
            symbol_name_diag = str(getattr(symbol, "Name", "unknown")) if symbol is not None else "no_symbol"
        except Exception:
            pt = "error_reading"
        _write_diag_json(
            "fresh_view_create_failed",
            {
                "reason": str(exc),
                "type": type(exc).__name__,
                "family_placement_type": str(pt),
                "family_name": family_name_diag,
                "symbol_name": symbol_name_diag,
                "element_class": type(element).__name__,
                "element_category": str(getattr(getattr(element, "Category", None), "Name", "unknown")),
            },
        )
        if tmp_view is not None:
            try:
                with scoped_transaction(doc, "DSE: cleanup failed symbol raster view"):
                    doc.Delete(tmp_view.Id)
            except Exception:
                pass
        return None


def _delete_temp_view(doc, tmp_view):
    if tmp_view is None:
        return
    try:
        tx_del = _start_transaction(doc, "DSE: delete temp view")
        try:
            doc.Delete(tmp_view.Id)
            tx_del.Commit()
        except Exception:
            try:
                tx_del.RollBack()
            except Exception:
                pass
    except Exception:
        pass


def _collect_points_for_element(view, doc, element, config):
    elem_id = _safe_int_element_id(element)
    family_name, _ = _safe_type_sig_parts(element)

    transform = None
    bbox = None
    try:
        transform = element.GetTotalTransform()
        bbox = element.get_BoundingBox(view)
    except Exception as exc:
        warnings.warn(
            "DSE: symbol raster OBB failure for element {} ({}) : {}".format(elem_id, family_name, exc),
            RuntimeWarning,
            stacklevel=2,
        )
        return None, None

    if transform is None or bbox is None:
        return None, None

    placement_point = to_view_local_2d([transform.Origin], view)[0]
    obb_width = abs(float(bbox.Max.X - bbox.Min.X))
    obb_height = abs(float(bbox.Max.Y - bbox.Min.Y))

    try:
        (
            cache_key,
            family_name,
            _type_name,
            view_scale,
            detail_level,
            orientation_bucket,
            doc_scope,
            length_bucket_in,
        ) = _symbol_cache_key(element, view, obb_width=obb_width, obb_height=obb_height)
    except Exception as exc:
        warnings.warn(
            "DSE: symbol raster key failure for element {} ({}) : {}".format(elem_id, family_name, exc),
            RuntimeWarning,
            stacklevel=2,
        )
        return None, None

    cache_path = _cache_file_path(config, family_name, cache_key)
    cached = _read_cache_entry(cache_path)
    if isinstance(cached, dict) and "points" in cached:
        return elem_id, _translate_points(cached.get("points") or [], placement_point)

    if obb_width <= 0.0 or obb_height <= 0.0:
        entry = {
            "cache_schema": "symbol_raster.v1",
            "cache_key": cache_key,
            "family_name": family_name,
            "view_scale": view_scale,
            "detail_level": detail_level,
            "orientation_bucket": orientation_bucket,
            "length_bucket_in": length_bucket_in,
            "doc_scope": doc_scope,
            "obb_width": obb_width,
            "obb_height": obb_height,
            "points": [],
            "build_time_utc": datetime.now(timezone.utc).isoformat(),
        }
        _write_cache_entry(cache_path, entry)
        return elem_id, []

    pad = max(obb_width, obb_height) * 0.25
    pad = max(pad, 0.1)
    raster_world_width = obb_width + (2.0 * pad)
    raster_world_height = obb_height + (2.0 * pad)

    tmp_view = None
    png_path = None
    retained_png_path = None
    export_tmp_dir = None
    try:
        tmp_view = _create_fresh_view_with_symbol(doc, view, element, obb_width=obb_width, obb_height=obb_height)
        _write_diag_json(
            "fresh_view_created",
            {
                "tmp_view_is_none": tmp_view is None,
                "tmp_view_id": _safe_int_element_id(tmp_view) if tmp_view is not None else None,
            },
        )
        if tmp_view is None:
            raise RuntimeError("failed to duplicate/isolate temporary view")
        dpi = int(config.get("symbol_raster_dpi", 150))
        png_path, export_tmp_dir = _export_temp_view_png(doc, tmp_view, dpi)
        if png_path and os.path.exists(png_path):
            retained_png_path = _retained_png_path(config, family_name, cache_key)
            with open(png_path, "rb") as src:
                blob = src.read()
            with open(retained_png_path, "wb") as dst:
                dst.write(blob)
            _write_diag_json(
                "retained_export_png",
                {"source": png_path, "retained": retained_png_path, "size_bytes": int(len(blob))},
            )
            png_path = retained_png_path
    except Exception as exc:
        warnings.warn(
            "DSE: symbol raster export failure for element {} ({}) : {}".format(elem_id, family_name, exc),
            RuntimeWarning,
            stacklevel=2,
        )
        _cleanup_export_tmp_dir(export_tmp_dir)
        return None, None
    finally:
        _delete_temp_view(doc, tmp_view)

    try:
        points_xy_rel = []
        if png_path and os.path.exists(png_path):
            try:
                img_width, img_height, lum = _png_to_luminance(png_path)
                edges = _edge_pixels(img_width, img_height, lum)
                for col, row in edges:
                    x_rel = ((float(col) / float(max(1, img_width))) - 0.5) * raster_world_width
                    y_rel = ((float(row) / float(max(1, img_height))) - 0.5) * raster_world_height
                    points_xy_rel.append([x_rel, y_rel])
            except Exception as exc:
                warnings.warn(
                    "DSE: symbol raster decode failure for element {} ({}) : {}".format(
                        elem_id, family_name, exc
                    ),
                    RuntimeWarning,
                    stacklevel=2,
                )
                return None, None

        points_xy_rel = _subsample_points(points_xy_rel, int(config.get("symbol_raster_max_points", 200)))
        points_xy = _translate_points(points_xy_rel, placement_point)

        entry = {
            "cache_schema": "symbol_raster.v1",
            "cache_key": cache_key,
            "family_name": family_name,
            "view_scale": view_scale,
            "detail_level": detail_level,
            "orientation_bucket": orientation_bucket,
            "length_bucket_in": length_bucket_in,
            "doc_scope": doc_scope,
            "obb_width": obb_width,
            "obb_height": obb_height,
            "points": points_xy_rel,
            "build_time_utc": datetime.now(timezone.utc).isoformat(),
        }
        _write_cache_entry(cache_path, entry)
        return elem_id, points_xy
    finally:
        _cleanup_export_tmp_dir(export_tmp_dir)


def collect_raster_points_for_view(view, doc=None, config=None):
    """Collect view-local raster edge points for FamilyInstance elements.

    Returns: {element_id_int: [[x, y], ...]}
    """

    out = {}
    config = config or {}
    doc = doc or getattr(view, "Document", None)
    if view is None or doc is None:
        return out

    try:
        elements = get_view_elements(view)
    except Exception as exc:
        warnings.warn(
            "DSE: symbol raster failed to read view elements: {}".format(exc),
            RuntimeWarning,
            stacklevel=2,
        )
        return out

    for element in elements:
        try:
            if not is_family_instance(element):
                continue
            elem_id, points = _collect_points_for_element(view, doc, element, config)
            if elem_id is None:
                continue
            out[int(elem_id)] = points or []
        except Exception as exc:
            elem_id = _safe_int_element_id(element)
            fam_name, _ = _safe_type_sig_parts(element)
            warnings.warn(
                "DSE: symbol raster unexpected failure for element {} ({}) : {}".format(elem_id, fam_name, exc),
                RuntimeWarning,
                stacklevel=2,
            )
            continue

    return out
