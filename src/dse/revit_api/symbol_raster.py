import hashlib
import json
import math
import os
import random
import re
import struct
import tempfile
import time
import warnings
import zlib
from datetime import datetime, timezone

from dse.features.tokens import type_signature
from dse.io_paths import ensure_dir
from dse.revit_api.collect import get_view_elements, is_family_instance
from dse.revit_api.geometry_2d import to_view_local_2d

_SYMBOL_RASTER_PIPELINE_VERSION = "symbol_raster.pipeline.v5"
_CANONICAL_LINE_LENGTH_FT = 1.0  # 12 inches
_RUN_MEMORY_SYMBOL_RASTER_CACHE = {}
_RUN_DOCUMENT_LOOKUP_CACHE = {
    "drafting_view_family_type_id": {},
    "stats": {"drafting_lookup_hits": 0, "drafting_lookup_misses": 0},
}


def _emit_lookup_diagnostic(callback, payload):
    if callback is None:
        return
    try:
        callback(payload)
    except Exception:
        return


def _write_diag_json(_event, _payload):
    return


def _flush_diag_json_buffer():
    return


def _memory_cache_get(cache_key):
    payload = _RUN_MEMORY_SYMBOL_RASTER_CACHE.get(str(cache_key))
    if payload is None:
        return None
    try:
        return [[pt[0], pt[1]] for pt in payload]
    except Exception:
        return None


def _memory_cache_set(cache_key, canonical_points):
    if not isinstance(canonical_points, list):
        return
    frozen_points = []
    for pt in canonical_points:
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            return
        if not _is_numeric(pt[0]) or not _is_numeric(pt[1]):
            return
        frozen_points.append((pt[0], pt[1]))
    _RUN_MEMORY_SYMBOL_RASTER_CACHE[str(cache_key)] = tuple(frozen_points)


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


def _extract_type_id_int(element):
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
    return type_id_int


def _is_line_based_family_instance(element):
    if getattr(element, "Symbol", None) is None:
        return True
    try:
        placement_type = str(getattr(getattr(element.Symbol, "Family", None), "FamilyPlacementType", ""))
    except Exception:
        placement_type = ""
    placement_type = placement_type.lower()
    return ("curve" in placement_type) or ("line" in placement_type)


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


def _document_cache_key(doc):
    doc_identity = _document_identity(doc)
    try:
        doc_hash = int(doc.GetHashCode())
    except Exception:
        doc_hash = None
    return "{}|{}".format(doc_identity, doc_hash)


def _increment_doc_lookup_stat(name):
    stats = _RUN_DOCUMENT_LOOKUP_CACHE.setdefault("stats", {})
    stats[name] = int(stats.get(name, 0)) + 1


def _document_lookup_debug_snapshot():
    stats = _RUN_DOCUMENT_LOOKUP_CACHE.get("stats", {})
    return {str(k): int(v) for k, v in dict(stats).items()}


def _symbol_cache_key(element, view, obb_width=0.0, obb_height=0.0):
    family_name, type_name = _safe_type_sig_parts(element)
    view_scale = int(round(float(getattr(view, "Scale", 1))))
    detail_level = str(int(view.DetailLevel))
    doc_identity = _document_identity(getattr(view, "Document", None))
    doc_scope = hashlib.sha1(doc_identity.encode("utf-8")).hexdigest()[:12]
    is_line_based = _is_line_based_family_instance(element)
    # Stable type-id disambiguates Symbol-less instances (line-based families resolved via
    # GetTypeId) that share a placeholder family name, preventing cross-family cache collisions.
    type_id_int = _extract_type_id_int(element)
    # Canonical cache key is type-local and intentionally excludes observed pose/length
    # fields such as orientation buckets and instance-length buckets.
    key = "{}|{}|{}|{}|{}|line{}|tid{}".format(
        doc_scope, family_name, type_name, view_scale, detail_level, int(bool(is_line_based)), type_id_int
    )
    return (
        key,
        family_name,
        type_name,
        view_scale,
        detail_level,
        is_line_based,
        doc_scope,
        type_id_int,
    )


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


