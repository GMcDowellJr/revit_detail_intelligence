# Graph Report - .  (2026-06-22)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 740 nodes · 1431 edges · 54 communities (46 shown, 8 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 185 edges (avg confidence: 0.77)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `48fe3ba1`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_View Feature Cache|View Feature Cache]]
- [[_COMMUNITY_Legacy Similarity Script|Legacy Similarity Script]]
- [[_COMMUNITY_Symbol Raster Pipeline|Symbol Raster Pipeline]]
- [[_COMMUNITY_Similarity Search Pipeline|Similarity Search Pipeline]]
- [[_COMMUNITY_Symbol Cache Layer|Symbol Cache Layer]]
- [[_COMMUNITY_IO Paths and File Routing|IO Paths and File Routing]]
- [[_COMMUNITY_Feature Cache Abstraction|Feature Cache Abstraction]]
- [[_COMMUNITY_Config and Fine Metrics|Config and Fine Metrics]]
- [[_COMMUNITY_Symbol Raster Analysis Scripts|Symbol Raster Analysis Scripts]]
- [[_COMMUNITY_Symbol Raster Regression Tests|Symbol Raster Regression Tests]]
- [[_COMMUNITY_View Preview Export|View Preview Export]]
- [[_COMMUNITY_Dynamo Thin Runner|Dynamo Thin Runner]]
- [[_COMMUNITY_Index Diagnostic Accumulator|Index Diagnostic Accumulator]]
- [[_COMMUNITY_PR Comment Auditor|PR Comment Auditor]]
- [[_COMMUNITY_Diagnostic Sidecars|Diagnostic Sidecars]]
- [[_COMMUNITY_Sidecar Path Resolution|Sidecar Path Resolution]]
- [[_COMMUNITY_Architecture Docs (CLAUDE.md)|Architecture Docs (CLAUDE.md)]]
- [[_COMMUNITY_Symbol Cache Pseudocode|Symbol Cache Pseudocode]]
- [[_COMMUNITY_Scoring Config and Calibration|Scoring Config and Calibration]]
- [[_COMMUNITY_Cache Temperature Diagnostics|Cache Temperature Diagnostics]]
- [[_COMMUNITY_Sidecar Unit Tests|Sidecar Unit Tests]]
- [[_COMMUNITY_Symbol Raster Diagnostic Tests|Symbol Raster Diagnostic Tests]]
- [[_COMMUNITY_Architecture Similarity Diagram|Architecture Similarity Diagram]]
- [[_COMMUNITY_Pipeline Architecture Docs|Pipeline Architecture Docs]]
- [[_COMMUNITY_Pipeline Pseudocode|Pipeline Pseudocode]]
- [[_COMMUNITY_Runtime Storage Design|Runtime Storage Design]]
- [[_COMMUNITY_Output Formatting|Output Formatting]]
- [[_COMMUNITY_Ranking and Similarity Metrics|Ranking and Similarity Metrics]]
- [[_COMMUNITY_Verification Notes|Verification Notes]]
- [[_COMMUNITY_Golden Test Harness|Golden Test Harness]]
- [[_COMMUNITY_Geometry Fingerprint Docs|Geometry Fingerprint Docs]]
- [[_COMMUNITY_CI and Contributing|CI and Contributing]]
- [[_COMMUNITY_Placeholder Tests|Placeholder Tests]]
- [[_COMMUNITY_Cache Package Init|Cache Package Init]]
- [[_COMMUNITY_Dynamo Entrypoint|Dynamo Entrypoint]]
- [[_COMMUNITY_Diagnostics Package Init|Diagnostics Package Init]]
- [[_COMMUNITY_DSE Package Init|DSE Package Init]]
- [[_COMMUNITY_Features Package Init|Features Package Init]]
- [[_COMMUNITY_PR Template|PR Template]]
- [[_COMMUNITY_Outputs Package Init|Outputs Package Init]]
- [[_COMMUNITY_Pipelines Package Init|Pipelines Package Init]]
- [[_COMMUNITY_Ranking Package Init|Ranking Package Init]]
- [[_COMMUNITY_Revit API Package Init|Revit API Package Init]]
- [[_COMMUNITY_Test Configuration|Test Configuration]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 49|Community 49]]

