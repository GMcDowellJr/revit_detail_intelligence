import hashlib
import json
import math
import os
import random
import time

import warnings
from dse.cache.view_feature_cache import (
    GLOBAL_VIEW_FEATURE_CACHE,
    ViewFeatureCacheEntry,
    deserialize_cache_entry,
    get_cached_bundle_with_diagnostics,
    put_bundle_in_caches,
    resolve_view_cache_root,
    serialize_cache_entry,
)
from dse.config import CONFIG, TOKEN_STOPWORDS, default_idf_for_doc_count
from dse.features.fine_metrics import build_fine_metrics
from dse.features.geom_fingerprint import bin_index, geom_fingerprint_knn, normalize_l1, robust_scale
from dse.features.idf import build_token_df_from_features, build_token_idf
from dse.diagnostics.sidecars import (
    IndexDiagnosticAccumulator,
    SearchDiagnosticBuilder,
    build_config_snapshot,
    resolve_index_sidecar_path,
    resolve_search_sidecar_path,
    write_json_sidecar,
)
from dse.features.tokens import (
    emit_token,
    family_type_sig,
    is_valid_token_value,
    new_token_store,
    safe_name,
    safe_type_name,
    token_weight,
    type_signature,
)
from dse.models import (
    ViewFeatureBundle,
    ViewPresentationSummary,
    ViewSearchFeatures,
    ViewStateSignature,
    legacy_view_features_from_search,
)
from dse.io_paths import run_stamp
from dse.outputs.contact_folder import create_contact_folder
from dse.pipelines.many_to_many import build_many_to_many_edges, write_many_to_many_outputs
from dse.ranking.similarity import (
    apply_geom_dominant_suppression,
    confidence_tier,
    cosine_similarity,
    derive_min_token_threshold,
    effective_weights,
    explain_match,
    fine_similarity,
    token_similarity,
)
from dse.revit_api.collect import (
    category_name,
    classify_view_kind,
    class_name,
    get_model_elements_contributing_to_view,
    get_view_elements,
    increment,
    is_annotation_like,
    is_curve_annotation,
    is_dimension,
    is_family_instance,
    is_filled_region,
    is_text_note,
    is_view,
    safe_name as collect_safe_name,
    token_assignment_policy,
)
from dse.revit_api.geometry_2d import (
    dedupe_points_by_grid,
    element_geometry_curves,
    element_curve_cache_key,
    element_layout_signature,
    endpoints_from_curves,
    geometry_summary_for_element,
    get_2d_curves_in_view,
    to_view_local_2d,
)
from dse.revit_api import symbol_raster
from dse.revit_api.preview_export import generate_and_cache_view_preview, get_cached_view_preview

SEARCH_SCHEMA_VERSION = "view_search_features.v0.3"


def _stable_json_hash(payload):
    txt = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha1(txt.encode("utf-8")).hexdigest()


def _bundle_source_scope(bundle):
    source_doc_id = bundle.search_features.source_doc_id or bundle.state_signature.source_doc_id
    source_doc_name = bundle.search_features.source_doc_name or bundle.state_signature.source_doc_name
    payload = {
        "source_doc_id": None if source_doc_id is None else str(source_doc_id),
        "source_doc_name": None if source_doc_name is None else str(source_doc_name),
    }
    if payload["source_doc_id"] is None and payload["source_doc_name"] is None:
        payload = {"source_scope": "<no-doc>"}
    return _stable_json_hash(payload)[:16]


def _doc_scoped_cache_path(cache_root, bundle):
    scope_hash = _bundle_source_scope(bundle)
    view_id = int(bundle.search_features.view_id)
    filename = "view_{}__doc_{}.json".format(view_id, scope_hash)
    return os.path.join(cache_root, "view_features", filename)


