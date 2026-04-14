#!/usr/bin/env python3
"""Analyze symbol_raster.v1 cache redundancy and key over-specification.

Usage examples:
  python scripts/analyze_symbol_raster_cache.py --input ./cache/symbol_raster --recurse
  python scripts/analyze_symbol_raster_cache.py --glob "./cache/**/*.json" --recurse --outdir ./artifacts/cache_audit
  python scripts/analyze_symbol_raster_cache.py --input ./cache --family-report "Wide Flange" --plot

The script emits a console summary and writes machine-readable outputs (JSON/CSV) to --outdir.
It is robust to missing optional fields and malformed files (those are skipped with warnings).
"""

from __future__ import annotations

import argparse
import csv
import glob as glob_lib
import hashlib
import itertools
import json
import math
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


MISSING = "<missing>"
DEFAULT_BASE_FIELDS = ["doc_scope", "family_type", "view_scale", "detail_level", "length_bucket_in"]
ABLATED_FIELDS = ["orientation_bucket", "length_bucket_in", "detail_level", "view_scale"]


@dataclass(frozen=True)
class Record:
    path: str
    cache_schema: str
    cache_key: str
    doc_scope: str
    family_name: str
    type_name: str
    family_type: str
    view_scale: str
    detail_level: str
    orientation_bucket: str
    length_bucket_in: str
    obb_width: float | None
    obb_height: float | None
    points: tuple[tuple[float, float], ...]
    point_count: int
    bbox_min_x: float
    bbox_min_y: float
    bbox_max_x: float
    bbox_max_y: float
    bbox_width: float
    bbox_height: float
    strict_fingerprint: str


def safe_str(value):
    if value is None:
        return MISSING
    if isinstance(value, str) and value.strip() == "":
        return MISSING
    return str(value)


def safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def get_type_name(payload):
    candidates = ["type_name", "family_type", "symbol_name", "type", "symbol"]
    for field in candidates:
        if field in payload and payload[field] not in (None, ""):
            return safe_str(payload[field])
    return MISSING


def normalize_point_list(points_raw):
    points = []
    if not isinstance(points_raw, list):
        return tuple()
    for item in points_raw:
        if isinstance(item, dict):
            x = item.get("x")
            y = item.get("y")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            x, y = item[0], item[1]
        else:
            continue
        try:
            points.append((float(x), float(y)))
        except (TypeError, ValueError):
            continue
    return tuple(points)


def bbox_stats(points):
    if not points:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    return (min_x, min_y, max_x, max_y, max_x - min_x, max_y - min_y)


def strict_fingerprint(points, quantization):
    if not points:
        return hashlib.sha256(b"empty").hexdigest()

    min_x = min(p[0] for p in points)
    min_y = min(p[1] for p in points)
    normalized = []
    for x, y in points:
        nx = (x - min_x) / quantization
        ny = (y - min_y) / quantization
        normalized.append((int(round(nx)), int(round(ny))))
    normalized.sort()
    digest = hashlib.sha256(repr(tuple(normalized)).encode("utf-8")).hexdigest()
    return digest


def dedupe_quantized_points(points, quantization):
    bins = set()
    for x, y in points:
        bins.add((int(round(x / quantization)), int(round(y / quantization))))
    return sorted(bins)


def transform_points(points_bins, rotation_deg=0, mirror=False):
    transformed = []
    for x, y in points_bins:
        tx, ty = x, y
        if mirror:
            tx = -tx

        if rotation_deg == 0:
            rx, ry = tx, ty
        elif rotation_deg == 90:
            rx, ry = -ty, tx
        elif rotation_deg == 180:
            rx, ry = -tx, -ty
        elif rotation_deg == 270:
            rx, ry = ty, -tx
        else:
            raise ValueError(f"unsupported rotation {rotation_deg}")
        transformed.append((rx, ry))

    if not transformed:
        return transformed

    min_x = min(p[0] for p in transformed)
    min_y = min(p[1] for p in transformed)
    return sorted((x - min_x, y - min_y) for x, y in transformed)