## God Nodes (most connected - your core abstractions)
1. `find_similar_views` - 25 edges
2. `IndexDiagnosticAccumulator` - 20 edges
3. `_collect_canonical_points_for_context()` - 20 edges
4. `_load_symbol_raster()` - 20 edges
5. `graphify` - 20 edges
6. `ViewFeatureCacheEntry` - 17 edges
7. `ViewSearchFeatures` - 16 edges
8. `ViewStateSignature` - 15 edges
9. `ViewPresentationSummary` - 15 edges
10. `extract_features()` - 15 edges

## Surprising Connections (you probably didn't know these)
- `FIND_SIMILAR_VIEWS (pseudocode)` --semantically_similar_to--> `find_similar_views() main algorithm`  [INFERRED] [semantically similar]
  src/pseudocode_pipeline_v0.1.0.txt → CLAUDE.md
- `GEOM_FINGERPRINT_KNN (pseudocode)` --semantically_similar_to--> `Neighborhood Graph (k-NN)`  [INFERRED] [semantically similar]
  src/pseudocode_pipeline_v0.1.0.txt → docs/geometry-fingerprint.md
- `view_raster_similarity (cosine on descriptors)` --semantically_similar_to--> `Geometry Similarity (cosine/histogram distance)`  [INFERRED] [semantically similar]
  src/pseudocode_symbol-cache-view-raster-pipeline_v0.2.1.txt → docs/similarity-matching.md
- `Visual Re-ranking (Stage-2 raster re-rank)` --semantically_similar_to--> `stage2_rerank (two-stage integration)`  [INFERRED] [semantically similar]
  docs/architecture-diagram-similarity.md → src/pseudocode_symbol-cache-view-raster-pipeline_v0.2.1.txt
- `test_contact_folder_emits_placeholders_when_preview_missing()` --calls--> `create_contact_folder()`  [INFERRED]
  tests/test_disk_cache_and_outputs_v031.py → src/dse/outputs/contact_folder.py

## Import Cycles
- None detected.

## Communities (54 total, 8 thin omitted)

### Community 0 - "View Feature Cache"
Cohesion: 0.09
Nodes (51): _bundle_from_dict(), _bundle_to_dict(), cache_file_for_view(), deserialize_cache_entry(), _doc_scope_from_bundle(), _doc_scope_from_source(), get_cached_bundle_with_diagnostics(), invalidate_cache_record() (+43 more)

### Community 1 - "Legacy Similarity Script"
Cohesion: 0.07
Nodes (60): _add_token(), _bbox(), bbox_aspect_ratio(), bbox_diagonal(), bin_index(), build_token_df(), _build_token_idf(), _category_name() (+52 more)

### Community 2 - "Symbol Raster Pipeline"
Cohesion: 0.08
Nodes (46): _actual_instance_length_ft(), _apply_canonical_instance_transform(), _build_symbol_instance_context(), _cache_file_path(), _cleanup_export_tmp_dir(), _collect_canonical_points_for_context(), _collect_points_for_element(), collect_raster_points_for_view() (+38 more)

### Community 3 - "Similarity Search Pipeline"
Cohesion: 0.08
Nodes (47): legacy_view_features_from_search(), Compatibility adapter for the existing stage-1 similarity scorer., ViewFeatures, _build_state_context(), _bundle_source_scope(), collect_token_data_for_view(), _doc_provenance(), _doc_scoped_cache_path() (+39 more)

### Community 4 - "Symbol Cache Layer"
Cohesion: 0.11
Nodes (38): aggregate_symbol_descriptors(), build_symbol_descriptor(), build_validity_token(), compute_cache_stats(), cosine_sim(), descriptor_similarity_variant(), DescriptorVariant, hash_config() (+30 more)

### Community 5 - "IO Paths and File Routing"
Cohesion: 0.11
Nodes (36): ensure_dir(), resolve_cache_root(), resolve_contacts_dir(), resolve_many_to_many_dir(), resolve_output_root(), resolve_preview_cache_dir(), run_stamp(), _cand_file_name() (+28 more)

