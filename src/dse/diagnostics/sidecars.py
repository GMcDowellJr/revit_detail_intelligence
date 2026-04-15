import hashlib
import json
import os
import time
from datetime import datetime

from dse.config import CONFIG
from dse.io_paths import resolve_cache_root

SEARCH_SIDECAR_SCHEMA = "sidecar.search.1.0"
INDEX_SIDECAR_SCHEMA = "sidecar.index.1.2"
INDEX_VIEWS_JSONL_SCHEMA = "sidecar.index.views.1.0"


def percentile(sorted_values, p):
    if not sorted_values:
        return 0.0
    if p <= 0.0:
        return float(sorted_values[0])
    if p >= 1.0:
        return float(sorted_values[-1])
    idx = (len(sorted_values) - 1) * float(p)
    low = int(idx)
    high = min(low + 1, len(sorted_values) - 1)
    frac = idx - low
    return float(sorted_values[low]) * (1.0 - frac) + float(sorted_values[high]) * frac


def distribution_stats(values):
    if not values:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p95": None,
        }
    sorted_values = sorted(float(value) for value in values)
    count = len(sorted_values)
    return {
        "count": count,
        "min": float(sorted_values[0]),
        "max": float(sorted_values[-1]),
        "mean": float(sum(sorted_values) / float(count)),
        "p25": float(percentile(sorted_values, 0.25)),
        "p50": float(percentile(sorted_values, 0.50)),
        "p75": float(percentile(sorted_values, 0.75)),
        "p95": float(percentile(sorted_values, 0.95)),
    }


