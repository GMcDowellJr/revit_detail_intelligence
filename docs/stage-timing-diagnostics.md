# Stage timing diagnostics (compact)

This note describes the compact extraction-stage timing fields added to support run-level bottleneck decisions without introducing full tracing.

## Per-view JSONL fields (`index_diagnostic_views.jsonl`)

Each row now includes:

- `stage_timings_ms`: compact map of per-view stage durations (milliseconds).
- `internal_stage_total_ms`: sum of `stage_timings_ms` values for that view.
- `internal_stage_coverage_ratio`: `internal_stage_total_ms / extraction_ms`.
- `extraction_minus_internal_stage_ms`: `max(0, extraction_ms - internal_stage_total_ms)`.

### Chosen stages

The current stages are:

- `element_collection_ms`: collect view elements from Revit API.
- `symbol_raster_ms`: symbol raster lookup/rebuild work.
- `curve_precollect_ms`: per-element curve precollection cache preparation.
- `token_collection_ms`: token extraction/assignment.
- `curve_extraction_ms`: 2D curve extraction + endpoint/local coordinate prep.
- `geometry_fingerprint_ms`: geometry fingerprint + orientation/length histograms.
- `fine_metrics_ms`: fine metric synthesis.

These were selected because they align with existing boundaries and major optimization decisions (symbol raster behavior, geometry collection/fingerprint costs, token work, and post-geometry metric computation).

## Index aggregate fields (`index_diagnostic.json`)

A new `stage_timing_summary` section aggregates per-stage timing across the run:

- per-stage `total_ms`
- per-stage timing stats (`mean`, `p50`, `p95`)
- per-stage `fraction_of_stage_total` (share of internal stage sum)
- per-stage `fraction_of_extraction_total` (share of outer extraction total)

The section also includes:

- `internal_stage_total_ms` (run-wide sum of internal stage totals)
- `total_extraction_ms` (run-wide sum of outer extraction time)

## Interpretation guidance

- Use `stage_timings_ms` for *which internal stage dominates* each slow view.
- Use `stage_timing_summary.stages` for *next optimization target across run*.
- Compare `extraction_ms` vs `internal_stage_total_ms` to spot likely suspend/sleep or scheduler-inflated rows; large positive `extraction_minus_internal_stage_ms` suggests outer elapsed inflation.

## Caveats

- Stages are measured at compact, mostly non-overlapping boundaries.
- The design intentionally avoids exhaustive nested tracing.
- `extraction_ms` remains wall-clock elapsed for the full view extraction flow and can exceed internal stage sums.