### Community 6 - "Feature Cache Abstraction"
Cohesion: 0.05
Nodes (35): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files, Part C - Merge AST + semantic into final extraction (+27 more)

### Community 7 - "Config and Fine Metrics"
Cohesion: 0.17
Nodes (24): analyze_base_groups(), approx_symmetric_chamfer(), bbox_stats(), build_equivalence_labels(), build_recommendations(), compare_schema(), dedupe_quantized_points(), discover_files() (+16 more)

### Community 8 - "Symbol Raster Analysis Scripts"
Cohesion: 0.12
Nodes (14): find_similar_views, search, symbol_raster_pipeline, default_idf_for_doc_count(), build_token_df_from_features(), build_token_idf(), check_feature_richness(), apply_geom_dominant_suppression() (+6 more)

### Community 9 - "Symbol Raster Regression Tests"
Cohesion: 0.19
Nodes (20): _clear_symbol_raster_memory_cache(), _load_symbol_raster(), test_apply_canonical_instance_transform_handles_rotation_mirror_and_translation(), test_cache_miss_skips_retained_png_when_debug_artifacts_disabled(), test_cache_miss_uses_canonical_bounds_not_instance_obb_with_retained_artifacts(), test_collect_canonical_points_line_based_uses_canonical_bounds_for_export_pixels(), test_collect_canonical_points_records_export_pixel_metadata(), test_collect_canonical_points_uses_memory_after_disk_hit() (+12 more)

### Community 10 - "View Preview Export"
Cohesion: 0.17
Nodes (6): Disk-backed JSON cache for ViewFeatures (roadmap track).  NOTE: The active v0.3, In-process + disk-backed cache for extracted ViewFeatures dicts.      Parameters, Return cached features dict or None., Store features dict and flush to disk., Remove all entries for a given view_id (any element_count)., Wipe the entire cache (memory + disk).

### Community 11 - "Dynamo Thin Runner"
Cohesion: 0.20
Nodes (17): _build_contact_folder_for_results(), _find_exported_preview_file(), generate_and_cache_view_preview(), get_cached_view_preview(), _has_required_resolution(), _png_size(), _preview_file_path(), _preview_filename() (+9 more)

### Community 12 - "Index Diagnostic Accumulator"
Cohesion: 0.18
Nodes (15): _candidate_entrypoints(), _candidate_roots(), _expand_repo_root(), _load_script_text(), _normalize_inputs(), _pop_import_paths(), _project_import_paths(), _push_import_paths() (+7 more)

### Community 13 - "PR Comment Auditor"
Cohesion: 0.23
Nodes (15): bbox_aspect_ratio(), build_fine_metrics(), linework_density(), bbox(), bbox_diagonal(), collect_curves_from_geometry(), _collect_points_for_curve(), _curve_angular_span_degrees() (+7 more)

### Community 14 - "Diagnostic Sidecars"
Cohesion: 0.31
Nodes (15): _make_cache(), Tests for src/dse/cache/feature_cache.py, _sample_features(), test_clear_wipes_all_entries(), test_corrupt_cache_file_starts_fresh(), test_disk_file_is_valid_json(), test_get_miss_returns_none(), test_invalidate_nonexistent_view_is_noop() (+7 more)

### Community 15 - "Sidecar Path Resolution"
Cohesion: 0.22
Nodes (15): Step 7: Similarity Matching, Match Explainability (shared tokens, geometry diffs), Geometry Similarity (cosine/histogram distance), Similarity Matching Document, Token Similarity (weighted Jaccard), EXPLAIN_MATCH (pseudocode), EXTRACT_FEATURES (pseudocode), FIND_SIMILAR_VIEWS (pseudocode) (+7 more)

### Community 16 - "Architecture Docs (CLAUDE.md)"
Cohesion: 0.24
Nodes (13): annotate_staleness(), _fetch_all_threads(), fetch_merged_prs(), _first_nonempty_line(), _graphql(), is_file_stale(), main(), Execute a GitHub GraphQL query; raise on HTTP or API errors. (+5 more)

### Community 17 - "Symbol Cache Pseudocode"
Cohesion: 0.18
Nodes (11): build_config_snapshot(), classify_cache_temperature(), distribution_stats(), percentile(), resolve_index_sidecar_path(), resolve_search_sidecar_path(), _utc_now_iso(), write_json_sidecar() (+3 more)

