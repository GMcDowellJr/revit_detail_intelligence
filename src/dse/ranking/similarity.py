import math

from dse.config import CONFIG, EPS


def token_similarity(tokens_a, tokens_b, token_idf=None, default_idf=1.0):
    keys = set(tokens_a.keys()) | set(tokens_b.keys())
    if not keys:
        return 0.0
    idf_map = token_idf or {}
    num = 0.0
    den = 0.0
    for key in keys:
        a = tokens_a.get(key, 0.0)
        b = tokens_b.get(key, 0.0)
        idf = idf_map.get(key, default_idf)
        wa = a * idf
        wb = b * idf
        num += min(wa, wb)
        den += max(wa, wb)
    return 0.0 if den <= EPS else num / den


def cosine_similarity(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(a[index] * b[index] for index in range(len(a)))
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


def fine_similarity(fa, fb):
    if not fa or not fb:
        return 0.5
    s1 = gaussian_sim(fa.get("bbox_aspect", 1.0), fb.get("bbox_aspect", 1.0), sigma=0.5)
    s2 = gaussian_sim(fa.get("linework_density", 0.0), fb.get("linework_density", 0.0), sigma=0.5)
    return 0.5 * s1 + 0.5 * s2


def derive_min_token_threshold(corpus_features):
    sizes = sorted(len(feature.tokens) for feature in corpus_features)
    floor = int(CONFIG.get("min_token_threshold_floor", CONFIG.get("min_token_threshold", 4)))
    ceiling = int(CONFIG.get("min_token_threshold_ceiling", floor))
    percentile = float(CONFIG.get("min_token_threshold_percentile", 10))
    if not sizes:
        return max(floor, min(ceiling, int(CONFIG.get("min_token_threshold", floor))))
    idx = int((max(0.0, min(100.0, percentile)) / 100.0) * (len(sizes) - 1))
    raw = sizes[idx]
    return max(floor, min(ceiling, raw))


def effective_weights(query_features, candidate_features, min_token_threshold=None):
    min_tokens = int(
        min_token_threshold
        if min_token_threshold is not None
        else CONFIG.get("min_token_threshold", 4)
    )
    if len(query_features.tokens) < min_tokens or len(candidate_features.tokens) < min_tokens:
        return CONFIG.get("low_semantic_weights", CONFIG["weights"])
    return CONFIG["weights"]


def apply_geom_dominant_suppression(score_total, s_tokens, s_geom, s_symbol):
    cfg = CONFIG.get("geom_dominant_suppression", {})
    if not bool(cfg.get("enabled", False)):
        return score_total
    if (
        s_geom > float(cfg.get("geom_min", 0.65))
        and s_tokens < float(cfg.get("tok_max", 0.25))
        and s_symbol < float(cfg.get("symbol_max", 0.25))
    ):
        return score_total * float(cfg.get("penalty_factor", 0.65))
    return score_total


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


def explain_match(query_features, candidate_features):
    common = set(query_features.tokens.keys()) & set(candidate_features.tokens.keys())
    token_contrib = [
        (k, min(query_features.tokens[k], candidate_features.tokens[k])) for k in common
    ]
    token_contrib.sort(key=lambda x: (-x[1], x[0]))
    return {
        "top_shared_tokens": token_contrib[:10],
        "top_shared_geom_bins": top_shared_bins(
            query_features.geom_fingerprint, candidate_features.geom_fingerprint, top=10
        ),
    }