def approx_symmetric_chamfer(a_points, b_points):
    if not a_points and not b_points:
        return 0.0
    if not a_points or not b_points:
        return float("inf")

    def one_way(source, target):
        total = 0.0
        for sx, sy in source:
            best_sq = None
            for tx, ty in target:
                dx = sx - tx
                dy = sy - ty
                d2 = dx * dx + dy * dy
                if best_sq is None or d2 < best_sq:
                    best_sq = d2
            total += math.sqrt(best_sq) if best_sq is not None else 0.0
        return total / max(1, len(source))

    return 0.5 * (one_way(a_points, b_points) + one_way(b_points, a_points))


def equivalence_distance(points_a, points_b, quantization, allow_rotations, allow_mirror):
    bins_a = dedupe_quantized_points(points_a, quantization)
    bins_b = dedupe_quantized_points(points_b, quantization)

    rotations = [0, 90, 180, 270] if allow_rotations else [0]
    mirrors = [False, True] if allow_mirror else [False]

    best = float("inf")
    for rotation in rotations:
        for mirror in mirrors:
            b_variant = transform_points(bins_b, rotation_deg=rotation, mirror=mirror)
            dist = approx_symmetric_chamfer(bins_a, b_variant)
            if dist < best:
                best = dist
    return best


def load_record(path, strict_quantization):
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    points = normalize_point_list(payload.get("points"))
    bbox = bbox_stats(points)

    family_name = safe_str(payload.get("family_name"))
    type_name = get_type_name(payload)
    family_type = f"{family_name}::{type_name}"

    return Record(
        path=path,
        cache_schema=safe_str(payload.get("cache_schema")),
        cache_key=safe_str(payload.get("cache_key")),
        doc_scope=safe_str(payload.get("doc_scope")),
        family_name=family_name,
        type_name=type_name,
        family_type=family_type,
        view_scale=safe_str(payload.get("view_scale")),
        detail_level=safe_str(payload.get("detail_level")),
        orientation_bucket=safe_str(payload.get("orientation_bucket")),
        length_bucket_in=safe_str(payload.get("length_bucket_in")),
        obb_width=safe_float(payload.get("obb_width")),
        obb_height=safe_float(payload.get("obb_height")),
        points=points,
        point_count=len(points),
        bbox_min_x=bbox[0],
        bbox_min_y=bbox[1],
        bbox_max_x=bbox[2],
        bbox_max_y=bbox[3],
        bbox_width=bbox[4],
        bbox_height=bbox[5],
        strict_fingerprint=strict_fingerprint(points, strict_quantization),
    )


def discover_files(input_dir, glob_pattern, recurse):
    files = set()
    if input_dir:
        base = Path(input_dir)
        if recurse:
            iterator = base.rglob("*.json")
        else:
            iterator = base.glob("*.json")
        files.update(str(p) for p in iterator if p.is_file())
    if glob_pattern:
        files.update(glob_lib.glob(glob_pattern, recursive=recurse))
    return sorted(files)


def make_group_key(record, fields):
    return tuple(getattr(record, field, MISSING) for field in fields)


def build_equivalence_labels(records, threshold, quantization, allow_rotations, allow_mirror):
    labels = {}
    if not records:
        return labels

    class_representatives = []
    class_ids = []
    for rec in sorted(records, key=lambda r: r.path):
        assigned = None
        for idx, rep in enumerate(class_representatives):
            dist = equivalence_distance(
                rec.points,
                rep.points,
                quantization=quantization,
                allow_rotations=allow_rotations,
                allow_mirror=allow_mirror,
            )
            if dist <= threshold:
                assigned = class_ids[idx]
                break
        if assigned is None:
            assigned = f"eq_{len(class_representatives)}"
            class_representatives.append(rec)
            class_ids.append(assigned)
        labels[rec.path] = assigned
    return labels


def analyze_base_groups(
    records,
    base_fields,
    equiv_threshold,
    strict_quantization,
    allow_rotations,
    allow_mirror,
):
    grouped = defaultdict(list)
    for rec in records:
        grouped[make_group_key(rec, base_fields)].append(rec)

    rows = []
    all_labels = {}
    for key, group in grouped.items():
        labels = build_equivalence_labels(
            group,
            threshold=equiv_threshold,
            quantization=strict_quantization,
            allow_rotations=allow_rotations,
            allow_mirror=allow_mirror,
        )
        all_labels.update(labels)

        strict_unique = len({r.strict_fingerprint for r in group})
        equiv_unique = len(set(labels.values()))
        total_entries = len(group)

        redundancy_ratio = 0.0
        if total_entries:
            redundancy_ratio = 1.0 - (equiv_unique / total_entries)

        row = {
            "base_key": "|".join(str(v) for v in key),
            "total_entries": total_entries,
            "unique_strict_fingerprints": strict_unique,
            "unique_equiv_classes": equiv_unique,
            "redundancy_ratio": redundancy_ratio,
            "family_name": group[0].family_name if group else MISSING,
            "type_name": group[0].type_name if group else MISSING,
            "doc_scope": group[0].doc_scope if group else MISSING,
        }
        rows.append(row)

    rows.sort(key=lambda r: (-r["redundancy_ratio"], -r["total_entries"], r["base_key"]))
    return rows, all_labels


