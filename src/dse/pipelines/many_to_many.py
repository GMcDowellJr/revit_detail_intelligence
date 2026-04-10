import csv
import json
import os
from typing import Dict, List

from dse.io_paths import ensure_dir, resolve_many_to_many_dir, run_stamp
from dse.ranking.similarity import cosine_similarity, fine_similarity, token_similarity


def _layout_similarity(a: Dict[str, float], b: Dict[str, float]) -> float:
    keys = ("node_count", "edge_density_est", "component_count_est")
    scores = []
    for key in keys:
        av = float(a.get(key, 0.0))
        bv = float(b.get(key, 0.0))
        denom = max(1.0, abs(av), abs(bv))
        scores.append(max(0.0, 1.0 - abs(av - bv) / denom))
    return sum(scores) / float(len(scores))


def _symbol_similarity(a: Dict[str, int], b: Dict[str, int]) -> float:
    keys = set(a.keys()) | set(b.keys())
    if not keys:
        return 1.0
    inter = 0.0
    union = 0.0
    for key in keys:
        av = float(a.get(key, 0))
        bv = float(b.get(key, 0))
        inter += min(av, bv)
        union += max(av, bv)
    if union <= 0.0:
        return 0.0
    return inter / union


def build_many_to_many_edges(
    rows: List[Dict[str, object]],
    *,
    top_k: int,
    skip_self: bool = True,
    symmetric_dedupe: bool = False,
):
    out = []
    dedupe = set()
    for seed in rows:
        seed_results = []
        for cand in rows:
            same = int(seed["view_id"]) == int(cand["view_id"])
            if skip_self and same:
                continue

            token_score = token_similarity(seed["tokens"], cand["tokens"], token_idf={}, default_idf=1.0)
            geom_score = cosine_similarity(seed["geom_fingerprint"], cand["geom_fingerprint"])
            fine_score = fine_similarity(seed["fine_metrics"], cand["fine_metrics"])
            layout_score = _layout_similarity(seed["layout_graph_features"], cand["layout_graph_features"])
            symbol_score = _symbol_similarity(seed["symbol_multiset"], cand["symbol_multiset"])
            total = (
                0.45 * token_score
                + 0.30 * geom_score
                + 0.10 * fine_score
                + 0.10 * layout_score
                + 0.05 * symbol_score
            )
            seed_results.append(
                {
                    "seed_view_id": int(seed["view_id"]),
                    "seed_display_name": seed.get("display_name", ""),
                    "candidate_view_id": int(cand["view_id"]),
                    "candidate_display_name": cand.get("display_name", ""),
                    "rank": 0,
                    "total_score": total,
                    "token_score": token_score,
                    "geometry_score": geom_score,
                    "layout_score": layout_score,
                    "symbol_score": symbol_score,
                    "same_view": bool(same),
                    "source_doc_id": seed.get("source_doc_id"),
                    "source_doc_name": seed.get("source_doc_name"),
                    "explanation": "tok={:.3f}, geom={:.3f}, layout={:.3f}, symbol={:.3f}".format(
                        token_score, geom_score, layout_score, symbol_score
                    ),
                }
            )

        seed_results.sort(key=lambda r: (-r["total_score"], r["candidate_view_id"]))
        top = seed_results[: max(0, int(top_k))]
        for rank, row in enumerate(top, 1):
            row["rank"] = rank
            if symmetric_dedupe:
                key = tuple(sorted((row["seed_view_id"], row["candidate_view_id"])))
                if key in dedupe:
                    continue
                dedupe.add(key)
            out.append(row)

    out.sort(key=lambda r: (r["seed_view_id"], r["rank"], -r["total_score"]))
    return out


def write_many_to_many_outputs(rows, config, run_id=None):
    out_dir = ensure_dir(resolve_many_to_many_dir(config))
    rid = run_id or run_stamp("many_to_many")
    json_path = os.path.join(out_dir, "{}_edges.json".format(rid))
    csv_path = os.path.join(out_dir, "{}_edges.csv".format(rid))

    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2, sort_keys=True)

    if rows:
        fieldnames = list(rows[0].keys())
        if "confidence_tier" not in fieldnames:
            fieldnames.append("confidence_tier")
    else:
        fieldnames = [
            "seed_view_id",
            "seed_display_name",
            "candidate_view_id",
            "candidate_display_name",
            "rank",
            "total_score",
            "token_score",
            "geometry_score",
            "layout_score",
            "symbol_score",
            "confidence_tier",
            "same_view",
            "source_doc_id",
            "source_doc_name",
            "explanation",
        ]
    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return {"run_id": rid, "json_path": json_path, "csv_path": csv_path, "row_count": len(rows)}