def write_json_sidecar(path, payload):
    tmp_path = "{}.tmp".format(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    os.replace(tmp_path, path)


def resolve_search_sidecar_path(contact_folder):
    return os.path.join(contact_folder, "search_diagnostic.json")


def resolve_index_sidecar_path(config):
    return os.path.join(resolve_cache_root(config), "index_diagnostic.json")


def _utc_now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def classify_cache_temperature(unique_symbol_types, new_symbol_types, reused_symbol_types):
    if int(unique_symbol_types) <= 0:
        return "none"
    if int(new_symbol_types) > 0 and int(reused_symbol_types) > 0:
        return "mixed"
    if int(new_symbol_types) > 0:
        return "cold"
    return "warm"


class ViewSymbolRasterPerfAccumulator:
    """Collects symbol-raster lookup diagnostics for one view."""

    def __init__(self):
        self.lookups_total = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.lookup_ms_total = 0.0
        self.lookup_ms_hit_total = 0.0
        self.lookup_ms_miss_total = 0.0
        self.cache_miss_reasons = {}
        self.symbol_types_seen = set()

    def accumulate(self, lookup):
        self.lookups_total += 1
        symbol_type_key = str(lookup.get("symbol_type_key", "<unknown-symbol>"))
        self.symbol_types_seen.add(symbol_type_key)
        elapsed_ms = float(lookup.get("elapsed_ms", 0.0))
        self.lookup_ms_total += elapsed_ms
        was_hit = bool(lookup.get("cache_hit", False))
        if was_hit:
            self.cache_hits += 1
            self.lookup_ms_hit_total += elapsed_ms
            return

        self.cache_misses += 1
        self.lookup_ms_miss_total += elapsed_ms
        reason = str(lookup.get("miss_reason", "unknown"))
        self.cache_miss_reasons[reason] = self.cache_miss_reasons.get(reason, 0) + 1

    def finalize(self, run_seen_symbol_types):
        unique_symbol_types = len(self.symbol_types_seen)
        new_types = {symbol_type for symbol_type in self.symbol_types_seen if symbol_type not in run_seen_symbol_types}
        reused_types = self.symbol_types_seen.difference(new_types)
        summary = {
            "symbol_lookups_total": int(self.lookups_total),
            "symbol_cache_hits": int(self.cache_hits),
            "symbol_cache_misses": int(self.cache_misses),
            "symbol_cache_hit_rate": 0.0
            if self.lookups_total <= 0
            else float(self.cache_hits) / float(self.lookups_total),
            "symbol_lookup_ms_total": float(self.lookup_ms_total),
            "symbol_lookup_ms_hit_total": float(self.lookup_ms_hit_total),
            "symbol_lookup_ms_miss_total": float(self.lookup_ms_miss_total),
            "symbol_cache_miss_reasons": dict(sorted(self.cache_miss_reasons.items())),
            "unique_symbol_types_in_view": int(unique_symbol_types),
            "new_symbol_types_built_in_view": int(len(new_types)),
            "reused_symbol_types_in_view": int(len(reused_types)),
        }
        summary["cache_temperature"] = classify_cache_temperature(
            summary["unique_symbol_types_in_view"],
            summary["new_symbol_types_built_in_view"],
            summary["reused_symbol_types_in_view"],
        )
        run_seen_symbol_types.update(self.symbol_types_seen)
        return summary


class IndexDiagnosticAccumulator:
    """Accumulates per-view stats incrementally as bundles are extracted."""

    def __init__(self):
        self.schema_version = INDEX_SIDECAR_SCHEMA
        self.pipeline_version = CONFIG["pipeline_version"]
        self.view_records = []
        self.corpus_id_parts = []
        self.count_total = 0
        self.count_indexed = 0
        self.count_errored = 0
        self.count_cache_statuses = {}
        self.kind_breakdown = {}
        self.source_docs = set()
        self._symbol_counts = {}
        self._symbol_raster_total = 0
        self._symbol_raster_hits = 0
        self._symbol_raster_misses = 0
        self._symbol_raster_miss_reasons = {}
        self._symbol_raster_hit_ms = []
        self._symbol_raster_miss_ms = []
        self._symbol_raster_types_seen = set()
        self._symbol_raster_types_hit = set()
        self._symbol_raster_types_miss = set()
        self._view_extraction_ms = []
        self._view_extraction_rows = []
        self._cache_temperature_cohort_ms = {"cold": [], "mixed": [], "warm": [], "none": []}
        self._run_seen_symbol_types = set()

    def flush_view_record(self, path, bundle, status, view_perf=None):
        """Append one JSON Lines record for this view to path."""

        presentation = getattr(bundle, "presentation_summary", None)
        search = getattr(bundle, "search_features", None)
        presentation_debug = getattr(presentation, "debug", None) or {}
        search_debug = getattr(search, "debug", None) or {}
        feature_summary = getattr(presentation, "feature_summary", None) or {}

        perf = dict(view_perf or {})
        for key, default in (
            ("symbol_lookups_total", 0),
            ("symbol_cache_hits", 0),
            ("symbol_cache_misses", 0),
            ("symbol_cache_hit_rate", 0.0),
            ("symbol_lookup_ms_total", 0.0),
            ("symbol_lookup_ms_hit_total", 0.0),
            ("symbol_lookup_ms_miss_total", 0.0),
            ("symbol_cache_miss_reasons", {}),
            ("unique_symbol_types_in_view", 0),
            ("new_symbol_types_built_in_view", 0),
            ("reused_symbol_types_in_view", 0),
            ("cache_temperature", "none"),
        ):
            if key not in perf:
                perf[key] = default

        record = {
            "schema_version": INDEX_VIEWS_JSONL_SCHEMA,
            "view_id": int(getattr(search, "view_id", -1)),
            "display_name": getattr(presentation, "display_name", ""),
            "cache_status": str(status),
            "extraction_ms": presentation_debug.get("extraction_ms"),
            "pt_count": search_debug.get("pt_count"),
            "symbol_instances": feature_summary.get("symbol_instances"),
            "curve_count": feature_summary.get("curve_count"),
            "ts_utc": datetime.utcnow().isoformat() + "Z",
        }
        record.update(perf)

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def create_view_symbol_perf_accumulator(self):
        return ViewSymbolRasterPerfAccumulator()

    def finalize_view_symbol_perf(self, view_perf):
        return view_perf.finalize(self._run_seen_symbol_types)

    def accumulate(self, bundle, cache_status):
        self.count_total += 1
        self.count_indexed += 1

        features = bundle.search_features
        source_scope = features.source_doc_name or features.source_doc_id or "<no-doc>"
        view_id = int(features.view_id)
        view_name = bundle.presentation_summary.display_name
        token_count = len(features.tokens_stable) + len(features.tokens_context)
        nonzero_fp_bins = sum(1 for value in features.geom_hist_knn_endpoints if float(value) > 0.0)
        symbol_count = len(features.symbol_multiset)

        self.corpus_id_parts.append((str(source_scope), view_id))
        self.source_docs.add(str(source_scope))

        for symbol_key, count in features.symbol_multiset.items():
            self._symbol_counts[symbol_key] = self._symbol_counts.get(symbol_key, 0) + int(count)

        sparse_threshold = int(CONFIG.get("sparse_fingerprint_threshold", 5))
        min_token_threshold = int(CONFIG.get("min_token_threshold", 4))
        flags = []
        if token_count == 0:
            flags.append("zero_tokens")
        if token_count < min_token_threshold:
            flags.append("below_token_threshold")
        if nonzero_fp_bins == 0:
            flags.append("empty_fingerprint")
        if nonzero_fp_bins < sparse_threshold:
            flags.append("sparse_fingerprint")

        self.view_records.append(
            {
                "view_id": view_id,
                "view_name": view_name,
                "view_kind": features.view_kind,
                "source_scope": str(source_scope),
                "token_count": token_count,
                "nonzero_fp_bins": nonzero_fp_bins,
                "symbol_count": symbol_count,
                "cache_status": str(cache_status),
                "flags": flags,
            }
        )
        self.count_cache_statuses[str(cache_status)] = self.count_cache_statuses.get(str(cache_status), 0) + 1
        view_kind = str(features.view_kind)
        self.kind_breakdown[view_kind] = self.kind_breakdown.get(view_kind, 0) + 1

    def accumulate_symbol_raster_lookup(self, lookup):
        self._symbol_raster_total += 1
        symbol_type_key = str(lookup.get("symbol_type_key", "<unknown-symbol>"))
        self._symbol_raster_types_seen.add(symbol_type_key)
        was_hit = bool(lookup.get("cache_hit", False))
        elapsed_ms = float(lookup.get("elapsed_ms", 0.0))
        if was_hit:
            self._symbol_raster_hits += 1
            self._symbol_raster_hit_ms.append(elapsed_ms)
            self._symbol_raster_types_hit.add(symbol_type_key)
            return

        self._symbol_raster_misses += 1
        self._symbol_raster_miss_ms.append(elapsed_ms)
        self._symbol_raster_types_miss.add(symbol_type_key)
        reason = str(lookup.get("miss_reason", "unknown"))
        self._symbol_raster_miss_reasons[reason] = self._symbol_raster_miss_reasons.get(reason, 0) + 1

    def accumulate_view_timing(self, view_id, display_name, extraction_ms):
        duration = float(extraction_ms)
        self._view_extraction_ms.append(duration)
        self._view_extraction_rows.append(
            {"view_id": int(view_id), "display_name": str(display_name), "ms": duration}
        )

    def accumulate_cache_temperature(self, cache_temperature, extraction_ms):
        cohort = str(cache_temperature or "none")
        if cohort not in self._cache_temperature_cohort_ms:
            cohort = "none"
        self._cache_temperature_cohort_ms[cohort].append(float(extraction_ms))

    def accumulate_error(self, view_id, view_name, error):
        self.count_total += 1
        self.count_errored += 1
        self.view_records.append(
            {
                "view_id": view_id,
                "view_name": view_name,
                "view_kind": None,
                "source_scope": None,
                "token_count": None,
                "nonzero_fp_bins": None,
                "symbol_count": None,
                "cache_status": None,
                "flags": ["extraction_error"],
                "error": str(error),
            }
        )

    def finalize(self, token_idf, token_df, config):
        corpus_payload = json.dumps(sorted(self.corpus_id_parts), sort_keys=True)
        corpus_id = hashlib.sha1(corpus_payload.encode("utf-8")).hexdigest()

        stopword_idf_floor = float(config.get("diagnostics", {}).get("stopword_idf_floor", 0.5))
        # Dynamic alternative would use the bottom decile of IDF distribution;
        # revisit this once corpus-size behavior is stable.
        stopword_candidates = sorted(
            [[token, float(idf)] for token, idf in token_idf.items() if float(idf) < stopword_idf_floor],
            key=lambda row: (row[1], row[0]),
        )

        idf_pairs = sorted([[token, float(idf)] for token, idf in token_idf.items()], key=lambda row: (row[1], row[0]))
        top_low = idf_pairs[:10]
        top_high = sorted(idf_pairs, key=lambda row: (-row[1], row[0]))[:10]

        symbol_top = sorted(self._symbol_counts.items(), key=lambda row: (-row[1], row[0]))[:10]
        symbol_top = [[key, int(value)] for key, value in symbol_top]

        token_counts = [row["token_count"] for row in self.view_records if row["token_count"] is not None]
        fp_counts = [row["nonzero_fp_bins"] for row in self.view_records if row["nonzero_fp_bins"] is not None]
        idf_values = [float(value) for value in token_idf.values()]

        flagged_rows = [
            {"view_id": row["view_id"], "view_name": row["view_name"], "flags": row["flags"]}
            for row in self.view_records
            if row.get("flags")
        ]

        views_with_symbols = sum(
            1
            for row in self.view_records
            if row.get("symbol_count") is not None and row["symbol_count"] > 0
        )
        symbol_hit_stats = distribution_stats(self._symbol_raster_hit_ms)
        symbol_miss_stats = distribution_stats(self._symbol_raster_miss_ms)
        view_stats = distribution_stats(self._view_extraction_ms)
        slowest_views = sorted(self._view_extraction_rows, key=lambda row: (-float(row["ms"]), row["view_id"]))[:5]
        cache_temperature_summary = {}
        for cohort in ("cold", "mixed", "warm", "none"):
            timings = self._cache_temperature_cohort_ms.get(cohort, [])
            cache_temperature_summary[cohort] = {
                "view_count": len(timings),
                "timing_ms": distribution_stats(timings),
            }

        return {
            "schema_version": self.schema_version,
            "built_at": _utc_now_iso(),
            "pipeline_version": self.pipeline_version,
            "corpus_id": corpus_id,
            "corpus_summary": {
                "view_count_total": self.count_total,
                "view_count_indexed": self.count_indexed,
                "view_count_errored": self.count_errored,
                "errored_view_ids": [
                    row["view_id"] for row in self.view_records if "extraction_error" in row.get("flags", [])
                ],
                "view_kind_breakdown": dict(sorted(self.kind_breakdown.items())),
                "source_docs": sorted(self.source_docs),
            },
            "token_health": {
                "vocabulary_size": len(token_df),
                "views_below_min_token_threshold": sum(
                    1
                    for row in self.view_records
                    if row.get("token_count") is not None
                    and row["token_count"] < int(CONFIG.get("min_token_threshold", 4))
                ),
                "views_with_zero_tokens": sum(1 for row in self.view_records if row.get("token_count") == 0),
                "token_count_distribution": distribution_stats(token_counts),
                "idf_distribution": distribution_stats(idf_values),
                "top_10_highest_idf_tokens": top_high,
                "top_10_lowest_idf_tokens": top_low,
                "stopword_candidates": stopword_candidates,
                "stopword_idf_floor_used": stopword_idf_floor,
            },
            "geometry_health": {
                "views_with_empty_fingerprint": sum(1 for row in self.view_records if row.get("nonzero_fp_bins") == 0),
                "views_with_sparse_fingerprint": sum(
                    1
                    for row in self.view_records
                    if row.get("nonzero_fp_bins") is not None
                    and row["nonzero_fp_bins"] < int(CONFIG.get("sparse_fingerprint_threshold", 5))
                ),
                "fingerprint_nonzero_bin_distribution": distribution_stats(fp_counts),
            },
            "symbol_coverage": {
                "views_with_symbol_data": views_with_symbols,
                "views_without_symbol_data": self.count_indexed - views_with_symbols,
                "unique_symbol_types": len(self._symbol_counts),
                "top_10_most_common_symbols": symbol_top,
            },
            "cache_health": {
                "cache_statuses": dict(sorted(self.count_cache_statuses.items())),
            },
            "symbol_raster_summary": {
                "lookups_total": self._symbol_raster_total,
                "hit_count": self._symbol_raster_hits,
                "miss_count": self._symbol_raster_misses,
                "hit_rate": 0.0
                if self._symbol_raster_total <= 0
                else float(self._symbol_raster_hits) / float(self._symbol_raster_total),
                "miss_reasons": dict(sorted(self._symbol_raster_miss_reasons.items())),
                "hit_timing_ms": {
                    "min": symbol_hit_stats["min"],
                    "max": symbol_hit_stats["max"],
                    "mean": symbol_hit_stats["mean"],
                    "p50": symbol_hit_stats["p50"],
                    "p95": symbol_hit_stats["p95"],
                },
                "miss_timing_ms": {
                    "min": symbol_miss_stats["min"],
                    "max": symbol_miss_stats["max"],
                    "mean": symbol_miss_stats["mean"],
                    "p50": symbol_miss_stats["p50"],
                    "p95": symbol_miss_stats["p95"],
                },
                "unique_symbol_types_total": len(self._symbol_raster_types_seen),
                "unique_symbol_types_hit": len(self._symbol_raster_types_hit),
                "unique_symbol_types_miss": len(self._symbol_raster_types_miss),
            },
            "miss_reason_summary": dict(sorted(self._symbol_raster_miss_reasons.items())),
            "unique_symbol_type_totals": {
                "total": len(self._symbol_raster_types_seen),
                "hit": len(self._symbol_raster_types_hit),
                "miss": len(self._symbol_raster_types_miss),
            },
            "cache_temperature_summary": cache_temperature_summary,
            "timing": {
                "total_elapsed_ms": float(sum(self._view_extraction_ms)),
                "mean_view_ms": view_stats["mean"],
                "p50_view_ms": view_stats["p50"],
                "p95_view_ms": view_stats["p95"],
                "slowest_views": slowest_views,
            },
            "timing_summary": {
                "total_elapsed_ms": float(sum(self._view_extraction_ms)),
                "mean_view_ms": view_stats["mean"],
                "p50_view_ms": view_stats["p50"],
                "p95_view_ms": view_stats["p95"],
            },
            "slowest_views": slowest_views,
            "flag_summary": {
                "views_flagged": len(flagged_rows),
                "flags": flagged_rows,
            },
        }


class SearchDiagnosticBuilder:
    """Collects timing checkpoints and builds the search sidecar payload."""

    def __init__(self, run_id):
        self.run_id = run_id
        self.timings = {}
        self._starts = {}

    def start_timer(self, label):
        self._starts[label] = time.monotonic()

    def stop_timer(self, label):
        self.timings[label] = (time.monotonic() - self._starts[label]) * 1000.0

    def build(
        self,
        *,
        query_bundle,
        corpus_size,
        corpus_errors,
        cache_statuses,
        config_snapshot,
        token_idf,
        default_idf,
        all_scored,
        top_results,
        stage2_available,
        min_token_threshold=None,
    ):
        token_count = len(query_bundle.search_features.tokens_stable) + len(query_bundle.search_features.tokens_context)
        effective_min_token_threshold = int(
            min_token_threshold if min_token_threshold is not None else CONFIG.get("min_token_threshold", 4)
        )
        semantic_regime = (
            "low_semantic_fallback" if token_count < effective_min_token_threshold else "normal"
        )
        nonzero_bins = sum(1 for value in query_bundle.search_features.geom_hist_knn_endpoints if float(value) > 0.0)
        scores = [float(row.get("score_total", 0.0)) for row in all_scored]

        tier_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for row in all_scored:
            tier = str(row.get("confidence_tier", "LOW")).upper()
            if tier not in tier_counts:
                tier = "LOW"
            tier_counts[tier] += 1

        if semantic_regime == "low_semantic_fallback":
            weights_applied = dict(CONFIG.get("low_semantic_weights", {}))
        else:
            weights_applied = dict(CONFIG.get("weights", {}))

        results = []
        for rank, row in enumerate(top_results, start=1):
            presentation = row.get("presentation_summary") or {}
            if not isinstance(presentation, dict):
                presentation = {}
            explanation = row.get("explanation") or {}
            results.append(
                {
                    "rank": rank,
                    "candidate_view_id": row.get("candidate_view_id"),
                    "candidate_display_name": presentation.get("display_name") or "",
                    "score_total": row.get("score_total"),
                    "score_tokens": row.get("score_tokens"),
                    "score_geom": row.get("score_geom"),
                    "score_fine": row.get("score_fine"),
                    "weights_applied": weights_applied,
                    "confidence_tier": row.get("confidence_tier"),
                    "score_combined": row.get("score_combined") if stage2_available else None,
                    "score_raster": row.get("score_raster"),
                    "score_symbols": row.get("score_symbols"),
                    "confidence_raster_support": row.get("confidence_raster_support"),
                    "stage2_notes": row.get("stage2_notes") or [],
                    "explanation": {
                        "top_shared_tokens": explanation.get("top_shared_tokens") or [],
                        "top_shared_geom_bins": explanation.get("top_shared_geom_bins") or [],
                    },
                }
            )

        return {
            "schema_version": SEARCH_SIDECAR_SCHEMA,
            "run_id": self.run_id,
            "built_at": _utc_now_iso(),
            "pipeline_version": CONFIG["pipeline_version"],
            "query": {
                "view_id": query_bundle.search_features.view_id,
                "display_name": query_bundle.presentation_summary.display_name,
                "view_kind": query_bundle.search_features.view_kind,
                "token_count": token_count,
                "geom_nonzero_bins": nonzero_bins,
                "semantic_regime": semantic_regime,
                "cache_status": query_bundle.presentation_summary.debug.get("cache_status"),
            },
            "corpus": {
                "size": corpus_size,
                "views_errored": int(corpus_errors),
                "cache_statuses": dict(sorted(cache_statuses.items())),
                "idf_doc_count": int(corpus_size),
                "token_vocabulary_size": len(token_idf),
                "default_idf_used": float(default_idf),
            },
            "config_snapshot": config_snapshot,
            "timings_ms": dict(self.timings),
            "score_distribution": {
                **distribution_stats(scores),
                "tier_counts": tier_counts,
            },
            "results": results,
        }


def build_config_snapshot(config):
    diagnostics = config.get("diagnostics", {})
    return {
        "weights": config.get("weights"),
        "low_semantic_weights": config.get("low_semantic_weights"),
        "min_token_threshold": config.get("min_token_threshold"),
        "confidence_thresholds": config.get("confidence_thresholds"),
        "stage2_enabled": config.get("stage2_rerank", {}).get("enabled"),
        "stage2_pool_mode": config.get("stage2_rerank", {}).get("band_mode"),
        "stage2_pool_size": config.get("stage2_rerank", {}).get("pool_top_k"),
        "stopword_idf_floor": diagnostics.get("stopword_idf_floor", 0.5),
    }
