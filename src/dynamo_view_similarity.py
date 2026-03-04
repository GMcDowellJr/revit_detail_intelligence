"""
Dynamo (CPython3) script for Revit 2025.
Feature-based similarity matching for detail / drafting views.

Inputs (Dynamo IN):
- IN[0]: query view reference (DB.View, wrapped Dynamo View, ElementId/int, or single-item list)
- IN[1]: corpus view references (list of the same supported formats)
- IN[2]: topN (optional, default=5)
- IN[3]: sampleN (optional). When provided, returns sampled fingerprint reports instead of similarity results.
- IN[4]: sampleSeed (optional, default=0). Used only when IN[3] is provided.

Output (OUT):
- similarity mode: list[dict] sorted by descending similarity score.
- sampling mode: list[dict] fingerprint report for each sampled view, including collected element-level details and summary counts.
"""

import math
import random
from collections import defaultdict

import clr

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    CategoryType,
    CurveElement,
    DetailCurve,
    DetailLine,
    Dimension,
    ElementId,
    FamilyInstance,
    FilledRegion,
    FilteredElementCollector,
    TextNote,
    View,
    ViewType,
)

try:
    clr.AddReference("RevitServices")
    from RevitServices.Persistence import DocumentManager
except Exception:
    DocumentManager = None

# -------------------------
# CONFIG / POLICY (tunable)
# -------------------------
CONFIG = {
    "kNN_k": 3,
    "len_bins": [0.00, 0.10, 0.20, 0.35, 0.50, 0.70, 1.00, 1.40, 2.00, float("inf")],
    "ang_bins_deg": [0, 15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180],
    "tol_coord": 1.0 / 256.0,  # feet
    "weights": {"w_tokens": 0.55, "w_geom": 0.35, "w_fine": 0.10},
    "confidence_thresholds": {"HIGH_min": 0.85, "MED_min": 0.65},
    "token_weights_by_kind": {
        "category": 1.0,
        "type_sig": 1.5,
        "line_style": 1.0,
        "detail_component": 2.0,
        "fill_region": 1.2,
        "dim_style": 1.2,
        "text_type": 0.8,
    },
}
EPS = 1e-9


class ViewFeatures(object):
    def __init__(self, view_id, view_kind, tokens, geom_fingerprint, fine_metrics, debug=None):
        self.view_id = view_id
        self.view_kind = view_kind
        self.tokens = tokens
        self.geom_fingerprint = geom_fingerprint
        self.fine_metrics = fine_metrics
        self.debug = debug or {}


def _current_doc():
    if DocumentManager is None:
        return None
    try:
        return DocumentManager.Instance.CurrentDBDocument
    except Exception:
        return None


def _first_item(value):
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        return value[0]
    return value


def _unwrap_dynamo_element(value):
    # Supports Revit.Elements wrappers in Dynamo CPython.
    if value is None:
        return None
    try:
        return value.InternalElement
    except Exception:
        return value


def _coerce_view(value, fallback_doc=None):
    """Accept View, wrapped Dynamo View, ElementId, int, or single-item list of those."""
    candidate = _unwrap_dynamo_element(_first_item(value))

    if isinstance(candidate, View):
        return candidate

    doc = fallback_doc or _current_doc()
    if doc is None:
        return None

    if isinstance(candidate, ElementId):
        elem = doc.GetElement(candidate)
        return elem if isinstance(elem, View) else None

    try:
        elem = doc.GetElement(ElementId(int(candidate)))
        return elem if isinstance(elem, View) else None
    except Exception:
        return None


def _coerce_views(values, fallback_doc=None):
    if values is None:
        return []
    seq = values if isinstance(values, list) else [values]
    out = []
    for v in seq:
        view = _coerce_view(v, fallback_doc=fallback_doc)
        if view is not None:
            out.append(view)
    return out


def _safe_name(obj, fallback="<none>"):
    try:
        return obj.Name if obj is not None else fallback
    except Exception:
        return fallback


def _safe_type_name(element, fallback="<none>"):
    if element is None:
        return fallback
    try:
        typ = element.Document.GetElement(element.GetTypeId())
        name = _safe_name(typ, fallback=fallback)
        return name if name else fallback
    except Exception:
        return fallback


def _class_name(element):
    try:
        return element.GetType().Name
    except Exception:
        return "<unknown-class>"


