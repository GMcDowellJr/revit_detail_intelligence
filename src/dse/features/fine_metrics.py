from dse.config import EPS
from dse.revit_api.geometry_2d import bbox


def bbox_aspect_ratio(points2d):
    x0, y0, x1, y1 = bbox(points2d)
    w = max(x1 - x0, EPS)
    h = max(y1 - y0, EPS)
    return max(w, h) / min(w, h)


def linework_density(curves, points2d):
    x0, y0, x1, y1 = bbox(points2d)
    area_bbox = max(EPS, (x1 - x0) * (y1 - y0))
    total_len = 0.0
    for curve in curves:
        try:
            total_len += curve.Length
        except Exception:
            # Single curve failure must not abort density aggregation in this view.
            continue
    return total_len / area_bbox


def build_fine_metrics(curves, points2d):
    return {
        "pt_count": float(len(points2d)),
        "bbox_aspect": bbox_aspect_ratio(points2d) if points2d else 1.0,
        "linework_density": linework_density(curves, points2d) if points2d else 0.0,
    }
