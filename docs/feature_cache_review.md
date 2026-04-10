# Feature Cache Review (April 10, 2026, updated)

## Scope reviewed

- `src/dse/cache/feature_cache.py`
- `src/dse/cache/view_feature_cache.py`
- `src/dse/cache/symbol_cache.py`
- `src/dse/pipelines/search.py`
- cache/search tests under `tests/`

## Findings

1. **`feature_cache.py` is not on the current runtime path, but appears to be roadmap work rather than a deprecated path.**
   - Runtime search/indexing imports and calls `view_feature_cache` helpers, not `FeatureCache` from `feature_cache.py`.
   - `FeatureCache` is still covered by tests, but there are no runtime imports of `dse.cache.feature_cache` from pipeline modules.

2. **Current production path uses `view_feature_cache.py` + per-view disk records.**
   - `search.py` uses `get_cached_bundle_with_diagnostics(...)` and `put_bundle_in_caches(...)` and writes doc-scoped cache records for source document disambiguation.
   - This design is coherent with v0.3 bundle/schema models and test coverage for cache-hit/miss/invalidation semantics.

3. **`symbol_cache.py` is in-memory for descriptors unless higher-level persistence exists elsewhere.**
   - `SymbolCacheModel` supports descriptor math and stats, but this file alone does not persist descriptors to disk.
   - If symbol cache persistence is expected, implementation is still pending in another module or needs to be added.

4. **Error handling posture differs by cache path.**
   - `view_feature_cache.py` warns on read failures and treats bad records as misses.
   - `feature_cache.py` silently swallows read/write exceptions and starts fresh.

## What needs to be done

### Priority 1 (product/ownership clarity)

- **Decide and document ownership/status of `feature_cache.py` as roadmap work.**
  - If it is an active roadmap track, define entry criteria for integration with `search.py` and link that work item in code/docs.
  - If plans changed and it is no longer targeted for integration, then consider deprecation/removal after confirming no external callers depend on it.

### Priority 2 (cache consistency)

- **Standardize cache failure telemetry.**
  - Either add warnings/diagnostics to `feature_cache.py` (to match `view_feature_cache.py`) or retire it.

### Priority 3 (symbol cache completeness)

- **Confirm persistence expectations for symbol descriptors.**
  - If descriptors should survive process restarts, add explicit disk load/save helpers (schema + version checks + invalidation policy).

### Priority 4 (operational safeguards)

- **Add a small integration test that encodes the intended cache-selection policy.**
  - If current behavior is intentional, test that `search.py` stays on `view_feature_cache` until roadmap integration is explicitly enabled.

## Validation performed during review

- Ran targeted cache/search tests:
  - `tests/test_feature_cache.py`
  - `tests/test_view_feature_cache_v03.py`
  - `tests/test_symbol_cache_pipeline.py`
  - `tests/test_disk_cache_and_outputs_v031.py`
  - `tests/test_search_index_and_cache_loading.py`
- All passed in this environment.