def _increment(counter, key, amount=1):
    counter[key] = counter.get(key, 0) + amount


def _token_weight(kind):
    return CONFIG["token_weights_by_kind"].get(kind, 1.0)


def _add_token(tokens, token, kind):
    tokens[token] += _token_weight(kind)


def _category_type_label(category):
    """Return a stable category type label across Revit Python hosts."""
    if category is None:
        return None

    cat_type = getattr(category, "CategoryType", None)
    if cat_type is None:
        return None

    # In some Dynamo CPython environments, enum values arrive as plain ints.
    enum_by_int = {
        int(CategoryType.Model): "Model",
        int(CategoryType.Annotation): "Annotation",
    }

    try:
        return enum_by_int.get(int(cat_type), str(cat_type))
    except Exception:
        try:
            return cat_type.ToString()
        except Exception:
            return str(cat_type)


def classify_view_kind(view):
    if view.ViewType == ViewType.DraftingView:
        return "DRAFTING"
    if view.ViewType in (ViewType.Detail, ViewType.Section, ViewType.Elevation):
        has_model = any(_category_type_label(e.Category) != "Annotation" for e in get_view_elements(view))
        return "DETAIL_MODEL" if has_model else "DETAIL_DRAFTING"
    return "DETAIL_DRAFTING"


def get_view_elements(view):
    doc = view.Document
    return list(
        FilteredElementCollector(doc, view.Id)
        .WhereElementIsNotElementType()
        .ToElements()
    )


def get_model_elements_contributing_to_view(view):
    elems = []
    for e in get_view_elements(view):
        cat = e.Category
        if cat is None:
            continue
        if _category_type_label(cat) == "Model":
            elems.append(e)
    return elems


def get_annotation_elements(view):
    elems = []
    for e in get_view_elements(view):
        cat = e.Category
        if cat is None:
            continue
        if _category_type_label(cat) == "Annotation":
            elems.append(e)
    return elems


def type_signature(element):
    doc = element.Document
    type_name = "<no-type>"
    try:
        typ = doc.GetElement(element.GetTypeId())
        type_name = _safe_name(typ)
    except Exception:
        pass

    fam_name = "<no-family>"
    if isinstance(element, FamilyInstance) and element.Symbol is not None:
        fam_name = _safe_name(element.Symbol.Family)
    return "{}|{}".format(fam_name, type_name)


def family_type_sig(annotation_element):
    return type_signature(annotation_element)


def get_2d_curves_in_view(view, only_model_intersections=False):
    # Practical Dynamo/Revit implementation:
    # - Collect view-owned detail curves
    # - Add model curves visible in the view when requested
    curves = []
    for e in get_view_elements(view):
        if isinstance(e, CurveElement):
            if only_model_intersections:
                if isinstance(e, (DetailCurve, DetailLine)):
                    continue
            c = e.GeometryCurve
            if c is not None:
                curves.append(c)
    return curves


def endpoints_from_curves(curves):
    pts = []
    for c in curves:
        try:
            pts.append(c.GetEndPoint(0))
            pts.append(c.GetEndPoint(1))
        except Exception:
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
    o = view.Origin
    out = []
    for p in points_xyz:
        vx = p.X - o.X
        vy = p.Y - o.Y
        vz = p.Z - o.Z
        x = vx * right.X + vy * right.Y + vz * right.Z
        y = vx * up.X + vy * up.Y + vz * up.Z
        out.append((x, y))
    return out


def _bbox(points2d):
    if not points2d:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [p[0] for p in points2d]
    ys = [p[1] for p in points2d]
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_diagonal(points2d):
    x0, y0, x1, y1 = _bbox(points2d)
    return math.hypot(x1 - x0, y1 - y0)


def k_nearest_neighbors(points2d, i, k):
    x0, y0 = points2d[i]
    rows = []
    for j, (x, y) in enumerate(points2d):
        if i == j:
            continue
        d = math.hypot(x - x0, y - y0)
        rows.append((d, round(x, 9), round(y, 9), j))
    rows.sort(key=lambda r: (r[0], r[1], r[2], r[3]))
    return [r[3] for r in rows[:k]]