def compare_schema(records, schema_fields, equiv_labels):
    grouped = defaultdict(list)
    for rec in records:
        grouped[make_group_key(rec, schema_fields)].append(rec)

    key_cardinality = len(grouped)
    pure_groups = 0
    false_merge_groups = 0
    false_merge_records = 0
    collision_records = 0
    unique_equiv_counts = []

    for group in grouped.values():
        equiv_ids = [equiv_labels.get(r.path, f"fallback::{r.strict_fingerprint}") for r in group]
        unique_equiv = len(set(equiv_ids))
        unique_equiv_counts.append(unique_equiv)
        if unique_equiv <= 1:
            pure_groups += 1
        else:
            false_merge_groups += 1
            false_merge_records += len(group)
            collision_records += len(group) - 1

    total_groups = max(1, len(grouped))
    purity = pure_groups / total_groups
    avg_unique_outputs = sum(unique_equiv_counts) / total_groups

    return {
        "schema_fields": "|".join(schema_fields),
        "key_cardinality": key_cardinality,
        "purity": purity,
        "false_merge_groups": false_merge_groups,
        "false_merge_records": false_merge_records,
        "collision_records": collision_records,
        "avg_unique_outputs_per_group": avg_unique_outputs,
    }


def schema_candidates(records):
    possible_fields = [
        "doc_scope",
        "family_type",
        "view_scale",
        "detail_level",
        "orientation_bucket",
        "length_bucket_in",
    ]

    present_fields = []
    for field in possible_fields:
        values = {getattr(r, field, MISSING) for r in records}
        if len(values) > 1:
            present_fields.append(field)

    if not present_fields:
        return [["doc_scope", "family_type"]]

    # Current-like key plus all single-field ablations and selected multi-ablations.
    baseline = [f for f in possible_fields if f in present_fields]
    candidates = [baseline]

    for field in ABLATED_FIELDS:
        if field in baseline:
            candidates.append([f for f in baseline if f != field])

    for r in range(2, min(4, len(ABLATED_FIELDS) + 1)):
        for combo in itertools.combinations([f for f in ABLATED_FIELDS if f in baseline], r):
            reduced = [f for f in baseline if f not in combo]
            if reduced:
                candidates.append(reduced)

    # Deduplicate while preserving deterministic order.
    seen = set()
    uniq = []
    for fields in candidates:
        key = tuple(fields)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(fields)
    return uniq


def pareto_frontier(rows):
    frontier = []
    for row in rows:
        dominated = False
        for other in rows:
            if row is other:
                continue
            better_or_equal = (
                other["key_cardinality"] <= row["key_cardinality"]
                and other["false_merge_groups"] <= row["false_merge_groups"]
                and other["purity"] >= row["purity"]
            )
            strictly_better = (
                other["key_cardinality"] < row["key_cardinality"]
                or other["false_merge_groups"] < row["false_merge_groups"]
                or other["purity"] > row["purity"]
            )
            if better_or_equal and strictly_better:
                dominated = True
                break
        if not dominated:
            frontier.append(row)

    frontier.sort(key=lambda r: (r["key_cardinality"], r["false_merge_groups"], -r["purity"]))
    return frontier