def _retain_debug_artifacts_enabled(config):
    value = config.get("symbol_raster_retain_debug_artifacts", False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _read_cache_entry(path):
    if not os.path.exists(path):
        return None, "file not found"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            return payload, None
        return None, "wrong schema"
    except Exception:
        return None, "parse error"


def _cache_lookup_diag_payload(
    cache_key,
    cache_path,
    doc_scope,
    family_name,
    type_name,
    type_id_int,
    view_scale,
    detail_level,
    is_line_based,
):
    return {
        "cache_key": cache_key,
        "cache_path": cache_path,
        "doc_scope": doc_scope,
        "family_name": family_name,
        "type_name": type_name,
        "type_id_int": int(type_id_int),
        "view_scale": int(view_scale),
        "detail_level": str(detail_level),
        "is_line_based_lookup": bool(is_line_based),
    }


def _is_numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_points_payload_valid(points):
    if not isinstance(points, list):
        return False
    for pt in points:
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            return False
        if not _is_numeric(pt[0]) or not _is_numeric(pt[1]):
            return False
    return True


def _validate_cache_entry(cached, expected):
    if not isinstance(cached, dict):
        return None, "wrong schema"
    if cached.get("cache_schema") != "symbol_raster.v1":
        return None, "wrong schema"
    if cached.get("pipeline_version") != _SYMBOL_RASTER_PIPELINE_VERSION:
        return None, "version mismatch"

    required_fields = (
        "cache_key",
        "doc_scope",
        "family_name",
        "view_scale",
        "detail_level",
        "is_line_based",
        "obb_width",
        "obb_height",
        "points",
    )
    missing = [name for name in required_fields if name not in cached]
    if missing:
        return None, "missing required fields"

    for name in (
        "cache_key",
        "doc_scope",
        "family_name",
        "view_scale",
        "detail_level",
        "is_line_based",
    ):
        if cached.get(name) != expected.get(name):
            return None, "missing required fields"
    if not _is_numeric(cached.get("obb_width")) or not _is_numeric(cached.get("obb_height")):
        return None, "missing required fields"

    points = cached.get("points")
    if not _is_points_payload_valid(points):
        return None, "invalid points payload"
    return points, None


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


def _foreground_edge_pixels(binary_image):
    height = len(binary_image)
    if height <= 0:
        return []
    width = len(binary_image[0]) if binary_image[0] is not None else 0
    edges = []
    for row in range(height):
        for col in range(width):
            if not binary_image[row][col]:
                continue
            for dc, dr in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nc = col + dc
                nr = row + dr
                if nc < 0 or nr < 0 or nc >= width or nr >= height or not binary_image[nr][nc]:
                    edges.append((col, row))
                    break
    return edges


def _edge_pixels(width, height, luminance):
    binary = []
    for row in range(height):
        start = row * width
        row_pixels = []
        for col in range(width):
            row_pixels.append(luminance[start + col] < 128)
        binary.append(row_pixels)
    return _foreground_edge_pixels(binary)


def _component_angular_subsample(points, max_points=8):
    if not points:
        return []
    if len(points) <= max_points:
        return list(points)
    cx = sum(float(p[0]) for p in points) / float(len(points))
    cy = sum(float(p[1]) for p in points) / float(len(points))
    rows = []
    for x, y in points:
        rows.append((math.atan2(float(y) - cy, float(x) - cx), x, y))
    rows.sort(key=lambda r: r[0])
    out = []
    step = float(len(rows)) / float(max_points)
    for i in range(max_points):
        idx = int(round(i * step))
        idx = min(max(idx, 0), len(rows) - 1)
        out.append((rows[idx][1], rows[idx][2]))
    return out


def _hough_endpoints(binary_image, min_length_px=3):
    height = len(binary_image)
    if height <= 0:
        return [], 0
    width = len(binary_image[0]) if binary_image[0] is not None else 0
    if width <= 0:
        return [], 0

    edge_pixels = _foreground_edge_pixels(binary_image)
    if not edge_pixels:
        return [], 0

    rng = random.Random(0)
    sampled = list(edge_pixels)
    rng.shuffle(sampled)
    sampled = sampled[: max(128, min(len(sampled), 2048))]

    theta_count = 90
    thetas = []
    for i in range(theta_count):
        theta = (math.pi * float(i)) / float(theta_count)
        thetas.append((math.cos(theta), math.sin(theta)))

    votes = {}
    for col, row in sampled:
        x = float(col)
        y = float(row)
        for theta_idx, (ct, st) in enumerate(thetas):
            rho_bin = int(round(((x * ct) + (y * st))))
            key = (theta_idx, rho_bin)
            votes[key] = votes.get(key, 0) + 1
    if not votes:
        return [], 0

    sorted_bins = sorted(votes.items(), key=lambda kv: kv[1], reverse=True)
    covered = set()
    endpoints = []
    segment_count = 0
    for (theta_idx, rho_bin), _score in sorted_bins[: min(64, len(sorted_bins))]:
        ct, st = thetas[theta_idx]
        rho = float(rho_bin)
        inliers = []
        for pix_idx, (col, row) in enumerate(edge_pixels):
            if pix_idx in covered:
                continue
            dist = abs((float(col) * ct) + (float(row) * st) - rho)
            if dist <= 1.0:
                proj = (float(col) * (-st)) + (float(row) * ct)
                inliers.append((proj, col, row, pix_idx))
        if len(inliers) < 2:
            continue
        inliers.sort(key=lambda r: r[0])

        runs = []
        run = [inliers[0]]
        for item in inliers[1:]:
            if abs(item[0] - run[-1][0]) <= 2.5:
                run.append(item)
            else:
                if len(run) >= 2:
                    runs.append(run)
                run = [item]
        if len(run) >= 2:
            runs.append(run)

        for seg in runs:
            p0 = seg[0]
            p1 = seg[-1]
            length = math.hypot(float(p1[1]) - float(p0[1]), float(p1[2]) - float(p0[2]))
            if length < float(min_length_px):
                continue
            endpoints.append((int(p0[1]), int(p0[2])))
            endpoints.append((int(p1[1]), int(p1[2])))
            segment_count += 1
            for row in seg:
                covered.add(row[3])

    remaining_map = {}
    for pix_idx, point in enumerate(edge_pixels):
        if pix_idx not in covered:
            remaining_map[pix_idx] = point
    if not remaining_map:
        return endpoints, segment_count

    point_to_idx = {}
    for pix_idx, (col, row) in remaining_map.items():
        point_to_idx[(col, row)] = pix_idx

    visited = set()
    for seed_idx in list(remaining_map.keys()):
        if seed_idx in visited:
            continue
        stack = [seed_idx]
        visited.add(seed_idx)
        component = []
        while stack:
            current = stack.pop()
            cx, cy = remaining_map[current]
            component.append((cx, cy))
            for dc in (-1, 0, 1):
                for dr in (-1, 0, 1):
                    if dc == 0 and dr == 0:
                        continue
                    neighbor_idx = point_to_idx.get((cx + dc, cy + dr))
                    if neighbor_idx is None or neighbor_idx in visited:
                        continue
                    visited.add(neighbor_idx)
                    stack.append(neighbor_idx)
        endpoints.extend(_component_angular_subsample(component, max_points=8))

    return endpoints, segment_count


def _instance_pose_in_view_2d(transform, view):
    origin_xy = to_view_local_2d([transform.Origin], view)[0]
    right = view.RightDirection
    up = view.UpDirection
    bx = transform.BasisX
    raw_dx = float(bx.X) * float(right.X) + float(bx.Y) * float(right.Y) + float(bx.Z) * float(right.Z)
    raw_dy = float(bx.X) * float(up.X) + float(bx.Y) * float(up.Y) + float(bx.Z) * float(up.Z)
    mag = math.hypot(raw_dx, raw_dy)
    if mag <= 1e-9:
        dx, dy = 1.0, 0.0
    else:
        dx, dy = raw_dx / mag, raw_dy / mag
    mirrored = bool(float(getattr(transform, "Determinant", 1.0)) < 0.0)
    angle_deg = math.degrees(math.atan2(dy, dx))
    return origin_xy, (dx, dy), mirrored, angle_deg


def _actual_instance_length_ft(element, obb_width=0.0, obb_height=0.0):
    try:
        location = getattr(element, "Location", None)
        curve = getattr(location, "Curve", None)
        if curve is not None:
            length = float(getattr(curve, "Length", 0.0))
            if length > 1e-9:
                return length
    except Exception:
        pass
    return max(float(obb_width), float(obb_height), 1e-9)


def _build_symbol_instance_context(view, element):
    elem_id = _safe_int_element_id(element)
    family_name, _ = _safe_type_sig_parts(element)
    try:
        transform = element.GetTotalTransform()
        bbox = element.get_BoundingBox(view)
    except Exception as exc:
        warnings.warn(
            "DSE: symbol raster OBB failure for element {} ({}) : {}".format(elem_id, family_name, exc),
            RuntimeWarning,
            stacklevel=2,
        )
        return None

    if transform is None or bbox is None:
        return None

    placement_point, axis_x, is_mirrored, rotation_deg = _instance_pose_in_view_2d(transform, view)
    obb_width = abs(float(bbox.Max.X - bbox.Min.X))
    obb_height = abs(float(bbox.Max.Y - bbox.Min.Y))
    try:
        (
            cache_key,
            family_name,
            type_name,
            view_scale,
            detail_level,
            is_line_based,
            doc_scope,
            type_id_int,
        ) = _symbol_cache_key(element, view, obb_width=obb_width, obb_height=obb_height)
    except Exception as exc:
        warnings.warn(
            "DSE: symbol raster key failure for element {} ({}) : {}".format(elem_id, family_name, exc),
            RuntimeWarning,
            stacklevel=2,
        )
        return None

    actual_length_ft = _actual_instance_length_ft(element, obb_width=obb_width, obb_height=obb_height)
    length_scale_x = (actual_length_ft / _CANONICAL_LINE_LENGTH_FT) if is_line_based else 1.0
    return {
        "elem_id": elem_id,
        "family_name": family_name,
        "type_name": type_name,
        "cache_key": cache_key,
        "view_scale": view_scale,
        "detail_level": detail_level,
        "is_line_based": is_line_based,
        "doc_scope": doc_scope,
        "type_id_int": type_id_int,
        "obb_width": obb_width,
        "obb_height": obb_height,
        "placement_point": placement_point,
        "axis_x": axis_x,
        "is_mirrored": is_mirrored,
        "rotation_deg": rotation_deg,
        "length_scale_x": length_scale_x,
    }


def _collect_canonical_points_for_context(
    view,
    doc,
    element,
    context,
    config,
    diagnostic_callback=None,
):
    lookup_start = time.perf_counter()
    cache_key = context["cache_key"]
    family_name = context["family_name"]
    type_name = context["type_name"]
    view_scale = context["view_scale"]
    detail_level = context["detail_level"]
    is_line_based = context["is_line_based"]
    doc_scope = context["doc_scope"]
    obb_width = context["obb_width"]
    obb_height = context["obb_height"]
    obb_paper_width_inches = _obb_paper_inches(obb_width, view_scale)
    obb_paper_height_inches = _obb_paper_inches(obb_height, view_scale)
    px_w, px_h = _export_pixel_size_from_obb_paper_inches(obb_paper_width_inches, obb_paper_height_inches)
    symbol_type_key = "{}|{}".format(family_name, type_name)
    cache_path = _cache_file_path(config, family_name, cache_key)
    in_memory_points = _memory_cache_get(cache_key)
    if in_memory_points is not None:
        _emit_lookup_diagnostic(
            diagnostic_callback,
            {
                "symbol_type_key": symbol_type_key,
                "cache_hit": True,
                "cache_layer": "memory",
                "miss_reason": None,
                "elapsed_ms": (time.perf_counter() - lookup_start) * 1000.0,
            },
        )
        return in_memory_points

    cached, miss_reason = _read_cache_entry(cache_path)
    expected_entry = {
        "cache_key": cache_key,
        "doc_scope": doc_scope,
        "family_name": family_name,
        "view_scale": view_scale,
        "detail_level": detail_level,
        "is_line_based": is_line_based,
    }
    if miss_reason is None:
        cached_points, miss_reason = _validate_cache_entry(cached, expected_entry)
        if miss_reason is None:
            _memory_cache_set(cache_key, cached_points)
            _emit_lookup_diagnostic(
                diagnostic_callback,
                {
                    "symbol_type_key": symbol_type_key,
                    "cache_hit": True,
                    "cache_layer": "disk",
                    "miss_reason": None,
                    "elapsed_ms": (time.perf_counter() - lookup_start) * 1000.0,
                },
            )
            return cached_points

    miss_reason = str(miss_reason or "unknown")
    if obb_width <= 0.0 or obb_height <= 0.0:
        entry = {
            "cache_schema": "symbol_raster.v1",
            "cache_key": cache_key,
            "family_name": family_name,
            "view_scale": view_scale,
            "detail_level": detail_level,
            "is_line_based": is_line_based,
            "doc_scope": doc_scope,
            "obb_width": obb_width,
            "obb_height": obb_height,
            "obb_paper_width_inches": obb_paper_width_inches,
            "obb_paper_height_inches": obb_paper_height_inches,
            "px_w": px_w,
            "px_h": px_h,
            "points": [],
            "hough_segment_count": 0,
            "endpoint_count": 0,
            "pipeline_version": _SYMBOL_RASTER_PIPELINE_VERSION,
            "build_time_utc": datetime.now(timezone.utc).isoformat(),
        }
        _write_cache_entry(cache_path, entry)
        _memory_cache_set(cache_key, entry["points"])
        _emit_lookup_diagnostic(
            diagnostic_callback,
            {
                "symbol_type_key": symbol_type_key,
                "cache_hit": False,
                "cache_layer": "rebuild",
                "miss_reason": miss_reason,
                "elapsed_ms": (time.perf_counter() - lookup_start) * 1000.0,
            },
        )
        return []

    tmp_view = None
    canonical_bounds = None
    png_path = None
    retained_png_path = None
    export_tmp_dir = None
    try:
        tmp_view_result = _create_fresh_view_with_symbol(
            doc,
            view,
            element,
            obb_width=obb_width,
            obb_height=obb_height,
            include_canonical_bounds=True,
        )
        if isinstance(tmp_view_result, tuple):
            tmp_view, canonical_bounds = tmp_view_result
        else:
            # Backward compatibility for test stubs that still return only a view-like object.
            tmp_view = tmp_view_result
        if tmp_view is None:
            raise RuntimeError("failed to duplicate/isolate temporary view")
        if is_line_based:
            resolved_bounds = canonical_bounds or {
                "min_x": 0.0,
                "max_x": float(_CANONICAL_LINE_LENGTH_FT),
                "min_y": -0.05 * float(_CANONICAL_LINE_LENGTH_FT),
                "max_y": 0.05 * float(_CANONICAL_LINE_LENGTH_FT),
            }
            canonical_width = max(float(resolved_bounds["max_x"]) - float(resolved_bounds["min_x"]), 1e-9)
            canonical_height = max(float(resolved_bounds["max_y"]) - float(resolved_bounds["min_y"]), 1e-9)
            canonical_paper_width_inches = _obb_paper_inches(canonical_width, view_scale)
            canonical_paper_height_inches = _obb_paper_inches(canonical_height, view_scale)
            px_w, px_h = _export_pixel_size_from_obb_paper_inches(
                canonical_paper_width_inches,
                canonical_paper_height_inches,
            )
        png_path, export_tmp_dir = _export_temp_view_png(doc, tmp_view, px_w, px_h)
        if png_path and os.path.exists(png_path) and _retain_debug_artifacts_enabled(config):
            retained_png_path = _retained_png_path(config, family_name, cache_key)
            with open(png_path, "rb") as src:
                blob = src.read()
            with open(retained_png_path, "wb") as dst:
                dst.write(blob)
            png_path = retained_png_path
    except Exception as exc:
        _emit_lookup_diagnostic(
            diagnostic_callback,
            {
                "symbol_type_key": symbol_type_key,
                "cache_hit": False,
                "miss_reason": "rebuild_export_failure: {}".format(exc),
                "elapsed_ms": (time.perf_counter() - lookup_start) * 1000.0,
            },
        )
        warnings.warn(
            "DSE: symbol raster export failure for element {} ({}) : {}".format(
                context.get("elem_id"), family_name, exc
            ),
            RuntimeWarning,
            stacklevel=2,
        )
        _cleanup_export_tmp_dir(export_tmp_dir)
        return None
    finally:
        _delete_temp_view(doc, tmp_view)

    try:
        if not canonical_bounds:
            if is_line_based:
                canonical_bounds = {
                    "min_x": 0.0,
                    "max_x": float(_CANONICAL_LINE_LENGTH_FT),
                    "min_y": -0.05 * float(_CANONICAL_LINE_LENGTH_FT),
                    "max_y": 0.05 * float(_CANONICAL_LINE_LENGTH_FT),
                }
            else:
                half_w = max(float(obb_width) * 0.5, 1.0 / 12.0)
                half_h = max(float(obb_height) * 0.5, 1.0 / 12.0)
                canonical_bounds = {
                    "min_x": -half_w,
                    "max_x": half_w,
                    "min_y": -half_h,
                    "max_y": half_h,
                }
        canonical_width = max(float(canonical_bounds["max_x"]) - float(canonical_bounds["min_x"]), 1e-9)
        canonical_height = max(float(canonical_bounds["max_y"]) - float(canonical_bounds["min_y"]), 1e-9)
        pad = max(canonical_width, canonical_height) * 0.25
        pad = max(pad, 0.1)
        raster_min_x = float(canonical_bounds["min_x"]) - pad
        raster_max_x = float(canonical_bounds["max_x"]) + pad
        raster_min_y = float(canonical_bounds["min_y"]) - pad
        raster_max_y = float(canonical_bounds["max_y"]) + pad
        raster_world_width = raster_max_x - raster_min_x
        raster_world_height = raster_max_y - raster_min_y

        points_xy_rel = []
        hough_segment_count = 0
        endpoint_count = 0
        if png_path and os.path.exists(png_path):
            try:
                img_width, img_height, lum = _png_to_luminance(png_path)
                binary = []
                for row in range(img_height):
                    start = row * img_width
                    row_pixels = []
                    for col in range(img_width):
                        row_pixels.append(lum[start + col] < 128)
                    binary.append(row_pixels)
                endpoints, hough_segment_count = _hough_endpoints(binary, min_length_px=3)
                endpoint_count = len(endpoints)
                for col, row in endpoints:
                    x_rel = raster_min_x + (float(col) / float(max(1, img_width))) * raster_world_width
                    y_rel = raster_min_y + (1.0 - (float(row) / float(max(1, img_height)))) * raster_world_height
                    points_xy_rel.append([x_rel, y_rel])
            except Exception as exc:
                _emit_lookup_diagnostic(
                    diagnostic_callback,
                    {
                        "symbol_type_key": symbol_type_key,
                        "cache_hit": False,
                        "miss_reason": "rebuild_decode_failure: {}".format(exc),
                        "elapsed_ms": (time.perf_counter() - lookup_start) * 1000.0,
                    },
                )
                warnings.warn(
                    "DSE: symbol raster decode failure for element {} ({}) : {}".format(
                        context.get("elem_id"), family_name, exc
                    ),
                    RuntimeWarning,
                    stacklevel=2,
                )
                return None

        entry = {
            "cache_schema": "symbol_raster.v1",
            "cache_key": cache_key,
            "family_name": family_name,
            "view_scale": view_scale,
            "detail_level": detail_level,
            "is_line_based": is_line_based,
            "doc_scope": doc_scope,
            "obb_width": obb_width,
            "obb_height": obb_height,
            "obb_paper_width_inches": obb_paper_width_inches,
            "obb_paper_height_inches": obb_paper_height_inches,
            "px_w": px_w,
            "px_h": px_h,
            "canonical_bounds": canonical_bounds,
            "points": points_xy_rel,
            "hough_segment_count": hough_segment_count,
            "endpoint_count": endpoint_count,
            "pipeline_version": _SYMBOL_RASTER_PIPELINE_VERSION,
            "build_time_utc": datetime.now(timezone.utc).isoformat(),
        }
        _write_cache_entry(cache_path, entry)
        _memory_cache_set(cache_key, entry["points"])
        _emit_lookup_diagnostic(
            diagnostic_callback,
            {
                "symbol_type_key": symbol_type_key,
                "cache_hit": False,
                "cache_layer": "rebuild",
                "miss_reason": miss_reason,
                "elapsed_ms": (time.perf_counter() - lookup_start) * 1000.0,
            },
        )
        return points_xy_rel
    finally:
        _cleanup_export_tmp_dir(export_tmp_dir)


def _apply_canonical_instance_transform(
    points_xy,
    placement_point,
    axis_x,
    mirrored=False,
    length_scale_x=1.0,
):
    px, py = float(placement_point[0]), float(placement_point[1])
    dx, dy = float(axis_x[0]), float(axis_x[1])
    # Build the local Y axis from local X; mirroring flips handedness in canonical local frame.
    ey_x = -dy
    ey_y = dx
    if mirrored:
        ey_x *= -1.0
        ey_y *= -1.0
    out = []
    for xy in points_xy or []:
        try:
            x = float(xy[0]) * float(length_scale_x)
            y = float(xy[1])
            out.append([px + (x * dx) + (y * ey_x), py + (x * dy) + (y * ey_y)])
        except Exception:
            continue
    return out


def _obb_paper_inches(obb_ft, view_scale):
    try:
        obb_ft_value = float(obb_ft)
        scale = float(view_scale)
        if not math.isfinite(obb_ft_value) or not math.isfinite(scale):
            return 0.0
        scale = max(scale, 1.0)
        paper_inches = (obb_ft_value * 12.0) / scale
        if not math.isfinite(paper_inches):
            return 0.0
        return max(paper_inches, 0.0)
    except Exception:
        return 0.0


def _export_pixel_size_from_obb_paper_inches(obb_paper_width_inches, obb_paper_height_inches):
    try:
        width_inches = float(obb_paper_width_inches)
    except Exception:
        width_inches = 0.0
    if not math.isfinite(width_inches):
        width_inches = 0.0
    try:
        height_inches = float(obb_paper_height_inches)
    except Exception:
        height_inches = 0.0
    if not math.isfinite(height_inches):
        height_inches = 0.0
    max_inches_for_ceil = 512.0 / 96.0
    width_inches = min(max(width_inches, 0.0), max_inches_for_ceil)
    height_inches = min(max(height_inches, 0.0), max_inches_for_ceil)
    px_w = max(64, min(512, int(math.ceil(width_inches * 96.0))))
    px_h = max(64, min(512, int(math.ceil(height_inches * 96.0))))
    return px_w, px_h


def _export_temp_view_png(doc, tmp_view, px_w, px_h):
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
    export_px_w = int(px_w)
    export_px_h = int(px_h)
    if hasattr(opts, "ZoomType"):
        try:
            from Autodesk.Revit.DB import ZoomFitType

            opts.ZoomType = ZoomFitType.FitToPage
        except Exception:
            pass
    if hasattr(opts, "FitDirection"):
        try:
            from Autodesk.Revit.DB import FitDirectionType

            opts.FitDirection = (
                FitDirectionType.Horizontal if export_px_w >= export_px_h else FitDirectionType.Vertical
            )
        except Exception:
            pass
    if hasattr(opts, "PixelSize"):
        try:
            opts.PixelSize = max(export_px_w, export_px_h)
        except Exception:
            pass
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

    cache_bucket = _RUN_DOCUMENT_LOOKUP_CACHE.setdefault("drafting_view_family_type_id", {})
    doc_key = _document_cache_key(doc)
    cached_id = cache_bucket.get(doc_key)
    if cached_id is not None:
        try:
            if doc.GetElement(cached_id) is not None:
                _increment_doc_lookup_stat("drafting_lookup_hits")
                return cached_id
        except Exception:
            pass
        cache_bucket.pop(doc_key, None)

    _increment_doc_lookup_stat("drafting_lookup_misses")
    collector = FilteredElementCollector(doc).WherePasses(ElementClassFilter(ViewFamilyType))
    for view_family_type in collector:
        if getattr(view_family_type, "ViewFamily", None) == ViewFamily.Drafting:
            cache_bucket[doc_key] = view_family_type.Id
            return view_family_type.Id
    return None


def _suppress_filled_region_patterns(doc, tmp_view):
    """Hide filled-region and family-instance surface patterns in a temp view."""
    try:
        import clr

        clr.AddReference("RevitAPI")
        from Autodesk.Revit.DB import (
            FamilyInstance,
            FilledRegion,
            FilteredElementCollector,
            OverrideGraphicSettings,
        )
    except Exception as exc:
        warnings.warn(
            "DSE: symbol raster failed to load RevitAPI for pattern suppression: {}".format(exc),
            RuntimeWarning,
            stacklevel=2,
        )
        return

    try:
        override = OverrideGraphicSettings()
        try:
            override.SetSurfaceForegroundPatternVisible(False)
            override.SetSurfaceBackgroundPatternVisible(False)
        except Exception:
            # Some Python bindings expose these as writable properties instead of setters.
            override.SurfaceForegroundPatternVisible = False
            override.SurfaceBackgroundPatternVisible = False
    except Exception as exc:
        warnings.warn(
            "DSE: symbol raster failed to create FilledRegion suppression override: {}".format(exc),
            RuntimeWarning,
            stacklevel=2,
        )
        return

    def _collector_for_temp_view():
        try:
            return FilteredElementCollector(doc, tmp_view.Id)
        except Exception:
            # Test doubles may only support the no-arg constructor.
            return FilteredElementCollector()

    def _collect_of_class(cls):
        collector = _collector_for_temp_view()
        if not hasattr(collector, "OfClass"):
            return []
        return list(collector.OfClass(cls))

    try:
        filled_regions = _collect_of_class(FilledRegion)
    except Exception as exc:
        warnings.warn(
            "DSE: symbol raster failed collecting FilledRegion elements in temp view: {}".format(exc),
            RuntimeWarning,
            stacklevel=2,
        )
        filled_regions = []
    for filled_region in filled_regions:
        try:
            tmp_view.SetElementOverrides(filled_region.Id, override)
        except Exception as exc:
            warnings.warn(
                "DSE: symbol raster failed to suppress FilledRegion {}: {}".format(
                    _safe_int_element_id(filled_region), exc
                ),
                RuntimeWarning,
                stacklevel=2,
            )

    try:
        family_instances = _collect_of_class(FamilyInstance)
    except Exception as exc:
        warnings.warn(
            "DSE: symbol raster failed collecting FamilyInstance elements in temp view: {}".format(exc),
            RuntimeWarning,
            stacklevel=2,
        )
        family_instances = []
    for family_instance in family_instances:
        try:
            tmp_view.SetElementOverrides(family_instance.Id, override)
        except Exception as exc:
            warnings.warn(
                "DSE: symbol raster failed to suppress FamilyInstance {}: {}".format(
                    _safe_int_element_id(family_instance), exc
                ),
                RuntimeWarning,
                stacklevel=2,
            )


def _create_fresh_view_with_symbol(
    doc,
    view,
    element,
    obb_width=0.0,
    obb_height=0.0,
    include_canonical_bounds=False,
):
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
                # Canonical line-based cache generation uses a fixed 12" local +X segment
                # (left-to-right) and does not derive length/orientation from observed instance pose.
                from Autodesk.Revit.DB import Line

                length_ft = _CANONICAL_LINE_LENGTH_FT
                dx, dy = 1.0, 0.0
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
            _suppress_filled_region_patterns(doc, tmp_view)
            doc.Regenerate()
            bb = tmp_inst.get_BoundingBox(tmp_view)
            canonical_bounds = None
            if bb is not None:
                canonical_bounds = {
                    "min_x": float(bb.Min.X),
                    "max_x": float(bb.Max.X),
                    "min_y": float(bb.Min.Y),
                    "max_y": float(bb.Max.Y),
                }
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
            else:
                # Fallback for rare API cases: use deterministic canonical defaults so cache output
                # remains type-stable even when temporary instance bounds are unavailable.
                if _is_line_based_family_instance(element):
                    canonical_bounds = {
                        "min_x": 0.0,
                        "max_x": float(_CANONICAL_LINE_LENGTH_FT),
                        "min_y": -0.05 * float(_CANONICAL_LINE_LENGTH_FT),
                        "max_y": 0.05 * float(_CANONICAL_LINE_LENGTH_FT),
                    }
                else:
                    half_w = max(float(obb_width) * 0.5, 1.0 / 12.0)
                    half_h = max(float(obb_height) * 0.5, 1.0 / 12.0)
                    canonical_bounds = {
                        "min_x": -half_w,
                        "max_x": half_w,
                        "min_y": -half_h,
                        "max_y": half_h,
                    }
            doc.Regenerate()

        return (tmp_view, canonical_bounds) if include_canonical_bounds else tmp_view
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


def _collect_points_for_element(view, doc, element, config, diagnostic_callback=None):
    context = _build_symbol_instance_context(view, element)
    if context is None:
        return None, None
    points_xy_rel = _collect_canonical_points_for_context(
        view=view,
        doc=doc,
        element=element,
        context=context,
        config=config,
        diagnostic_callback=diagnostic_callback,
    )
    if points_xy_rel is None:
        return None, None
    points_xy = _apply_canonical_instance_transform(
        points_xy_rel,
        placement_point=context["placement_point"],
        axis_x=context["axis_x"],
        mirrored=context["is_mirrored"],
        length_scale_x=context["length_scale_x"],
    )
    return context["elem_id"], points_xy


def collect_raster_points_for_view(view, doc=None, config=None, diagnostic_callback=None, elements=None):
    """Collect view-local raster edge points for FamilyInstance elements.

    Returns: {element_id_int: [[x, y], ...]}
    """

    out = {}
    config = config or {}
    doc = doc or getattr(view, "Document", None)
    if view is None or doc is None:
        return out

    if elements is None:
        try:
            elements = get_view_elements(view)
        except Exception as exc:
            warnings.warn(
                "DSE: symbol raster failed to read view elements: {}".format(exc),
                RuntimeWarning,
                stacklevel=2,
            )
            return out

    grouped_instances = {}
    for element in elements:
        try:
            if not is_family_instance(element):
                continue
            context = _build_symbol_instance_context(view, element)
            if context is None:
                continue
            cache_key = context["cache_key"]
            if cache_key not in grouped_instances:
                grouped_instances[cache_key] = {
                    "element": element,
                    "context": context,
                    "members": [],
                }
            grouped_instances[cache_key]["members"].append(context)
        except Exception as exc:
            elem_id = _safe_int_element_id(element)
            fam_name, _ = _safe_type_sig_parts(element)
            warnings.warn(
                "DSE: symbol raster unexpected failure for element {} ({}) : {}".format(
                    elem_id, fam_name, exc
                ),
                RuntimeWarning,
                stacklevel=2,
            )
            continue

    for group in grouped_instances.values():
        try:
            canonical_points = _collect_canonical_points_for_context(
                view=view,
                doc=doc,
                element=group["element"],
                context=group["context"],
                config=config,
                diagnostic_callback=diagnostic_callback,
            )
            if canonical_points is None:
                continue
            for context in group["members"]:
                elem_id = context["elem_id"]
                if elem_id is None:
                    continue
                out[int(elem_id)] = _apply_canonical_instance_transform(
                    canonical_points,
                    placement_point=context["placement_point"],
                    axis_x=context["axis_x"],
                    mirrored=context["is_mirrored"],
                    length_scale_x=context["length_scale_x"],
                )
        except Exception as exc:
            elem_id = _safe_int_element_id(group.get("element"))
            fam_name, _ = _safe_type_sig_parts(group.get("element"))
            warnings.warn(
                "DSE: symbol raster unexpected failure for element {} ({}) : {}".format(
                    elem_id, fam_name, exc
                ),
                RuntimeWarning,
                stacklevel=2,
            )
            continue

    return out
