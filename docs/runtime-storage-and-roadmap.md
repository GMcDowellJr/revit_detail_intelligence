# Runtime Storage and v0.3.2 Operational Notes

## Default storage locations

Unless overridden in config, the pipeline uses:

- Cache root: `C:\temp\revit_detail_intelligence\cache`
- Preview cache: `C:\temp\revit_detail_intelligence\cache\previews`
- Output root: `C:\temp\revit_detail_intelligence\output`
- Contact folders: `C:\temp\revit_detail_intelligence\output\contacts`
- Many-to-many outputs: `C:\temp\revit_detail_intelligence\output\many_to_many`

## 1) Stage-1 cache storage

Stage-1 feature bundles use a two-layer cache:

1. **In-memory layer** for same-process speed.
2. **Disk layer** for reuse across process restarts.

Disk records are written per view under:

- `...\cache\view_features\view_<view_id>.json`

Cache reuse requires:

- `view_id` match,
- `state_hash` match,
- `pipeline_version` match,
- schema version match.

If a disk entry is incompatible, it is invalidated and rebuilt.

Diagnostic statuses:

- `hit_memory`
- `hit_disk`
- `miss`
- `invalidated`
- `rebuilt`

## 2) Contact folder review artifacts (replaces composite contact sheet)

For one-to-many search, the system now creates a per-seed contact folder:

- `...\output\contacts\seed_<seed_view_id>`

Folder contents:

- seed PNG: `rank_00__<view_name>__id_<view_id>.png`
- ranked candidate PNGs:
  - `rank_<NN>__score_<SCORE>__conf_<CONFIDENCE>__<view_name>__id_<view_id>.png`
- `results.json` with ranking metadata

Only the **seed + final shortlisted candidates** are exported/rasterized.

Previews are exported with Revit `ExportImage` and cached in `...\cache\previews\view_<view_id>.png`.
Existing preview cache files are reused when their resolution meets the configured longest-side requirement.

## 3) Global runs index for portfolio analysis

Each one-to-many run appends seed→candidate rows to:

- `...\output\contacts\runs_index.csv`

This acts as a global edge list for later clustering/duplicate analysis.

## 4) Many-to-many mode

Many-to-many remains available as stage-1 execution mode:

- `find_similar_views_many_to_many(query_views, corpus_views, ...)`

Outputs:

- `...\output\many_to_many\<run_id>_edges.json`
- `...\output\many_to_many\<run_id>_edges.csv`

## 5) Symbol raster debug artifact retention (optional)

Production symbol raster rebuilds always write the required durable cache JSON under:

- `...\cache\symbol_rasters\<family>\<cache_key_hash>.json`

Debug-only retained PNG copies are now optional and controlled by:

- `CONFIG["symbol_raster_retain_debug_artifacts"]` (default: `False`)

When enabled (`True`), rebuilds also retain exported PNG artifacts under:

- `...\cache\symbol_rasters_png\<family>\<cache_key_hash>.png`

When disabled (`False`, production default), the pipeline still decodes the temporary exported PNG to compute points, but skips the retained PNG copy/write. This reduces avoidable file I/O without changing normal cache behavior.

Compatibility note:

- Existing debugging workflows that inspect retained PNG files should explicitly set `symbol_raster_retain_debug_artifacts=True`.
- Normal indexing and cache reuse behavior is unchanged with either setting.

## Deferred scope

Still deferred:

- full multi-file corpus orchestration/indexing,
- deep stage-2 raster rollout beyond current scope.