def orientation_diagnostics(records, equiv_threshold, strict_quantization, allow_rotations, allow_mirror):
    by_base = defaultdict(list)
    orientation_base_fields = ["doc_scope", "family_type", "view_scale", "detail_level", "length_bucket_in"]
    for rec in records:
        by_base[make_group_key(rec, orientation_base_fields)].append(rec)

    pair_stats = defaultdict(lambda: {"pairs": 0, "equiv_pairs": 0})

    for group in by_base.values():
        by_orientation = defaultdict(list)
        for rec in group:
            by_orientation[rec.orientation_bucket].append(rec)

        orientations = sorted(by_orientation)
        for a in orientations:
            for b in orientations:
                if a > b:
                    continue
                left = by_orientation[a]
                right = by_orientation[b]
                for rec_a in left:
                    for rec_b in right:
                        if a == b and rec_a.path >= rec_b.path:
                            continue
                        pair_stats[(a, b)]["pairs"] += 1
                        dist = equivalence_distance(
                            rec_a.points,
                            rec_b.points,
                            quantization=strict_quantization,
                            allow_rotations=allow_rotations,
                            allow_mirror=allow_mirror,
                        )
                        if dist <= equiv_threshold:
                            pair_stats[(a, b)]["equiv_pairs"] += 1

    rows = []
    for (a, b), stats in sorted(pair_stats.items()):
        pairs = stats["pairs"]
        equiv_pairs = stats["equiv_pairs"]
        rate = equiv_pairs / pairs if pairs else 0.0
        rows.append(
            {
                "orientation_a": a,
                "orientation_b": b,
                "pairs": pairs,
                "equiv_pairs": equiv_pairs,
                "equiv_rate": rate,
            }
        )
    return rows


def write_csv(path, rows, fieldnames):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def maybe_make_plots(outdir, group_rows, schema_rows, orientation_rows):
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return "matplotlib unavailable; skipped plots"

    # 1) entries vs unique outputs histogram/scatter
    fig = plt.figure(figsize=(8, 6))
    xs = [r["total_entries"] for r in group_rows]
    ys = [r["unique_equiv_classes"] for r in group_rows]
    plt.scatter(xs, ys, alpha=0.6)
    plt.xlabel("Entries per base group")
    plt.ylabel("Unique equivalence classes")
    plt.title("Base-group redundancy")
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "group_redundancy_scatter.png"), dpi=160)
    plt.close(fig)

    # 2) ablation bar chart (percent reduction from baseline)
    fig = plt.figure(figsize=(10, 5))
    labels = [r["schema_fields"] for r in schema_rows]
    reductions = [r.get("pct_reduction_from_baseline", 0.0) for r in schema_rows]
    plt.bar(range(len(labels)), reductions)
    plt.xticks(range(len(labels)), labels, rotation=65, ha="right")
    plt.ylabel("% key-cardinality reduction")
    plt.title("Schema ablation impact")
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "schema_ablation.png"), dpi=160)
    plt.close(fig)

    # 3) Pareto scatter
    fig = plt.figure(figsize=(8, 6))
    x = [r["key_cardinality"] for r in schema_rows]
    y = [r["false_merge_groups"] for r in schema_rows]
    plt.scatter(x, y, alpha=0.7)
    plt.xlabel("Schema key cardinality")
    plt.ylabel("False-merge groups")
    plt.title("Pareto trade-off: size vs merge risk")
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "pareto_scatter.png"), dpi=160)
    plt.close(fig)

    # 4) orientation heatmap
    orientations = sorted(
        set([r["orientation_a"] for r in orientation_rows] + [r["orientation_b"] for r in orientation_rows])
    )
    idx = {name: i for i, name in enumerate(orientations)}
    matrix = [[0.0 for _ in orientations] for _ in orientations]
    counts = [[0 for _ in orientations] for _ in orientations]
    for row in orientation_rows:
        i = idx[row["orientation_a"]]
        j = idx[row["orientation_b"]]
        matrix[i][j] = row["equiv_rate"]
        matrix[j][i] = row["equiv_rate"]
        counts[i][j] = row["pairs"]
        counts[j][i] = row["pairs"]

    fig = plt.figure(figsize=(7, 6))
    ax = fig.add_subplot(111)
    im = ax.imshow(matrix, vmin=0.0, vmax=1.0, cmap="viridis")
    ax.set_xticks(range(len(orientations)))
    ax.set_yticks(range(len(orientations)))
    ax.set_xticklabels(orientations, rotation=45, ha="right")
    ax.set_yticklabels(orientations)
    ax.set_title("Orientation equivalence rate")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "orientation_equivalence_heatmap.png"), dpi=160)
    plt.close(fig)

    return "plots generated"


