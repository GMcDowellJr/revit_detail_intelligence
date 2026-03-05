from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional

from dse.cache.symbol_cache import symbol_coverage_for_view, symbol_multiset_similarity


@dataclass
class Stage1Result:
    candidate_view_id: int
    score_total: float
    score_tokens: float
    score_geom: float
    score_fine: float
    confidence_tier: str
    confidence_margin: float = 0.0


@dataclass
class Stage2Result:
    candidate_view_id: int
    score_stage1_total: float
    score_raster: Optional[float]
    score_symbols: Optional[float]
    score_combined: float
    confidence_raster_support: str
    notes: List[str] = field(default_factory=list)


def select_rerank_pool(results: List[Stage1Result], rerank_cfg: Dict[str, float]) -> List[Stage1Result]:
    if not results:
        return []

    mode = rerank_cfg.get("band_mode", "top_k")
    if mode == "score_delta":
        delta = float(rerank_cfg.get("score_delta", 0.10))
        best = results[0].score_total
        return [result for result in results if best - result.score_total <= delta]

    top_k = int(rerank_cfg.get("pool_top_k", 50))
    return results[: max(top_k, 0)]


def stage2_rerank(
    stage1_results: List[Stage1Result],
    query_view_id: int,
    query_symbols,
    symbol_cache,
    view_raster_cache,
    config,
    resolve_view: Callable[[int], object],
    extract_view_symbol_multiset: Callable[[object], Dict[object, int]],
    view_raster_similarity: Callable[[object, object], float],
    build_view_raster_signature: Callable[[object], Optional[object]],
) -> List[Stage2Result]:
    rerank_cfg = config["stage2_rerank"]
    confidence_cfg = config["confidence_policy"]

    pool = select_rerank_pool(stage1_results, rerank_cfg)

    query_sig = view_raster_cache.get(query_view_id)
    if query_sig is None and rerank_cfg.get("min_view_raster_available", True):
        query_sig = build_view_raster_signature(resolve_view(query_view_id))
        if query_sig is not None:
            view_raster_cache[query_view_id] = query_sig

    query_cov = symbol_coverage_for_view(query_symbols, symbol_cache)

    out: List[Stage2Result] = []
    for row in pool:
        if row.score_total < float(rerank_cfg.get("require_min_stage1_score", 0.25)):
            out.append(
                Stage2Result(
                    candidate_view_id=row.candidate_view_id,
                    score_stage1_total=row.score_total,
                    score_raster=None,
                    score_symbols=None,
                    score_combined=row.score_total,
                    confidence_raster_support="NONE",
                    notes=["stage1_below_min; no rerank"],
                )
            )
            continue

        notes = []
        candidate_view = resolve_view(row.candidate_view_id)
        candidate_symbols = extract_view_symbol_multiset(candidate_view)
        candidate_cov = symbol_coverage_for_view(candidate_symbols, symbol_cache)

        score_symbols = None
        if min(query_cov, candidate_cov) >= float(rerank_cfg.get("min_symbol_coverage", 0.70)):
            score_symbols = symbol_multiset_similarity(query_symbols, candidate_symbols, symbol_cache)
        else:
            notes.append("low_symbol_coverage")

        score_raster = None
        cand_sig = view_raster_cache.get(row.candidate_view_id)
        if cand_sig is None and rerank_cfg.get("min_view_raster_available", True):
            cand_sig = build_view_raster_signature(candidate_view)
            if cand_sig is not None:
                view_raster_cache[row.candidate_view_id] = cand_sig

        if query_sig is not None and cand_sig is not None:
            score_raster = view_raster_similarity(query_sig, cand_sig)
        else:
            notes.append("missing_view_raster")

        score_combined = row.score_total
        if score_raster is not None:
            score_combined = 0.70 * score_combined + 0.30 * score_raster
        if score_symbols is not None:
            score_combined = 0.60 * score_combined + 0.40 * score_symbols

        support = "NONE"
        if score_raster is not None:
            if score_raster >= float(confidence_cfg.get("raster_support_threshold", 0.90)):
                support = "STRONG"
            elif score_raster >= 0.75:
                support = "WEAK"

        out.append(
            Stage2Result(
                candidate_view_id=row.candidate_view_id,
                score_stage1_total=row.score_total,
                score_raster=score_raster,
                score_symbols=score_symbols,
                score_combined=score_combined,
                confidence_raster_support=support,
                notes=notes,
            )
        )

    return out