### Community 18 - "Scoring Config and Calibration"
Cohesion: 0.18
Nodes (6): IndexDiagnosticAccumulator, normalize_stage_timings(), Accumulates per-view stats incrementally as bundles are extracted., Append one JSON Lines record for this view to path., test_normalize_stage_timings_filters_invalid_rows(), test_same_view_repeats_of_first_seen_type_remain_cold_for_temperature()

### Community 19 - "Cache Temperature Diagnostics"
Cohesion: 0.18
Nodes (12): Architecture Principles (Deterministic, Explainable, Scale-tolerant, Model-first), Revit Detail Intelligence Project, sample_view_fingerprints() diagnostic mode, ViewFeatures (feature container), Architecture Diagram (Mermaid flowchart), Drafting View Indexing, Feature Storage (token multiset + geometry fingerprint), Detail Indexing Document (+4 more)

### Community 20 - "Sidecar Unit Tests"
Cohesion: 0.21
Nodes (12): build_symbol_descriptor_family_doc (Mode A), build_symbol_descriptor_isolated_render (Mode B), build_symbol_cache (orchestration + coverage), DescriptorVariant (uniform/anisotropic normalization), normalize_image_variant (image preprocessing), stage2_rerank (two-stage integration), SymbolCache (data model), SymbolDescriptor (data model) (+4 more)

### Community 21 - "Symbol Raster Diagnostic Tests"
Cohesion: 0.33
Nodes (9): _bundle(), _jsonl_bundle(), test_extract_bundle_with_cache_returns_tuple(), test_finalize_cache_temperature_summary(), test_flush_view_record_appends_across_calls(), test_flush_view_record_creates_jsonl(), test_flush_view_record_survives_missing_optional_fields(), test_index_diagnostic_accumulator_finalize_with_flags_and_stopwords() (+1 more)

### Community 22 - "Architecture Similarity Diagram"
Cohesion: 0.35
Nodes (10): _clear_symbol_raster_memory_cache(), _load_symbol_raster(), test_cache_entry_validation_rejects_invalid_points_payload(), test_cache_entry_validation_requires_schema_and_pipeline_version(), test_collect_points_emits_cache_lookup_summary(), test_collect_points_emits_miss_summary_on_rebuild_export_failure(), test_collect_raster_points_accepts_diagnostic_callback(), test_collect_raster_points_applies_per_instance_transforms_after_group_lookup() (+2 more)

### Community 23 - "Pipeline Architecture Docs"
Cohesion: 0.22
Nodes (9): CONFIG dict (tunable parameters), find_similar_views() main algorithm, Composite Scoring Formula, Combined Similarity Score (weighted composite), golden_compare.py (score parity harness), Harness Verification Note (golden compare), DSE modular package (src/dse/), Dynamo Thin Runner (src/dynamo_thin_runner.py) (+1 more)

### Community 24 - "Pipeline Pseudocode"
Cohesion: 0.22
Nodes (9): 8-Step Pipeline Architecture, Step 1: Section Candidate Generation, Step 2: Geometry Extraction, Step 3: Endpoint Clustering, Step 4: Provenance Extraction, Step 8: Confidence Ranking, Index Aggregate Timing Fields (stage_timing_summary), Stage Timing Diagnostics Document (+1 more)

### Community 25 - "Runtime Storage Design"
Cohesion: 0.25
Nodes (7): Step 6b - Wiki (only if --wiki flag), Step 7d - MCP server (only if --mcp flag), graphify reference: extra exports and benchmark, Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 26 - "Output Formatting"
Cohesion: 0.25
Nodes (8): view_feature_cache.py (production runtime path), Contact Folder Output (per-seed ranked PNGs), Many-to-many Mode (find_similar_views_many_to_many), Runtime Storage and v0.3.2 Operational Notes, Global Runs Index CSV (edge list for clustering), Symbol Raster Debug Artifact Retention (CONFIG flag), Two-layer Cache (in-memory + disk per view), Validity Token (deterministic invalidation)