def build_recommendations(group_rows, schema_rows, orientation_rows, top_n=5):
    lines = []

    suspicious = sorted(
        schema_rows,
        key=lambda r: (-r.get("pct_reduction_from_baseline", 0.0), r["false_merge_groups"]),
    )
    if suspicious:
        best = suspicious[0]
        lines.append(
            "- Highest cardinality reduction candidate: "
            f"{best['schema_fields']} (reduction={best.get('pct_reduction_from_baseline', 0.0):.1f}%, "
            f"false_merge_groups={best['false_merge_groups']})."
        )

    low_risk = [r for r in schema_rows if r["false_merge_groups"] == 0 and r.get("pct_reduction_from_baseline", 0) > 0]
    if low_risk:
        candidate = max(low_risk, key=lambda r: r.get("pct_reduction_from_baseline", 0.0))
        lines.append(
            "- Dead-weight field signal: "
            f"{candidate['schema_fields']} removes keys without observed false merges in this sample."
        )

    high_redundancy = [r for r in group_rows if r["redundancy_ratio"] >= 0.5]
    if high_redundancy:
        lines.append(
            f"- {len(high_redundancy)} base groups show >=50% redundancy; "
            f"inspect top {min(top_n, len(high_redundancy))} first."
        )

    pair_map = {(r["orientation_a"], r["orientation_b"]): r for r in orientation_rows}
    orientation_hints = []
    for pair in [("r0", "r4"), ("r0", "r2"), ("r2", "r6")]:
        row = pair_map.get(pair) or pair_map.get((pair[1], pair[0]))
        if row and row["pairs"] >= 5:
            orientation_hints.append(
                f"{pair[0]}~{pair[1]} equivalence={row['equiv_rate']:.2f} over {row['pairs']} pairs"
            )
    if orientation_hints:
        lines.append("- Orientation diagnostics: " + "; ".join(orientation_hints) + ".")

    if not lines:
        lines.append("- No strong simplification signal detected with current thresholds and sample size.")

    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", dest="input_dir", help="Directory containing cache JSON files")
    parser.add_argument("--glob", dest="glob_pattern", help="Glob pattern for cache JSON files")
    parser.add_argument("--recurse", action="store_true", help="Recurse for --input and recursive glob")
    parser.add_argument("--outdir", default="./artifacts/symbol_raster_cache_analysis", help="Output directory")
    parser.add_argument("--plot", action="store_true", help="Generate optional plots when matplotlib is available")
    parser.add_argument(
        "--strict-quantization",
        type=float,
        default=1e-4,
        help="Quantization step for strict normalized fingerprint and equivalence bins",
    )
    parser.add_argument(
        "--equiv-threshold",
        type=float,
        default=0.75,
        help="Equivalence threshold on quantized symmetric Chamfer distance",
    )
    parser.add_argument("--allow-rotations", action="store_true", help="Compare equivalence across 90° rotations")
    parser.add_argument("--allow-mirror", action="store_true", help="Compare equivalence across mirror transforms")
    parser.add_argument("--sample-limit", type=int, default=0, help="Optional cap on number of loaded files")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--family-report", help="Optional family_name filter for focused report")

    args = parser.parse_args()

    if not args.input_dir and not args.glob_pattern:
        raise SystemExit("Provide at least one input source: --input or --glob")

    os.makedirs(args.outdir, exist_ok=True)

    files = discover_files(args.input_dir, args.glob_pattern, args.recurse)
    if args.sample_limit and args.sample_limit > 0:
        files = files[: args.sample_limit]

    records = []
    malformed = 0
    for path in files:
        try:
            rec = load_record(path, args.strict_quantization)
            records.append(rec)
        except Exception as exc:
            malformed += 1
            if args.verbose:
                print(f"[warn] failed to parse {path}: {exc}")

    if args.family_report:
        records = [r for r in records if r.family_name == args.family_report]

    if not records:
        raise SystemExit("No valid records found. Check input path/glob and schema.")

    base_fields = DEFAULT_BASE_FIELDS
    group_rows, equiv_labels = analyze_base_groups(
        records,
        base_fields,
        equiv_threshold=args.equiv_threshold,
        strict_quantization=args.strict_quantization,
        allow_rotations=args.allow_rotations,
        allow_mirror=args.allow_mirror,
    )

    schema_rows = []
    candidates = schema_candidates(records)
    baseline = None
    for fields in candidates:
        row = compare_schema(records, fields, equiv_labels)
        row["field_count"] = len(fields)
        schema_rows.append(row)
        if baseline is None:
            baseline = row

    baseline_cardinality = baseline["key_cardinality"] if baseline else len(records)
    for row in schema_rows:
        row["pct_reduction_from_baseline"] = 100.0 * (
            (baseline_cardinality - row["key_cardinality"]) / max(1, baseline_cardinality)
        )

    schema_rows.sort(key=lambda r: (r["false_merge_groups"], r["key_cardinality"], -r["purity"]))
    frontier = pareto_frontier(schema_rows)

    orientation_rows = orientation_diagnostics(
        records,
        equiv_threshold=args.equiv_threshold,
        strict_quantization=args.strict_quantization,
        allow_rotations=args.allow_rotations,
        allow_mirror=args.allow_mirror,
    )

    family_counts = Counter(r.family_name for r in records)
    top_redundant_groups = group_rows[:10]
    recommendations = build_recommendations(group_rows, schema_rows, orientation_rows)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_file_count": len(files),
        "valid_record_count": len(records),
        "malformed_file_count": malformed,
        "family_filter": args.family_report or None,
        "strict_quantization": args.strict_quantization,
        "equiv_threshold": args.equiv_threshold,
        "allow_rotations": args.allow_rotations,
        "allow_mirror": args.allow_mirror,
        "base_group_fields": base_fields,
        "total_base_groups": len(group_rows),
        "avg_redundancy_ratio": sum(r["redundancy_ratio"] for r in group_rows) / max(1, len(group_rows)),
        "top_families_by_count": family_counts.most_common(20),
        "top_redundant_groups": top_redundant_groups,
        "pareto_frontier": frontier,
        "recommendations": recommendations,
    }

    with open(os.path.join(args.outdir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    write_csv(
        os.path.join(args.outdir, "group_redundancy.csv"),
        group_rows,
        [
            "base_key",
            "doc_scope",
            "family_name",
            "type_name",
            "total_entries",
            "unique_strict_fingerprints",
            "unique_equiv_classes",
            "redundancy_ratio",
        ],
    )

    write_csv(
        os.path.join(args.outdir, "schema_comparison.csv"),
        schema_rows,
        [
            "schema_fields",
            "field_count",
            "key_cardinality",
            "pct_reduction_from_baseline",
            "purity",
            "false_merge_groups",
            "false_merge_records",
            "collision_records",
            "avg_unique_outputs_per_group",
        ],
    )

    write_csv(
        os.path.join(args.outdir, "orientation_equivalence.csv"),
        orientation_rows,
        ["orientation_a", "orientation_b", "pairs", "equiv_pairs", "equiv_rate"],
    )

    plot_status = "plots disabled"
    if args.plot:
        plot_status = maybe_make_plots(args.outdir, group_rows, schema_rows, orientation_rows)

    print("\n=== Symbol Raster Cache Key Analysis ===")
    print(f"Records analyzed: {len(records)} (input files={len(files)}, malformed={malformed})")
    print(f"Base groups: {len(group_rows)}")
    print(f"Average redundancy ratio: {summary['avg_redundancy_ratio']:.3f}")
    print("\nTop redundant base groups:")
    for row in top_redundant_groups[:5]:
        print(
            f"  - {row['base_key']} | entries={row['total_entries']} "
            f"equiv_unique={row['unique_equiv_classes']} redundancy={row['redundancy_ratio']:.2f}"
        )

    print("\nBest schema candidates (low merge risk, low cardinality):")
    for row in schema_rows[:5]:
        print(
            f"  - {row['schema_fields']} | keys={row['key_cardinality']} "
            f"reduction={row['pct_reduction_from_baseline']:.1f}% "
            f"false_merge_groups={row['false_merge_groups']} purity={row['purity']:.3f}"
        )

    print("\nPareto frontier:")
    for row in frontier:
        print(
            f"  - {row['schema_fields']} | keys={row['key_cardinality']} "
            f"false_merge_groups={row['false_merge_groups']} purity={row['purity']:.3f}"
        )

    print("\nRecommendations:")
    for line in recommendations:
        print(line)

    print(f"\nOutputs written to: {args.outdir}")
    print(f"Plot status: {plot_status}\n")


if __name__ == "__main__":
    main()
