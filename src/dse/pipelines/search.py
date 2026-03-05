import random
from dse.config import CONFIG, TOKEN_STOPWORDS, default_idf_for_doc_count
from dse.features.fine_metrics import build_fine_metrics
from dse.features.geom_fingerprint import geom_fingerprint_knn, robust_scale
from dse.features.idf import build_token_df_from_features, build_token_idf
from dse.features.tokens import (
    emit_token,
    family_type_sig,
    new_token_store,
    safe_name,
    safe_type_name,
    type_signature,
)
from dse.models import ViewFeatures
from dse.ranking.similarity import (
    confidence_tier,
    cosine_similarity,
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
    endpoints_from_curves,
    geometry_summary_for_element,
    get_2d_curves_in_view,
    to_view_local_2d,
)


def element_base_info(element):
    return {
        "element_id": getattr(getattr(element, "Id", None), "IntegerValue", None),
        "class_name": class_name(element),
        "category": collect_safe_name(getattr(element, "Category", None), fallback="<none>"),
    }


def collect_token_data_for_view(view, kind, tokens=None, include_element_report=False):
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
                geom_summary["note"] = "No extractable curves from element geometry in current view/context"
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
        for elem in get_model_elements_contributing_to_view(view):
            cat_name = collect_safe_name(elem.Category, "<no-category>")
            type_sig = type_signature(elem)
            category_emitted = emit_token(token_store, "category", cat_name, "category")
            type_emitted = emit_token(token_store, "type_sig", type_sig, "type_sig")
            record_row(
                elem,
                "model_elements",
                {"category_name": cat_name, "type_signature": type_sig},
                [t for t in (category_emitted, type_emitted) if t],
                collected=True,
            )
    else:
        for elem in get_view_elements(view):
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
                value = safe_name(elem)
                emitted = emit_token(token_store, "fill_region", value, "fill_region")
                if emitted is not None:
                    added_tokens.append(emitted)
                info["fill_region_name"] = value
                group = "annotation_filled_regions"
            elif is_dimension(elem):
                value = safe_name(getattr(elem, "DimensionType", None))
                emitted = emit_token(token_store, "dim_style", value, "dim_style")
                if emitted is not None:
                    added_tokens.append(emitted)
                info["dimension_style"] = value
                info["dimension_type_name"] = safe_type_name(elem)
                group = "annotation_dimensions"
            elif is_text_note(elem):
                value = safe_name(getattr(elem, "TextNoteType", None))
                emitted = emit_token(token_store, "text_type", value, "text_type")
                if emitted is not None:
                    added_tokens.append(emitted)
                info["text_type"] = value
                info["text_type_name"] = safe_type_name(elem)
                group = "annotation_text_notes"
            elif is_curve_annotation(elem):
                value = safe_name(getattr(elem, "LineStyle", None))
                emitted = emit_token(token_store, "line_style", value, "line_style")
                if emitted is not None:
                    added_tokens.append(emitted)
                info["line_style"] = value
                group = "annotation_lines"

            if not added_tokens:
                info["reason"] = "token filtered by stopword policy or element is not mapped to a token strategy"
                info["category_name"] = category_name(elem)

            record_row(elem, group, info, added_tokens, collected=True)

    return dict(token_store), element_report, summary


def extract_features(view):
    kind = classify_view_kind(view)
    tokens, _, _ = collect_token_data_for_view(view, kind, include_element_report=False)

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

    fine = build_fine_metrics(curves, ptsn)

    return ViewFeatures(
        view_id=view.Id.IntegerValue,
        view_kind=kind,
        tokens=dict(tokens),
        geom_fingerprint=geom_fp,
        fine_metrics=fine,
        debug={"scale": scale, "pt_count": len(ptsn)},
    )


def find_similar_views(query_view, corpus_views, top_n=5):
    query_features = extract_features(query_view)
    corpus_feat = [extract_features(v) for v in corpus_views if is_view(v) and v.Id != query_view.Id]

    token_df, doc_count = build_token_df_from_features(corpus_feat)
    token_idf = build_token_idf(token_df, doc_count)
    default_idf = default_idf_for_doc_count(doc_count)

    results = []
    for candidate in corpus_feat:
        weights = effective_weights(query_features, candidate)
        s_tokens = token_similarity(
            query_features.tokens,
            candidate.tokens,
            token_idf=token_idf,
            default_idf=default_idf,
        )
        s_geom = cosine_similarity(query_features.geom_fingerprint, candidate.geom_fingerprint)
        s_fine = fine_similarity(query_features.fine_metrics, candidate.fine_metrics)
        s_total = (
            weights["w_tokens"] * s_tokens
            + weights["w_geom"] * s_geom
            + weights["w_fine"] * s_fine
        )
        results.append(
            {
                "candidate_view_id": candidate.view_id,
                "score_total": s_total,
                "score_tokens": s_tokens,
                "score_geom": s_geom,
                "score_fine": s_fine,
                "confidence_tier": confidence_tier(s_total),
                "explanation": explain_match(query_features, candidate),
            }
        )

    results.sort(key=lambda r: (-r["score_total"], r["candidate_view_id"]))
    return results[: max(0, int(top_n))]


def view_label(view):
    try:
        return view.Name
    except Exception:
        return "<unknown>"


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
        feat = extract_features(view)
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
                "collected_elements": element_report,
                "collection_summary": collection_summary,
                "token_assignment_policy": token_assignment_policy(CONFIG, TOKEN_STOPWORDS),
            }
        )

    report.sort(key=lambda r: r["view_id"])
    return report
