import math

CONFIG = {
    "kNN_k": 3,
    "len_bins": [0.00, 0.10, 0.20, 0.35, 0.50, 0.70, 1.00, 1.40, 2.00, float("inf")],
    "ang_bins_deg": [0, 15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 165, 180],
    "tol_coord": 1.0 / 256.0,
    "weights": {"w_tokens": 0.55, "w_geom": 0.35, "w_fine": 0.10},
    "low_semantic_weights": {"w_tokens": 0.20, "w_geom": 0.70, "w_fine": 0.10},
    "min_token_threshold": 4,
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
    "pipeline_version": "dse.pipeline.v0.2.1",
    "stage2_rerank": {
        "enabled": True,
        "pool_top_k": 50,
        "band_mode": "top_k",
        "score_delta": 0.10,
        "require_min_stage1_score": 0.25,
        "min_symbol_coverage": 0.70,
        "min_view_raster_available": True,
    },
    "confidence_policy": {
        "margin_high": 0.15,
        "margin_med": 0.07,
        "raster_support_threshold": 0.90,
    },
}
EPS = 1e-9
TOKEN_STOPWORDS = {"<none>", "<no-type>", "<unknown-type>", "", "default", "none", "n/a"}


def default_idf_for_doc_count(doc_count):
    return math.log(float(max(1, doc_count)))