def robust_scale(points2d, k):
    if len(points2d) < (k + 1):
        return max(EPS, bbox_diagonal(points2d))
    dists = []
    for i in range(len(points2d)):
        for j in k_nearest_neighbors(points2d, i, k):
            dists.append(math.hypot(points2d[j][0] - points2d[i][0], points2d[j][1] - points2d[i][1]))
    if not dists:
        return max(EPS, bbox_diagonal(points2d))
    dists.sort()
    med = dists[len(dists) // 2]
    if med <= EPS:
        return max(EPS, bbox_diagonal(points2d))
    return med


def bin_index(v, bins):
    for i in range(len(bins) - 1):
        if bins[i] <= v < bins[i + 1]:
            return i
    return len(bins) - 2


def normalize_l1(vec):
    s = sum(vec)
    if s <= EPS:
        return [0.0 for _ in vec]
    return [v / s for v in vec]


def geom_fingerprint_knn(points2d, k, len_bins, ang_bins):
    n = len(points2d)
    if n < 2:
        return [0.0] * ((len(len_bins) - 1) * (len(ang_bins) - 1))

    edges = []
    for i in range(n):
        for j in k_nearest_neighbors(points2d, i, k):
            if i < j:
                dx = points2d[j][0] - points2d[i][0]
                dy = points2d[j][1] - points2d[i][1]
                length = math.hypot(dx, dy)
                angle = abs(math.degrees(math.atan2(dy, dx)))
                if angle > 180.0:
                    angle = 360.0 - angle
                edges.append((length, angle))

    cols = len(ang_bins) - 1
    hist = [0.0] * ((len(len_bins) - 1) * cols)
    for L, A in edges:
        bi = bin_index(L, len_bins)
        bj = bin_index(A, ang_bins)
        hist[bi * cols + bj] += 1.0
    return normalize_l1(hist)


def bbox_aspect_ratio(points2d):
    x0, y0, x1, y1 = _bbox(points2d)
    w = max(x1 - x0, EPS)
    h = max(y1 - y0, EPS)
    return max(w, h) / min(w, h)


def linework_density(curves, points2d):
    area_bbox = max(EPS, (_bbox(points2d)[2] - _bbox(points2d)[0]) * (_bbox(points2d)[3] - _bbox(points2d)[1]))
    total_len = 0.0
    for c in curves:
        try:
            total_len += c.Length
        except Exception:
            pass
    return total_len / area_bbox


def cosine_similarity(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= EPS or nb <= EPS:
        return 0.0
    return dot / (na * nb)


def gaussian_sim(x, y, sigma=0.5):
    if sigma <= EPS:
        return 0.0
    d = x - y
    return math.exp(-(d * d) / (2.0 * sigma * sigma))


def token_similarity(tokens_a, tokens_b):
    keys = set(tokens_a.keys()) | set(tokens_b.keys())
    if not keys:
        return 0.0
    num = 0.0
    den = 0.0
    for k in keys:
        a = tokens_a.get(k, 0.0)
        b = tokens_b.get(k, 0.0)
        num += min(a, b)
        den += max(a, b)
    return 0.0 if den <= EPS else num / den


def fine_similarity(fa, fb):
    if not fa or not fb:
        return 0.5
    s1 = gaussian_sim(fa.get("bbox_aspect", 1.0), fb.get("bbox_aspect", 1.0), sigma=0.5)
    s2 = gaussian_sim(fa.get("linework_density", 0.0), fb.get("linework_density", 0.0), sigma=0.5)
    return 0.5 * s1 + 0.5 * s2


def confidence_tier(score):
    if score >= CONFIG["confidence_thresholds"]["HIGH_min"]:
        return "HIGH"
    if score >= CONFIG["confidence_thresholds"]["MED_min"]:
        return "MEDIUM"
    return "LOW"


def top_shared_bins(fp_a, fp_b, top=10):
    rows = [(i, min(fp_a[i], fp_b[i])) for i in range(min(len(fp_a), len(fp_b)))]
    rows.sort(key=lambda r: (-r[1], r[0]))
    return [r for r in rows[:top] if r[1] > 0.0]


def explain_match(q, c):
    common = set(q.tokens.keys()) & set(c.tokens.keys())
    token_contrib = [(k, min(q.tokens[k], c.tokens[k])) for k in common]
    token_contrib.sort(key=lambda x: (-x[1], x[0]))
    return {
        "top_shared_tokens": token_contrib[:10],
        "top_shared_geom_bins": top_shared_bins(q.geom_fingerprint, c.geom_fingerprint, top=10),
    }


def _element_base_info(element):
    return {
        "element_id": getattr(getattr(element, "Id", None), "IntegerValue", None),
        "class_name": _class_name(element),
        "category": _safe_name(getattr(element, "Category", None), fallback="<none>"),
    }


def _collect_token_data_for_view(view, kind, tokens=None, include_element_report=False):
    token_store = tokens if tokens is not None else defaultdict(float)
    element_report = []
    summary = {
        "elements_seen_total": 0,
        "elements_collected_total": 0,
        "elements_with_tokens": 0,
        "elements_without_tokens": 0,
        "count_by_collection_group": {},
        "count_by_class_name": {},
    }

    def record_row(element, group, info, added_tokens, collected=True):
        _increment(summary, "elements_seen_total")
        if collected:
            _increment(summary, "elements_collected_total")
        _increment(summary["count_by_collection_group"], group)
        class_name = _class_name(element)
        _increment(summary["count_by_class_name"], class_name)

        if added_tokens:
            _increment(summary, "elements_with_tokens")
        else:
            _increment(summary, "elements_without_tokens")

        if include_element_report:
            row = _element_base_info(element)
            row.update(
                {
                    "collection_group": group,
                    "collected": bool(collected),
                    "collected_info": dict(info, tokens_added=added_tokens),
                }
            )
            element_report.append(row)

    if kind == "DETAIL_MODEL":
        for e in get_model_elements_contributing_to_view(view):
            cat_name = _safe_name(e.Category, "<no-category>")
            type_sig = type_signature(e)
            category_token = "category:" + cat_name
            type_token = "type_sig:" + type_sig
            _add_token(token_store, category_token, "category")
            _add_token(token_store, type_token, "type_sig")
            record_row(
                e,
                "model_elements",
                {"category_name": cat_name, "type_signature": type_sig},
                [category_token, type_token],
                collected=True,
            )
    else:
        for a in get_annotation_elements(view):
            added_tokens = []
            info = {}
            group = "annotation_elements_unmapped"

            if isinstance(a, FamilyInstance):
                value = family_type_sig(a)
                token = "detail_component:" + value
                _add_token(token_store, token, "detail_component")
                added_tokens.append(token)
                info["detail_component_sig"] = value
                info["element_type_name"] = _safe_type_name(a)
                group = "annotation_detail_components"
            elif isinstance(a, FilledRegion):
                value = _safe_name(a)
                token = "fill_region:" + value
                _add_token(token_store, token, "fill_region")
                added_tokens.append(token)
                info["fill_region_name"] = value
                group = "annotation_filled_regions"
            elif isinstance(a, Dimension):
                value = _safe_name(a.DimensionType)
                token = "dim_style:" + value
                _add_token(token_store, token, "dim_style")
                added_tokens.append(token)
                info["dimension_style"] = value
                info["dimension_type_name"] = _safe_type_name(a)
                group = "annotation_dimensions"
            elif isinstance(a, TextNote):
                value = _safe_name(a.TextNoteType)
                token = "text_type:" + value
                _add_token(token_store, token, "text_type")
                added_tokens.append(token)
                info["text_type"] = value
                info["text_type_name"] = _safe_type_name(a)
                group = "annotation_text_notes"
            elif isinstance(a, (DetailCurve, DetailLine, CurveElement)):
                value = _safe_name(a.LineStyle)
                token = "line_style:" + value
                _add_token(token_store, token, "line_style")
                added_tokens.append(token)
                info["line_style"] = value
                group = "annotation_lines"

            if not added_tokens:
                info["reason"] = "annotation element is not mapped to a token strategy"

            record_row(
                a,
                group,
                info,
                added_tokens,
                collected=True,
            )

    return dict(token_store), element_report, summary


def extract_features(view):
    kind = classify_view_kind(view)
    tokens, _, _ = _collect_token_data_for_view(view, kind, include_element_report=False)

    curves = get_2d_curves_in_view(view, only_model_intersections=(kind == "DETAIL_MODEL"))
    pts = endpoints_from_curves(curves)
    pts = dedupe_points_by_grid(pts, CONFIG["tol_coord"])
    pts2 = to_view_local_2d(pts, view)

    scale = robust_scale(pts2, CONFIG["kNN_k"])
    ptsn = [(p[0] / scale, p[1] / scale) for p in pts2] if pts2 else []

    geom_fp = geom_fingerprint_knn(
        ptsn,
        k=CONFIG["kNN_k"],
        len_bins=CONFIG["len_bins"],
        ang_bins=CONFIG["ang_bins_deg"],
    )

    fine = {
        "pt_count": float(len(ptsn)),
        "bbox_aspect": bbox_aspect_ratio(ptsn) if ptsn else 1.0,
        "linework_density": linework_density(curves, ptsn) if ptsn else 0.0,
    }

    return ViewFeatures(
        view_id=view.Id.IntegerValue,
        view_kind=kind,
        tokens=dict(tokens),
        geom_fingerprint=geom_fp,
        fine_metrics=fine,
        debug={"scale": scale, "pt_count": len(ptsn)},
    )


def find_similar_views(query_view, corpus_views, top_n=5):
    q = extract_features(query_view)
    corpus_feat = [extract_features(v) for v in corpus_views if isinstance(v, View) and v.Id != query_view.Id]

    results = []
    w = CONFIG["weights"]
    for c in corpus_feat:
        s_tokens = token_similarity(q.tokens, c.tokens)
        s_geom = cosine_similarity(q.geom_fingerprint, c.geom_fingerprint)
        s_fine = fine_similarity(q.fine_metrics, c.fine_metrics)
        s_total = w["w_tokens"] * s_tokens + w["w_geom"] * s_geom + w["w_fine"] * s_fine
        results.append(
            {
                "candidate_view_id": c.view_id,
                "score_total": s_total,
                "score_tokens": s_tokens,
                "score_geom": s_geom,
                "score_fine": s_fine,
                "confidence_tier": confidence_tier(s_total),
                "explanation": explain_match(q, c),
            }
        )

    results.sort(key=lambda r: (-r["score_total"], r["candidate_view_id"]))
    return results[: max(0, int(top_n))]


def _view_label(view):
    try:
        return view.Name
    except Exception:
        return "<unknown>"


def sample_view_fingerprints(views, sample_size, seed=0):
    """
    Sample a deterministic random subset of views and report each view fingerprint.

    Fingerprints are produced by the same extract_features(...) strategy used in
    similarity matching.
    """
    clean_views = [v for v in views if isinstance(v, View)]
    if not clean_views:
        return []

    n = max(0, int(sample_size))
    if n == 0:
        return []

    if n >= len(clean_views):
        sampled = list(clean_views)
    else:
        rng = random.Random(int(seed))
        sampled = rng.sample(clean_views, n)

    report = []
    for v in sampled:
        feat = extract_features(v)
        _, element_report, collection_summary = _collect_token_data_for_view(v, feat.view_kind, include_element_report=True)
        report.append(
            {
                "view_id": feat.view_id,
                "view_name": _view_label(v),
                "view_kind": feat.view_kind,
                "tokens": feat.tokens,
                "geom_fingerprint": feat.geom_fingerprint,
                "fine_metrics": feat.fine_metrics,
                "debug": feat.debug,
                "collected_elements": element_report,
                "collection_summary": collection_summary,
            }
        )

    report.sort(key=lambda r: r["view_id"])
    return report


# Dynamo entrypoint
doc = _current_doc()
query_input = IN[0] if len(IN) > 0 else None
corpus_input = IN[1] if len(IN) > 1 else []
top_n = IN[2] if len(IN) > 2 and IN[2] is not None else 5
sample_n = IN[3] if len(IN) > 3 else None
sample_seed = IN[4] if len(IN) > 4 and IN[4] is not None else 0

query_view = _coerce_view(query_input, fallback_doc=doc)
corpus_views = _coerce_views(corpus_input, fallback_doc=doc)

if sample_n is not None:
    OUT = sample_view_fingerprints(corpus_views, sample_n, seed=sample_seed)
elif query_view is None:
    OUT = {
        "error": "IN[0] must resolve to a Revit DB.View (View, wrapped View, ElementId, int, or single-item list)."
    }
else:
    OUT = find_similar_views(query_view, corpus_views, top_n)