def _write_doc_scoped_cache_record(cache_root, bundle):
    path = _doc_scoped_cache_path(cache_root, bundle)
    entry = ViewFeatureCacheEntry(
        view_id=int(bundle.search_features.view_id),
        state_hash=str(bundle.state_signature.state_hash),
        schema_version=SEARCH_SCHEMA_VERSION,
        pipeline_version=CONFIG["pipeline_version"],
        payload=bundle,
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(serialize_cache_entry(entry))
    return path


def _string_or_none(value):
    txt = "" if value is None else str(value).strip()
    return txt or None


def _doc_provenance(view):
    doc = getattr(view, "Document", None)
    if doc is None:
        return None, None
    doc_id = getattr(doc, "PathName", None)
    if doc_id is None:
        doc_id = getattr(getattr(doc, "Application", None), "VersionBuild", None)
    doc_name = getattr(doc, "Title", None)
    return _string_or_none(doc_id), _string_or_none(doc_name)


def _view_settings_signature(view):
    payload = {
        "scale": getattr(view, "Scale", None),
        "detail_level": str(getattr(view, "DetailLevel", "")),
        "display_style": str(getattr(view, "DisplayStyle", "")),
    }
    return _stable_json_hash(payload)


def _split_tokens(token_map):
    stable_prefixes = {
        "category",
        "type_sig",
        "detail_component",
        "fill_region",
        "dim_style",
        "text_type",
    }
    stable = {}
    context = {}
    counts_by_kind = {}
    symbols = {}
    for token, weight in token_map.items():
        prefix, _, value = token.partition(":")
        target = stable if prefix in stable_prefixes else context
        target[token] = float(weight)

        kind_weight = max(1e-9, float(token_weight(prefix)))
        count_est = max(1, int(round(float(weight) / kind_weight)))
        counts_by_kind[prefix] = counts_by_kind.get(prefix, 0) + count_est

        if prefix in ("detail_component", "type_sig"):
            symbols[value] = symbols.get(value, 0) + count_est
    return stable, context, counts_by_kind, symbols


def _orientation_hist(curves):
    bins = CONFIG["ang_bins_deg"]
    hist = [0.0] * (len(bins) - 1)
    for curve in curves:
        try:
            p0 = curve.GetEndPoint(0)
            p1 = curve.GetEndPoint(1)
        except Exception:
            # Single-curve endpoint failures are expected for invalid/deleted Revit elements.
            # One failing element must not abort orientation histogram collection.
            continue
        dx = p1.X - p0.X
        dy = p1.Y - p0.Y
        angle = abs(math.degrees(math.atan2(dy, dx)))
        if angle > 180.0:
            angle = 360.0 - angle
        hist[bin_index(angle, bins)] += 1.0
    return normalize_l1(hist)


def _normalized_length_hist(curves, scale):
    bins = CONFIG["len_bins"]
    hist = [0.0] * (len(bins) - 1)
    safe_scale = max(scale, 1e-9)
    for curve in curves:
        try:
            length = float(curve.Length) / safe_scale
        except Exception:
            # Single-curve length failures are expected for invalid/deleted Revit elements.
            # One failing element must not abort length histogram collection.
            continue
        hist[bin_index(length, bins)] += 1.0
    return normalize_l1(hist)


def _layout_graph_features(view, elements, element_curves=None):
    rows = []
    for elem in elements:
        curves_for_elem = None
        if element_curves is not None:
            cache_key = element_curve_cache_key(elem)
            if cache_key is not None:
                curves_for_elem = element_curves.get(cache_key)
        sig = element_layout_signature(elem, view=view, curves=curves_for_elem)
        if sig is None:
            continue
        cx, cy = sig["center"]
        w, h = sig["size"]
        rows.append((round(cx, 2), round(cy, 2), round(w, 2), round(h, 2), class_name(elem)))

    if not rows:
        return {"node_count": 0.0, "edge_density_est": 0.0, "component_count_est": 0.0}

    rows.sort()
    node_count = float(len(rows))
    span_x = max(r[0] for r in rows) - min(r[0] for r in rows)
    span_y = max(r[1] for r in rows) - min(r[1] for r in rows)
    span = max(span_x + span_y, 1e-9)

    near_pairs = 0
    for idx in range(len(rows)):
        for jdx in range(idx + 1, len(rows)):
            dist = abs(rows[idx][0] - rows[jdx][0]) + abs(rows[idx][1] - rows[jdx][1])
            if dist <= (0.25 * span):
                near_pairs += 1
    max_edges = max(1.0, (node_count * (node_count - 1.0)) * 0.5)
    edge_density = float(near_pairs) / max_edges

    grid = {(int(r[0] * 0.5), int(r[1] * 0.5)) for r in rows}
    component_count_est = float(len(grid))

    struct_hash = _stable_json_hash(rows)
    return {
        "node_count": node_count,
        "edge_density_est": edge_density,
        "component_count_est": component_count_est,
        "center_graph_hash": struct_hash,
    }


def _build_state_context(view, symbol_raster_lookup_callback=None):
    all_elements = get_view_elements(view)
    raster_symbol_points = symbol_raster.collect_raster_points_for_view(
        view=view,
        doc=getattr(view, "Document", None),
        config=CONFIG,
        diagnostic_callback=symbol_raster_lookup_callback,
    )
    total_family_instances = sum(1 for elem in all_elements if is_family_instance(elem))
    covered_instance_ids = {
        int(elem_id) for elem_id, pts in raster_symbol_points.items() if pts
    }
    element_curves = {}
    for elem in all_elements:
        cache_key = element_curve_cache_key(elem)
        if cache_key is None:
            continue
        element_curves[cache_key] = element_geometry_curves(elem, view=view)
    kind = classify_view_kind(view, elements=all_elements)
    source_doc_id, source_doc_name = _doc_provenance(view)
    raw_tokens, _, _ = collect_token_data_for_view(
        view, kind, include_element_report=False, elements=all_elements
    )

    curves, raster_points = get_2d_curves_in_view(
        view,
        only_model_intersections=(kind == "DETAIL_MODEL"),
        elements=all_elements,
        element_curves=element_curves,
        symbol_raster_points=raster_symbol_points,
    )
    pts = endpoints_from_curves(curves)
    pts = dedupe_points_by_grid(pts, CONFIG["tol_coord"])
    pts2 = to_view_local_2d(pts, view)
    raster_points = [(float(p[0]), float(p[1])) for p in raster_points]
    raster_points = list(dict.fromkeys(raster_points))
    points_for_scale = pts2 + raster_points

    scale = robust_scale(points_for_scale, CONFIG["kNN_k"])
    ptsn_curve = [(p[0] / scale, p[1] / scale) for p in pts2] if pts2 else []
    ptsn_raster = [(p[0] / scale, p[1] / scale) for p in raster_points] if raster_points else []
    ptsn = ptsn_curve + ptsn_raster

    tokens_stable, tokens_context, counts_by_kind, symbol_multiset = _split_tokens(raw_tokens)
    token_signature = _stable_json_hash(
        {
            "tokens_stable": sorted((k, round(v, 6)) for k, v in tokens_stable.items()),
            "tokens_context": sorted((k, round(v, 6)) for k, v in tokens_context.items()),
            "token_counts_by_kind": dict(sorted(counts_by_kind.items())),
        }
    )

    layout = _layout_graph_features(view, all_elements, element_curves=element_curves)
    content_bbox_q = [
        round(min((p[0] for p in ptsn), default=0.0), 3),
        round(min((p[1] for p in ptsn), default=0.0), 3),
        round(max((p[0] for p in ptsn), default=0.0), 3),
        round(max((p[1] for p in ptsn), default=0.0), 3),
    ]
    center_graph_hash = layout.get("center_graph_hash", "")

    source_scope = source_doc_id or source_doc_name or "<no-doc>"
    state_payload = {
        "view_id": view.Id.IntegerValue,
        "view_kind": kind,
        "source_scope": source_scope,
        "content_bbox_q": content_bbox_q,
        "element_count": len(all_elements),
        "type_count": len(symbol_multiset),
        "curve_count_est": len(curves),
        "symbol_instance_count": int(sum(symbol_multiset.values())),
        "center_graph_hash": center_graph_hash,
        "token_signature": token_signature,
        "view_settings_sig": _view_settings_signature(view),
        "pipeline_version": CONFIG["pipeline_version"],
        "search_schema_version": SEARCH_SCHEMA_VERSION,
    }
    state_hash = _stable_json_hash(state_payload)

    return {
        "kind": kind,
        "source_doc_id": source_doc_id,
        "source_doc_name": source_doc_name,
        "raw_tokens": raw_tokens,
        "curves": curves,
        "ptsn": ptsn,
        "scale": scale,
        "all_elements": all_elements,
        "covered_instance_ids": covered_instance_ids,
        "total_family_instances": total_family_instances,
        "layout": layout,
        "tokens_stable": tokens_stable,
        "tokens_context": tokens_context,
        "counts_by_kind": counts_by_kind,
        "symbol_multiset": symbol_multiset,
        "content_bbox_q": content_bbox_q,
        "center_graph_hash": center_graph_hash,
        "state_payload": state_payload,
        "state_hash": state_hash,
    }


def element_base_info(element):
    return {
        "element_id": getattr(getattr(element, "Id", None), "IntegerValue", None),
        "class_name": class_name(element),
        "category": collect_safe_name(getattr(element, "Category", None), fallback="<none>"),
    }


def collect_token_data_for_view(view, kind, tokens=None, include_element_report=False, elements=None):
    token_store = tokens if tokens is not None else new_token_store()
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
        increment(summary, "elements_seen_total")
        if collected:
            increment(summary, "elements_collected_total")
        increment(summary["count_by_collection_group"], group)
        increment(summary["count_by_class_name"], class_name(element))
        if added_tokens:
            increment(summary, "elements_with_tokens")
        else:
            increment(summary, "elements_without_tokens")

        if include_element_report:
            geom_summary = geometry_summary_for_element(element, view=view)
            if geom_summary.get("curve_count", 0) == 0:
                geom_summary["note"] = (
                    "No extractable curves from element geometry in current view/context"
                )
            row = element_base_info(element)
            row.update(
                {
                    "collection_group": group,
                    "collected": bool(collected),
                    "collected_info": dict(info, tokens_added=added_tokens),
                    "geometry_summary": geom_summary,
                }
            )
            element_report.append(row)

    if kind == "DETAIL_MODEL":
        for elem in get_model_elements_contributing_to_view(view, elements=elements):
            cat_name = collect_safe_name(elem.Category, "<no-category>")
            tsig = type_signature(elem)
            category_emitted = emit_token(token_store, "category", cat_name, "category")
            type_emitted = emit_token(token_store, "type_sig", tsig, "type_sig")
            record_row(
                elem,
                "model_elements",
                {"category_name": cat_name, "type_signature": tsig},
                [t for t in (category_emitted, type_emitted) if t],
                collected=True,
            )
    else:
        source_elements = elements if elements is not None else get_view_elements(view)
        for elem in source_elements:
            if not is_annotation_like(elem):
                continue
            added_tokens = []
            info = {}
            group = "annotation_elements_unmapped"

            if is_family_instance(elem):
                value = family_type_sig(elem)
                emitted = emit_token(token_store, "detail_component", value, "detail_component")
                if emitted is not None:
                    added_tokens.append(emitted)
                info["detail_component_sig"] = value
                info["element_type_name"] = safe_type_name(elem)
                group = "annotation_detail_components"
            elif is_filled_region(elem):
                type_name = safe_type_name(elem)
                emitted = emit_token(token_store, "fill_region", type_name, "fill_region")
                if emitted is not None:
                    added_tokens.append(emitted)
                info["fill_region_name"] = type_name
                group = "annotation_filled_regions"
            elif is_dimension(elem):
                try:
                    type_name = safe_name(elem.DimensionType)
                except Exception:
                    type_name = None
                if not is_valid_token_value(type_name):
                    type_name = safe_type_name(elem)
                emitted = emit_token(token_store, "dim_style", type_name, "dim_style")
                if emitted is not None:
                    added_tokens.append(emitted)
                info["dimension_style"] = type_name
                info["dimension_type_name"] = type_name
                group = "annotation_dimensions"
            elif is_text_note(elem):
                try:
                    type_name = safe_name(elem.TextNoteType)
                except Exception:
                    type_name = None
                if not is_valid_token_value(type_name):
                    type_name = safe_type_name(elem)
                emitted = emit_token(token_store, "text_type", type_name, "text_type")
                if emitted is not None:
                    added_tokens.append(emitted)
                info["text_type"] = type_name
                info["text_type_name"] = type_name
                group = "annotation_text_notes"
            elif is_curve_annotation(elem):
                value = safe_name(getattr(elem, "LineStyle", None))
                emitted = emit_token(token_store, "line_style", value, "line_style")
                if emitted is not None:
                    added_tokens.append(emitted)
                info["line_style"] = value
                group = "annotation_lines"

            if not added_tokens:
                info["reason"] = (
                    "token filtered by stopword policy or element is not mapped to a token strategy"
                )
                info["category_name"] = category_name(elem)

            record_row(elem, group, info, added_tokens, collected=True)

    return dict(token_store), element_report, summary


def extract_feature_bundle(view, state_ctx=None):
    ctx = state_ctx or _build_state_context(view)

    kind = ctx["kind"]
    source_doc_id = ctx["source_doc_id"]
    source_doc_name = ctx["source_doc_name"]
    curves = ctx["curves"]
    ptsn = ctx["ptsn"]
    scale = ctx["scale"]
    layout = dict(ctx["layout"])
    tokens_stable = ctx["tokens_stable"]
    tokens_context = ctx["tokens_context"]
    counts_by_kind = ctx["counts_by_kind"]
    symbol_multiset = ctx["symbol_multiset"]
    content_bbox_q = ctx["content_bbox_q"]
    center_graph_hash = ctx["center_graph_hash"]

    geom_fp = geom_fingerprint_knn(
        ptsn,
        k=CONFIG["kNN_k"],
        len_bins=CONFIG["len_bins"],
        ang_bins=CONFIG["ang_bins_deg"],
    )

    orientation_hist = _orientation_hist(curves)
    length_hist = _normalized_length_hist(curves, scale)

    fine = build_fine_metrics(curves, ptsn)
    covered_instance_ids = set(ctx.get("covered_instance_ids", set()))
    total_family_instances = int(ctx.get("total_family_instances", 0))
    fine.update(
        {
            "curve_count": float(len(curves)),
            "line_length_total_norm": float(
                sum(getattr(c, "Length", 0.0) for c in curves) / max(scale, 1e-9)
            ),
            "orientation_entropy": float(
                -sum(v * math.log(max(v, 1e-12), 2) for v in orientation_hist if v > 0.0)
            ),
            "component_count_est": float(layout.get("component_count_est", 0.0)),
            "text_note_count": float(counts_by_kind.get("text_type", 0)),
            "dimension_count": float(counts_by_kind.get("dim_style", 0)),
            "symbol_instance_count": float(sum(symbol_multiset.values())),
            "raster_geometry_coverage": float(len(covered_instance_ids)) / float(max(total_family_instances, 1)),
        }
    )

    state_payload = dict(ctx["state_payload"])
    state_hash = ctx["state_hash"]

    state_signature = ViewStateSignature(
        view_id=view.Id.IntegerValue,
        view_kind=kind,
        source_doc_id=source_doc_id,
        source_doc_name=source_doc_name,
        content_bbox_q=content_bbox_q,
        element_count=len(ctx["all_elements"]),
        type_count=len(symbol_multiset),
        curve_count_est=len(curves),
        symbol_instance_count=int(sum(symbol_multiset.values())),
        center_graph_hash=center_graph_hash,
        view_settings_sig=state_payload["view_settings_sig"],
        state_hash=state_hash,
        debug={
            "pt_count": len(ptsn),
            "curve_count": len(curves),
            "token_signature": state_payload["token_signature"],
        },
    )

    search_features = ViewSearchFeatures(
        view_id=view.Id.IntegerValue,
        view_kind=kind,
        source_doc_id=source_doc_id,
        source_doc_name=source_doc_name,
        tokens_stable=tokens_stable,
        tokens_context=tokens_context,
        token_counts_by_kind=counts_by_kind,
        geom_hist_knn_endpoints=geom_fp,
        geom_orientation_hist=orientation_hist,
        geom_length_hist=length_hist,
        layout_graph_features={k: v for k, v in layout.items() if k != "center_graph_hash"},
        fine_metrics=fine,
        symbol_multiset=symbol_multiset,
        symbol_counts={"total": int(sum(symbol_multiset.values())), "unique": len(symbol_multiset)},
        debug={"scale": scale, "pt_count": len(ptsn)},
    )

    token_scores = sorted(
        ((k, v) for k, v in {**tokens_stable, **tokens_context}.items()),
        key=lambda row: (-row[1], row[0]),
    )
    top_symbols = sorted(symbol_multiset.items(), key=lambda row: (-row[1], row[0]))
    presentation = ViewPresentationSummary(
        view_id=view.Id.IntegerValue,
        source_doc_id=source_doc_id,
        source_doc_name=source_doc_name,
        display_name=view_label(view),
        preview_key="view:{}:{}".format(view.Id.IntegerValue, state_hash[:12]),
        top_tokens=[k for k, _ in token_scores[:8]],
        top_symbols=["{} ({})".format(k, v) for k, v in top_symbols[:8]],
        feature_summary={
            "kind": kind,
            "curve_count": len(curves),
            "symbol_instances": int(sum(symbol_multiset.values())),
            "layout_nodes": int(layout.get("node_count", 0.0)),
        },
    )

    return ViewFeatureBundle(
        state_signature=state_signature,
        search_features=search_features,
        presentation_summary=presentation,
    )


def extract_features(view):
    """Compatibility wrapper around v0.3 bundle extraction."""

    bundle = extract_feature_bundle(view)
    return legacy_view_features_from_search(bundle.search_features)


def _extract_bundle_with_cache(view, write_legacy_cache_record=True, symbol_raster_lookup_callback=None):
    state_ctx = _build_state_context(view, symbol_raster_lookup_callback=symbol_raster_lookup_callback)
    cache_root = resolve_view_cache_root(CONFIG)
    cached, status = get_cached_bundle_with_diagnostics(
        in_memory_cache=GLOBAL_VIEW_FEATURE_CACHE,
        cache_root=cache_root,
        view_id=view.Id.IntegerValue,
        state_hash=state_ctx["state_hash"],
        pipeline_version=CONFIG["pipeline_version"],
        schema_version=SEARCH_SCHEMA_VERSION,
        source_doc_id=state_ctx.get("source_doc_id"),
        source_doc_name=state_ctx.get("source_doc_name"),
    )
    if cached is not None:
        cached.presentation_summary.debug["cache_status"] = status
        return cached, status

    fresh_bundle = extract_feature_bundle(view, state_ctx=state_ctx)
    put_bundle_in_caches(
        in_memory_cache=GLOBAL_VIEW_FEATURE_CACHE,
        cache_root=cache_root,
        view_id=fresh_bundle.state_signature.view_id,
        state_hash=fresh_bundle.state_signature.state_hash,
        pipeline_version=CONFIG["pipeline_version"],
        schema_version=SEARCH_SCHEMA_VERSION,
        payload=fresh_bundle,
        write_disk=write_legacy_cache_record,
    )
    cache_status = "rebuilt" if status == "miss" else status
    fresh_bundle.presentation_summary.debug["cache_status"] = cache_status
    return fresh_bundle, cache_status


def _build_contact_folder_for_results(query_view, query_bundle, ranked_rows, run_id=None):
    if not ranked_rows:
        return None

    seed_preview = generate_and_cache_view_preview(
        query_view,
        CONFIG,
        source_doc_id=query_bundle.search_features.source_doc_id,
        source_doc_name=query_bundle.search_features.source_doc_name,
    )
    seed = {
        "view_id": query_bundle.search_features.view_id,
        "display_name": query_bundle.presentation_summary.display_name,
        "preview_path": seed_preview,
    }

    candidates = []
    for row in ranked_rows:
        cand_id = int(row.get("candidate_view_id", 0))
        cand_preview = row.get("preview_path")
        ps = row.get("presentation_summary") or {}
        candidates.append(
            {
                "seed_view_id": int(seed["view_id"]),
                "seed_display_name": seed["display_name"],
                "candidate_view_id": cand_id,
                "candidate_display_name": ps.get("display_name") or "VIEW {}".format(cand_id),
                "rank": int(row.get("rank", 0)),
                "total_score": float(row.get("score_total", 0.0)),
                "token_score": float(row.get("score_tokens", 0.0)),
                "geometry_score": float(row.get("score_geom", 0.0)),
                "layout_score": float((ps.get("feature_summary") or {}).get("layout_nodes", 0.0)),
                "symbol_score": 0.0,
                "confidence_level": str(row.get("confidence_tier", "LOW")).lower(),
                "source_doc": ps.get("source_doc_name"),
                "preview_path": cand_preview,
            }
        )

    return create_contact_folder(seed, candidates, CONFIG, run_id=run_id)


def _load_all_cached_bundles(cache_root):
    cache_dir = os.path.join(cache_root, "view_features")
    if not os.path.isdir(cache_dir):
        return []

    bundles = []
    seen = set()
    try:
        filenames = sorted(
            name for name in os.listdir(cache_dir) if name.startswith("view_") and name.endswith(".json")
        )
    except Exception as exc:
        raise RuntimeError("DSE: failed to list cached bundle files in _load_all_cached_bundles") from exc

    for filename in filenames:
        path = os.path.join(cache_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                entry = deserialize_cache_entry(handle.read())
        except Exception as exc:
            warnings.warn(
                "DSE: failed to parse cached bundle in _load_all_cached_bundles: {}".format(exc),
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        if entry.schema_version != SEARCH_SCHEMA_VERSION:
            continue
        if entry.pipeline_version != CONFIG["pipeline_version"]:
            continue
        payload = entry.payload
        uniq = (_bundle_source_scope(payload), int(payload.search_features.view_id), payload.state_signature.state_hash)
        if uniq in seen:
            continue
        seen.add(uniq)
        bundles.append(payload)
    return bundles




def _extract_bundle_for_index(view, symbol_raster_lookup_callback=None):
    return _extract_bundle_with_cache(
        view,
        write_legacy_cache_record=False,
        symbol_raster_lookup_callback=symbol_raster_lookup_callback,
    )

def index_views(views):
    cache_root = resolve_view_cache_root(CONFIG)
    statuses = {}
    indexed = 0
    skipped = 0
    preview_failures = 0
    accum = IndexDiagnosticAccumulator()
    index_sidecar_path = resolve_index_sidecar_path(CONFIG)
    index_jsonl_path = index_sidecar_path.replace(".json", "_views.jsonl")
    os.makedirs(os.path.dirname(index_jsonl_path), exist_ok=True)
    with open(index_jsonl_path, "w", encoding="utf-8"):
        pass
    for view in views:
        if not is_view(view):
            skipped += 1
            continue
        extraction_start = time.perf_counter()
        try:
            bundle, status = _extract_bundle_for_index(
                view,
                symbol_raster_lookup_callback=accum.accumulate_symbol_raster_lookup,
            )
        except Exception as exc:
            accum.accumulate_error(getattr(getattr(view, "Id", None), "IntegerValue", None), view_label(view), str(exc))
            raise
        extraction_ms = (time.perf_counter() - extraction_start) * 1000.0
        bundle.presentation_summary.debug["extraction_ms"] = extraction_ms
        accum.accumulate_view_timing(
            bundle.search_features.view_id,
            bundle.presentation_summary.display_name,
            extraction_ms,
        )
        accum.accumulate(bundle, status)
        if status not in ("hit_disk", "hit_memory"):
            _write_doc_scoped_cache_record(cache_root, bundle)
        accum.flush_view_record(index_jsonl_path, bundle, status)
        try:
            preview_path = generate_and_cache_view_preview(
                view,
                CONFIG,
                source_doc_id=bundle.search_features.source_doc_id,
                source_doc_name=bundle.search_features.source_doc_name,
            )
            if preview_path is None:
                preview_failures += 1
        except Exception as exc:
            warnings.warn(
                "DSE: failed to generate preview in index_views: {}".format(exc),
                RuntimeWarning,
                stacklevel=2,
            )
            preview_failures += 1
        view_id = int(bundle.search_features.view_id)
        statuses[view_id] = status
        indexed += 1

    # index_views does not build IDF; empty token_idf/token_df is expected here.
    index_payload = accum.finalize(token_idf={}, token_df={}, config=CONFIG)
    write_json_sidecar(index_sidecar_path, index_payload)
    return {
        "indexed": indexed,
        "skipped": skipped,
        "cache_statuses": statuses,
        "preview_failures": preview_failures,
        "index_sidecar": index_sidecar_path,
        "index_jsonl": index_jsonl_path,
    }
def find_similar_views(query_view, top_n=5):
    run_id = run_stamp("run")
    diag = SearchDiagnosticBuilder(run_id=run_id)
    index_accum = IndexDiagnosticAccumulator()

    diag.start_timer("state_context_build")
    query_bundle, query_status = _extract_bundle_with_cache(query_view)
    diag.stop_timer("state_context_build")
    query_bundle.presentation_summary.debug["cache_status"] = query_status

    generate_and_cache_view_preview(
        query_view,
        CONFIG,
        source_doc_id=query_bundle.search_features.source_doc_id,
        source_doc_name=query_bundle.search_features.source_doc_name,
    )
    query_features = legacy_view_features_from_search(query_bundle.search_features)
    seed_ok, seed_reason = check_feature_richness(
        query_features,
        query_bundle.search_features.view_id,
        query_bundle.presentation_summary.display_name,
    )
    if not seed_ok:
        raise ValueError(seed_reason)
    cache_root = resolve_view_cache_root(CONFIG)

    diag.start_timer("corpus_feature_extraction_total")
    corpus_errors = 0
    cache_statuses = {}
    corpus_bundles = []
    corpus_feat = []
    corpus_richness_skips = []
    for bundle in _load_all_cached_bundles(cache_root):
        if int(bundle.search_features.view_id) == int(query_features.view_id):
            continue
        candidate = legacy_view_features_from_search(bundle.search_features)
        is_rich, reason = check_feature_richness(
            candidate,
            bundle.search_features.view_id,
            bundle.presentation_summary.display_name,
        )
        if not is_rich:
            corpus_richness_skips.append(
                {
                    "view_id": int(bundle.search_features.view_id),
                    "view_name": bundle.presentation_summary.display_name,
                    "reason": reason,
                }
            )
            continue
        status = str(bundle.presentation_summary.debug.get("cache_status", "hit_disk"))
        cache_statuses[status] = cache_statuses.get(status, 0) + 1
        index_accum.accumulate(bundle, status)
        corpus_bundles.append(bundle)
        corpus_feat.append(candidate)
    diag.stop_timer("corpus_feature_extraction_total")
    diag.timings["corpus_extract_per_view_avg_ms"] = (
        diag.timings["corpus_feature_extraction_total"] / max(1, len(corpus_bundles))
    )

    diag.start_timer("idf_build")
    token_df, doc_count = build_token_df_from_features(corpus_feat)
    token_idf = build_token_idf(token_df, doc_count)
    default_idf = default_idf_for_doc_count(doc_count)
    diag.stop_timer("idf_build")

    index_sidecar_path = resolve_index_sidecar_path(CONFIG)
    index_payload = index_accum.finalize(token_idf, token_df, CONFIG)
    write_json_sidecar(index_sidecar_path, index_payload)

    min_token_threshold = derive_min_token_threshold(corpus_feat)

    diag.start_timer("pairwise_scoring_total")
    results = []
    for idx, candidate in enumerate(corpus_feat):
        bundle = corpus_bundles[idx]
        weights = effective_weights(
            query_features, candidate, min_token_threshold=min_token_threshold
        )
        s_tokens = token_similarity(
            query_features.tokens,
            candidate.tokens,
            token_idf=token_idf,
            default_idf=default_idf,
        )
        s_geom = cosine_similarity(query_features.geom_fingerprint, candidate.geom_fingerprint)
        query_symbols = query_bundle.search_features.symbol_multiset
        candidate_symbols = bundle.search_features.symbol_multiset
        symbol_keys = set(query_symbols.keys()) | set(candidate_symbols.keys())
        if symbol_keys:
            symbol_inter = 0.0
            symbol_union = 0.0
            for key in symbol_keys:
                qa = float(query_symbols.get(key, 0))
                cb = float(candidate_symbols.get(key, 0))
                symbol_inter += min(qa, cb)
                symbol_union += max(qa, cb)
            s_symbol = 0.0 if symbol_union <= 0.0 else symbol_inter / symbol_union
        else:
            s_symbol = 1.0
        s_fine = fine_similarity(query_features.fine_metrics, candidate.fine_metrics)
        s_total = (
            weights["w_tokens"] * s_tokens
            + weights["w_geom"] * s_geom
            + weights["w_fine"] * s_fine
        )
        # s_symbol here is the stage-1 feature-layer symbol overlap score (from search_features.symbol_multiset),
        # not stage-2 descriptor-based symbol_multiset_similarity.
        s_total = apply_geom_dominant_suppression(s_total, s_tokens, s_geom, s_symbol)
        results.append(
            {
                "candidate_view_id": candidate.view_id,
                "candidate_source_doc_id": bundle.search_features.source_doc_id,
                "candidate_source_doc_name": bundle.search_features.source_doc_name,
                "score_total": s_total,
                "score_tokens": s_tokens,
                "score_geom": s_geom,
                "score_fine": s_fine,
                "confidence_tier": confidence_tier(s_total),
                "explanation": explain_match(query_features, candidate),
                "presentation_summary": bundle.presentation_summary.__dict__,
            }
        )
    diag.stop_timer("pairwise_scoring_total")

    results.sort(key=lambda r: (-r["score_total"], r["candidate_view_id"]))
    trimmed = results[: max(0, int(top_n))]
    for idx, row in enumerate(trimmed, 1):
        row["rank"] = idx
        row["preview_path"] = get_cached_view_preview(
            row["candidate_view_id"],
            CONFIG,
            source_doc_id=row.pop("candidate_source_doc_id", None),
            source_doc_name=row.pop("candidate_source_doc_name", None),
        )

    diag.start_timer("contact_folder_write")
    contact = _build_contact_folder_for_results(query_view, query_bundle, trimmed, run_id=run_id)
    diag.stop_timer("contact_folder_write")

    sidecar_path = None
    config_snapshot = build_config_snapshot(CONFIG)
    search_payload = diag.build(
        query_bundle=query_bundle,
        corpus_size=len(corpus_bundles),
        corpus_errors=corpus_errors,
        cache_statuses=cache_statuses,
        config_snapshot=config_snapshot,
        token_idf=token_idf,
        default_idf=default_idf,
        all_scored=results,
        top_results=trimmed,
        stage2_available=False,
        min_token_threshold=min_token_threshold,
    )
    search_payload["corpus"]["feature_richness_skipped_count"] = len(corpus_richness_skips)
    search_payload["corpus"]["feature_richness_skips"] = corpus_richness_skips
    if contact is not None:
        sidecar_path = resolve_search_sidecar_path(contact["contact_folder"])
        write_json_sidecar(sidecar_path, search_payload)
        for row in trimmed:
            row["contact_folder"] = contact.get("contact_folder")
            row["contact_results_path"] = contact.get("results_path")
            row["runs_index_path"] = contact.get("runs_index")
            row["run_id"] = contact.get("run_id")

    for row in trimmed:
        row["search_sidecar"] = sidecar_path
        row["index_sidecar"] = index_sidecar_path
    return trimmed
def find_similar_views_many_to_many(top_k=None, skip_self=None, dedupe=None, write_output=None):
    top_k = int(top_k if top_k is not None else CONFIG.get("many_to_many", {}).get("top_k", 5))
    skip_self_mode = (
        bool(skip_self)
        if skip_self is not None
        else bool(CONFIG.get("many_to_many", {}).get("skip_self", True))
    )
    dedupe_mode = (
        bool(dedupe)
        if dedupe is not None
        else bool(CONFIG.get("many_to_many", {}).get("symmetric_dedupe", False))
    )
    write_mode = (
        bool(write_output)
        if write_output is not None
        else bool(CONFIG.get("many_to_many", {}).get("write_output", True))
    )

    cache_root = resolve_view_cache_root(CONFIG)
    cached_bundles = _load_all_cached_bundles(cache_root)
    rows = []
    for bundle in cached_bundles:
        legacy = legacy_view_features_from_search(bundle.search_features)
        rows.append(
            {
                "view_id": legacy.view_id,
                "display_name": bundle.presentation_summary.display_name,
                "source_doc_id": bundle.search_features.source_doc_id,
                "source_doc_name": bundle.search_features.source_doc_name,
                "tokens": legacy.tokens,
                "geom_fingerprint": legacy.geom_fingerprint,
                "fine_metrics": legacy.fine_metrics,
                "layout_graph_features": bundle.search_features.layout_graph_features,
                "symbol_multiset": bundle.search_features.symbol_multiset,
            }
        )

    edges = build_many_to_many_edges(
        rows,
        top_k=top_k,
        skip_self=skip_self_mode,
        symmetric_dedupe=dedupe_mode,
    )
    output = None
    if write_mode:
        output = write_many_to_many_outputs(edges, CONFIG)
    return {"rows": edges, "output": output}


def view_label(view):
    try:
        return view.Name
    except Exception:
        return "<unknown>"


def check_feature_richness(features, view_id, view_name):
    cfg = CONFIG.get("feature_richness_filter", {})
    if not bool(cfg.get("enabled", True)):
        return True, None

    min_curve_count = int(cfg.get("min_curve_count", 3))
    min_non_text_tokens = int(cfg.get("min_non_text_tokens", 2))

    curve_count_raw = (features.fine_metrics or {}).get("curve_count")
    if curve_count_raw is None:
        pt_count = (features.fine_metrics or {}).get("pt_count")
        if pt_count is not None:
            curve_count = int(max(0, math.ceil(float(pt_count) / 2.0)))
        else:
            curve_count = 0
    else:
        curve_count = int(float(curve_count_raw))
    non_text_tokens = sum(
        1 for key in (features.tokens or {}).keys() if not str(key).startswith("text_type:")
    )

    if curve_count < min_curve_count or non_text_tokens < min_non_text_tokens:
        reason = (
            "feature_richness_filter failed for view {} ({}) "
            "[curve_count={} < min_curve_count={} or non_text_tokens={} < min_non_text_tokens={}]"
        ).format(view_id, view_name, curve_count, min_curve_count, non_text_tokens, min_non_text_tokens)
        return False, reason
    return True, None


def sample_view_fingerprints(views, sample_size, seed=0):
    clean_views = [v for v in views if is_view(v)]
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
    for view in sampled:
        bundle, _status = _extract_bundle_with_cache(view)
        feat = legacy_view_features_from_search(bundle.search_features)
        _, element_report, collection_summary = collect_token_data_for_view(
            view, feat.view_kind, include_element_report=True
        )
        report.append(
            {
                "view_id": feat.view_id,
                "view_name": view_label(view),
                "view_kind": feat.view_kind,
                "tokens": feat.tokens,
                "geom_fingerprint": feat.geom_fingerprint,
                "fine_metrics": feat.fine_metrics,
                "debug": feat.debug,
                "state_signature": bundle.state_signature.__dict__,
                "search_features": bundle.search_features.__dict__,
                "presentation_summary": bundle.presentation_summary.__dict__,
                "collected_elements": element_report,
                "collection_summary": collection_summary,
                "token_assignment_policy": token_assignment_policy(CONFIG, TOKEN_STOPWORDS),
            }
        )

    report.sort(key=lambda r: r["view_id"])
    return report
