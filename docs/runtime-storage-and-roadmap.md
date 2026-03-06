# Runtime Storage and v0.3.x Operational Notes

## Default storage locations

Unless overridden in config, the pipeline uses:

- Cache root: `C:\temp\revit_detail_intelligence\cache`
- Output root: `C:\temp\revit_detail_intelligence\output`
- Contact sheets: `C:\temp\revit_detail_intelligence\output\contact_sheets`
- Many-to-many outputs: `C:\temp\revit_detail_intelligence\output\many_to_many`
- Previews: `C:\temp\revit_detail_intelligence\previews`

## 1) Stage-1 cache storage

Stage-1 feature bundles now use a two-layer cache:

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

Diagnostic statuses are recorded in presentation debug metadata:

- `hit_memory`
- `hit_disk`
- `miss`
- `invalidated`
- `rebuilt`

## 2) Many-to-many mode

Many-to-many is now implemented as a real stage-1 execution mode via:

- `find_similar_views_many_to_many(query_views, corpus_views, ...)`

Outputs are written to:

- `...\output\many_to_many\<run_id>_edges.json`
- `...\output\many_to_many\<run_id>_edges.csv`

Each row includes review-ready edge evidence (seed/candidate IDs and names, rank, total/token/geometry/layout/symbol scores, source doc fields, and explanation summary).

## 3) Contact sheets

PNG contact sheets are now generated for one-to-many results and written to:

- `...\output\contact_sheets\<run_id>_seed-<view_id>.png`

Sheet layout:

- seed tile first,
- ranked candidate tiles after,
- each tile includes rendered preview image (or placeholder fallback), name, id, rank/score, and optional source label.

Preview generation details:

- Drafting view previews are exported using Revit `ExportImage` API.
- Preview images are cached to disk and reused if already present for the view.
- Default preview size target uses ~2048 px longest side; contact sheet rendering downsamples to tile space.

## Deferred scope

Still deferred:

- full multi-file corpus orchestration/indexing,
- deep stage-2 raster rollout beyond current scope.