### Community 27 - "Ranking and Similarity Metrics"
Cohesion: 0.32
Nodes (5): Return Dynamo-friendly score rows in a stable field order.      Row order:, to_dynamo_score_list(), Dynamo (CPython3) script for Revit 2025. Feature-based similarity matching for d, test_to_dynamo_score_list_can_omit_header(), test_to_dynamo_score_list_field_order()

### Community 28 - "Verification Notes"
Cohesion: 0.29
Nodes (7): graphify, graphify explain, graphify path, graphify query, graphify update, Key Entry Points, Project Overview

### Community 29 - "Golden Test Harness"
Cohesion: 0.29
Nodes (5): Collects symbol-raster lookup diagnostics for one view., ViewSymbolRasterPerfAccumulator, test_cache_temperature_is_unchanged_by_cache_layer_field(), test_repeated_type_misses_stay_cold_without_run_seen_bias(), test_view_symbol_perf_cohorts_and_zero_symbol_views()

### Community 30 - "Geometry Fingerprint Docs"
Cohesion: 0.33
Nodes (6): Architecture Diagram: Similarity Pipeline (Mermaid), Symbol Cache (in similarity pipeline diagram), Visual Re-ranking (Stage-2 raster re-rank), feature_cache.py (roadmap, not on runtime path), Feature Cache Review (April 2026), symbol_cache.py (in-memory, no disk persistence)

### Community 31 - "CI and Contributing"
Cohesion: 0.60
Nodes (5): bin_index(), geom_fingerprint_knn(), k_nearest_neighbors(), normalize_l1(), robust_scale()

### Community 32 - "Placeholder Tests"
Cohesion: 0.53
Nodes (5): _compare_results(), _float_close(), Golden output harness for Dynamo/Revit environment.  Usage inside Dynamo CPython, run_golden_compare(), _run_script()

### Community 34 - "Dynamo Entrypoint"
Cohesion: 0.50
Nodes (5): Histogram Construction (edge length + angle), Neighborhood Graph (k-NN), Geometry Fingerprint Document, Scale Normalization (characteristic length), Step 5: Geometry Fingerprint

### Community 35 - "Diagnostics Package Init"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 36 - "DSE Package Init"
Cohesion: 0.50
Nodes (3): For /graphify explain, graphify reference: query, path, explain, For /graphify path

### Community 37 - "Features Package Init"
Cohesion: 0.50
Nodes (3): For --cluster-only, For --update (incremental re-extraction), graphify reference: incremental update and cluster-only

### Community 38 - "PR Template"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

### Community 39 - "Outputs Package Init"
Cohesion: 0.50
Nodes (4): Ground Truth Dataset for Validation, Confidence Threshold Calibration, Calibration and Validation Document, Confidence Tiers (HIGH/MED/LOW)

## Knowledge Gaps
- **91 isolated node(s):** `Usage`, `Part A - Structural extraction for code files`, `Part C - Merge AST + semantic into final extraction`, `Step 9 - Save manifest, update cost tracker, clean up, and report`, `Interpreter guard for subcommands` (+86 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `collect_token_data_for_view()` connect `Similarity Search Pipeline` to `Legacy Similarity Script`?**
  _High betweenness centrality (0.111) - this node is a cross-community bridge._
- **Why does `ViewFeatures` connect `Legacy Similarity Script` to `Symbol Cache Layer`?**
  _High betweenness centrality (0.070) - this node is a cross-community bridge._
- **Why does `type_signature()` connect `Legacy Similarity Script` to `Symbol Raster Pipeline`, `Similarity Search Pipeline`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `find_similar_views` (e.g. with `build_config_snapshot()` and `IndexDiagnosticAccumulator`) actually correct?**
  _`find_similar_views` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `IndexDiagnosticAccumulator` (e.g. with `find_similar_views` and `index_views()`) actually correct?**
  _`IndexDiagnosticAccumulator` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Usage`, `Part A - Structural extraction for code files`, `Part C - Merge AST + semantic into final extraction` to the rest of the system?**
  _127 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `View Feature Cache` be split into smaller, more focused modules?**
  _Cohesion score 0.08516242317822652 - nodes in this community are weakly interconnected._