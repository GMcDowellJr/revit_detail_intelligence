# Runtime Storage and v0.3 Roadmap Clarifications

This note clarifies three common questions for the current `revit_detail_intelligence` implementation.

## 1) Where are the caches stored?

### View feature cache (stage-1 view bundle cache)
- **Current behavior (v0.3):** in-memory only.
- Implemented as process-local singleton `GLOBAL_VIEW_FEATURE_CACHE` in `src/dse/cache/view_feature_cache.py`.
- Cache entries are keyed by `view_id` and validated by **`state_hash` + `pipeline_version` + `schema_version`** before reuse.
- **Persistence:** none yet; cache is reset when Dynamo/Revit Python process reloads.

### Symbol cache
- `src/dse/cache/symbol_cache.py` currently provides dataclasses and helper utilities.
- There is no wired disk persistence path in the active `dse.pipelines.search` path yet.

## 2) How do I turn on or get many-to-many?

- **Not available in v0.3** (by design in this additive pass).
- One-to-many is implemented via `find_similar_views(query_view, corpus_views, top_n=...)`.
- A forward-compatible stub `find_similar_views_many_to_many(...)` now exists and intentionally raises `NotImplementedError` with a clear message.
- `CONFIG["many_to_many"]["enabled"]` is included as a roadmap flag placeholder only and does not activate orchestration yet.

## 3) Where are the contact sheets stored?

- **Contact sheet image generation is not implemented in v0.3**.
- Therefore there is currently no contact-sheet output directory.
- What is implemented now:
  - `ViewPresentationSummary` is generated during feature extraction with `display_name`, `preview_key`, `top_tokens`, `top_symbols`, and `feature_summary`.
  - These summaries are included in sample/report payloads and candidate result payloads so a future contact-sheet writer can consume them without recomputing stage-1 features.

## Deferred scope reminder

Still deferred after v0.3:
- multi-file corpus orchestration/indexing,
- stage-2 raster similarity implementation,
- PNG contact-sheet rendering and storage policy.
