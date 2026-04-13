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


def _symbol_cache_key(element, view):
    family_name, type_name = _safe_type_sig_parts(element)
    view_scale = int(round(float(getattr(view, "Scale", 1))))
    transform = element.GetTotalTransform()
    orientation_bucket = _orientation_bucket_from_transform(transform)
    key = "{}|{}|{}|{}".format(family_name, type_name, view_scale, orientation_bucket)
    return key, family_name, type_name, view_scale, orientation_bucket


def _cache_file_path(config, family_name, cache_key):
    cache_root = ensure_dir(config.get("cache_root", r"C:\temp\revit_detail_intelligence\cache"))
    family_dir = ensure_dir(os.path.join(cache_root, "symbol_rasters", _sanitize_path_component(family_name)))
    key_hash = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()[:16]
    return os.path.join(family_dir, "{}.json".format(key_hash))


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
    opts.SetViewsAndSheets([tmp_view.Id])

    doc.ExportImage(opts)

    candidates = []
    try:
        resolved = opts.GetFileName(doc, tmp_view.Id)
        if resolved:
            candidates.append(resolved)
    except Exception:
        pass
    candidates.append(file_stem_path + ".png")

    for name in os.listdir(tmp_dir):
        if name.lower().endswith(".png"):
            candidates.append(os.path.join(tmp_dir, name))

    for cand in candidates:
        if cand and os.path.exists(cand):
            return cand
    return None


def _start_transaction(doc, name):
    import clr

    clr.AddReference("RevitAPI")
    from Autodesk.Revit.DB import Transaction

    tx = Transaction(doc, name)
    tx.Start()
    return tx


def _duplicate_and_isolate_view(doc, view, element):
    tmp_view = None
    try:
        import clr

        clr.AddReference("RevitAPI")
        from Autodesk.Revit.DB import ViewDuplicateOption

        tx_dup = _start_transaction(doc, "DSE: duplicate view for symbol raster")
        try:
            tmp_id = view.Duplicate(ViewDuplicateOption.Duplicate)
            tmp_view = doc.GetElement(tmp_id)
            tmp_view.Scale = view.Scale
            tx_dup.Commit()
        except Exception:
            try:
                tx_dup.RollBack()
            except Exception:
                pass
            raise

        tx_iso = _start_transaction(doc, "DSE: isolate element for symbol raster")
        try:
            tmp_view.IsolateElementTemporary(element.Id)
            tx_iso.Commit()
        except Exception:
            try:
                tx_iso.RollBack()
            except Exception:
                pass
            raise

        return tmp_view
    except Exception:
        return tmp_view


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
    try:
        cache_key, family_name, _type_name, view_scale, orientation_bucket = _symbol_cache_key(element, view)
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
        return elem_id, cached.get("points") or []

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

    obb_width = abs(float(bbox.Max.X - bbox.Min.X))
    obb_height = abs(float(bbox.Max.Y - bbox.Min.Y))
    if obb_width <= 0.0 or obb_height <= 0.0:
        entry = {
            "cache_schema": "symbol_raster.v1",
            "cache_key": cache_key,
            "family_name": family_name,
            "view_scale": view_scale,
            "orientation_bucket": orientation_bucket,
            "obb_width": obb_width,
            "obb_height": obb_height,
            "points": [],
            "build_time_utc": datetime.now(timezone.utc).isoformat(),
        }
        _write_cache_entry(cache_path, entry)
        return elem_id, []

    placement_point = to_view_local_2d([transform.Origin], view)[0]

    tmp_view = None
    png_path = None
    try:
        tmp_view = _duplicate_and_isolate_view(doc, view, element)
        if tmp_view is None:
            raise RuntimeError("failed to duplicate/isolate temporary view")
        dpi = int(config.get("symbol_raster_dpi", 150))
        png_path = _export_temp_view_png(doc, tmp_view, dpi)
    except Exception as exc:
        warnings.warn(
            "DSE: symbol raster export failure for element {} ({}) : {}".format(elem_id, family_name, exc),
            RuntimeWarning,
            stacklevel=2,
        )
        return None, None
    finally:
        _delete_temp_view(doc, tmp_view)

    points_xy = []
    if png_path and os.path.exists(png_path):
        try:
            img_width, img_height, lum = _png_to_luminance(png_path)
            edges = _edge_pixels(img_width, img_height, lum)
            for col, row in edges:
                x_local = placement_point[0] + ((float(col) / float(max(1, img_width))) - 0.5) * obb_width
                y_local = placement_point[1] + ((float(row) / float(max(1, img_height))) - 0.5) * obb_height
                points_xy.append([x_local, y_local])
        except Exception as exc:
            warnings.warn(
                "DSE: symbol raster decode failure for element {} ({}) : {}".format(elem_id, family_name, exc),
                RuntimeWarning,
                stacklevel=2,
            )
            return None, None

    points_xy = _subsample_points(points_xy, int(config.get("symbol_raster_max_points", 200)))

    entry = {
        "cache_schema": "symbol_raster.v1",
        "cache_key": cache_key,
        "family_name": family_name,
        "view_scale": view_scale,
        "orientation_bucket": orientation_bucket,
        "obb_width": obb_width,
        "obb_height": obb_height,
        "points": points_xy,
        "build_time_utc": datetime.now(timezone.utc).isoformat(),
    }
    _write_cache_entry(cache_path, entry)
    return elem_id, points_xy


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
