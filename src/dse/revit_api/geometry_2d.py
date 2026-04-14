import math

import clr

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (  # noqa: E402
    CurveElement,
    DetailCurve,
    DetailLine,
    FamilyInstance,
    FilledRegion,
    GeometryInstance,
    Options,
)

from dse.config import CONFIG, EPS  # noqa: E402
from dse.revit_api.collect import get_view_elements  # noqa: E402


def element_curve_cache_key(element):
    if element is None:
        return None

    elem_id = getattr(element, "Id", None)
    if elem_id is None:
        return None

    try:
        id_value = int(elem_id.Value)
    except Exception:
        try:
            id_value = int(elem_id.IntegerValue)
        except Exception:
            return None

    doc = getattr(element, "Document", None)
    if doc is None:
        return id_value

    try:
        doc_key = doc.GetHashCode()
    except Exception:
        doc_key = None
    return (doc_key, id_value)


def collect_curves_from_geometry(geom_obj, out_curves):
    if geom_obj is None:
        return
    for g in geom_obj:
        if g is None:
            continue
        try:
            if hasattr(g, "AsCurve"):
                c = g.AsCurve()
                if c is not None:
                    out_curves.append(c)
                    continue
        except Exception:
            # Single geometry object failure must not abort per-element curve extraction.
            pass
        if hasattr(g, "GetEndPoint"):
            out_curves.append(g)
            continue
        if isinstance(g, GeometryInstance):
            try:
                collect_curves_from_geometry(g.GetInstanceGeometry(), out_curves)
            except Exception:
                # Single geometry instance failure must not abort per-element curve extraction.
                pass
            try:
                collect_curves_from_geometry(g.GetSymbolGeometry(), out_curves)
            except Exception:
                # Single geometry instance failure must not abort per-element curve extraction.
                pass


def element_geometry_curves(element, view=None):
    curves = []
    if isinstance(element, CurveElement):
        try:
            if element.GeometryCurve is not None:
                curves.append(element.GeometryCurve)
                return curves
        except Exception:
            # Revit may throw on invalid/deleted curve elements; continue with other extraction paths.
            pass

    if isinstance(element, FilledRegion):
        try:
            loops = element.GetBoundaries()
            for loop in loops:
                for curve in loop:
                    curves.append(curve)
            if curves:
                return curves
        except Exception:
            # Revit may throw on invalid filled-region boundaries; continue with geometry fallback.
            pass

    try:
        opts = Options()
        if view is not None:
            opts.View = view
        geom = element.get_Geometry(opts)
        collect_curves_from_geometry(geom, curves)
    except Exception:
        # Geometry extraction is per-element best effort; failures should not abort view processing.
        pass
    return curves


def get_2d_curves_in_view(
    view,
    only_model_intersections=False,
    elements=None,
    element_curves=None,
    symbol_raster_points=None,
):
    curves = []
    raster_points = []
    seen_curve_ids = set()
    source = elements if elements is not None else get_view_elements(view)
    for elem in source:
        if isinstance(elem, CurveElement):
            if only_model_intersections and isinstance(elem, (DetailCurve, DetailLine)):
                continue
            try:
                c = elem.GeometryCurve
            except Exception:
                c = None
            if c is not None:
                curves.append(c)
            continue

        if only_model_intersections:
            continue

        if isinstance(elem, (FamilyInstance, FilledRegion)):
            if isinstance(elem, FamilyInstance) and symbol_raster_points is not None:
                elem_id_int = None
                try:
                    elem_id_int = int(elem.Id.Value)
                except Exception:
                    try:
                        elem_id_int = int(elem.Id.IntegerValue)
                    except Exception:
                        elem_id_int = None
                if elem_id_int is not None and elem_id_int in symbol_raster_points:
                    raster_for_elem = symbol_raster_points.get(elem_id_int) or []
                    for xy in raster_for_elem:
                        try:
                            raster_points.append((float(xy[0]), float(xy[1])))
                        except Exception:
                            # Invalid raster point rows are ignored per-element.
                            continue

            curves_for_elem = None
            if element_curves is not None:
                cache_key = element_curve_cache_key(elem)
                if cache_key is not None:
                    curves_for_elem = element_curves.get(cache_key)
            if curves_for_elem is None:
                curves_for_elem = element_geometry_curves(elem, view=view)
            for curve in curves_for_elem:
                key = None
                try:
                    p0 = curve.GetEndPoint(0)
                    p1 = curve.GetEndPoint(1)
                    key = (
                        round(p0.X, 6),
                        round(p0.Y, 6),
                        round(p0.Z, 6),
                        round(p1.X, 6),
                        round(p1.Y, 6),
                        round(p1.Z, 6),
                    )
                except Exception:
                    # Single curve endpoint failure must not abort curve collection for the view.
                    pass
                if key is None or key not in seen_curve_ids:
                    curves.append(curve)
                    if key is not None:
                        seen_curve_ids.add(key)
    return curves, raster_points


def endpoints_from_curves(curves):
    pts = []
    for curve in curves:
        try:
            pts.append(curve.GetEndPoint(0))
            pts.append(curve.GetEndPoint(1))
        except Exception:
            # Single curve endpoint failure must not abort endpoint aggregation for the view.
            continue
    return pts


def dedupe_points_by_grid(points_xyz, tol):
    seen = set()
    out = []
    inv = 1.0 / max(tol, EPS)
    for p in points_xyz:
        key = (int(round(p.X * inv)), int(round(p.Y * inv)), int(round(p.Z * inv)))
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def to_view_local_2d(points_xyz, view):
    right = view.RightDirection
    up = view.UpDirection
    origin = view.Origin
    out = []
    for p in points_xyz:
        vx = p.X - origin.X
        vy = p.Y - origin.Y
        vz = p.Z - origin.Z
        x = vx * right.X + vy * right.Y + vz * right.Z
        y = vx * up.X + vy * up.Y + vz * up.Z
        out.append((x, y))
    return out


def bbox(points2d):
    if not points2d:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [p[0] for p in points2d]
    ys = [p[1] for p in points2d]
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_diagonal(points2d):
    x0, y0, x1, y1 = bbox(points2d)
    return math.hypot(x1 - x0, y1 - y0)


def geometry_summary_for_element(element, view=None):
    curves = element_geometry_curves(element, view=view)
    pts = endpoints_from_curves(curves)
    return {
        "curve_count": len(curves),
        "endpoint_count": len(pts),
        "unique_endpoint_count": len(dedupe_points_by_grid(pts, CONFIG["tol_coord"])) if pts else 0,
        "curve_total_length": sum(getattr(c, "Length", 0.0) for c in curves),
    }


def element_layout_signature(element, view=None, curves=None):
    curves = curves if curves is not None else element_geometry_curves(element, view=view)
    pts = endpoints_from_curves(curves)
    if not pts:
        return None
    pts2 = to_view_local_2d(pts, view) if view is not None else [(p.X, p.Y) for p in pts]
    x0, y0, x1, y1 = bbox(pts2)
    w = max(x1 - x0, EPS)
    h = max(y1 - y0, EPS)
    return {
        "center": ((x0 + x1) * 0.5, (y0 + y1) * 0.5),
        "size": (w, h),
        "area": w * h,
    }
