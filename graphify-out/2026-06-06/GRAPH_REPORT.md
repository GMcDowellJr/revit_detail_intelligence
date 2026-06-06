# Graph Report - .  (2026-06-06)

## Corpus Check
- Corpus is ~41,882 words - fits in a single context window. You may not need a graph.

## Summary
- 683 nodes · 1389 edges · 44 communities (41 shown, 3 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 187 edges (avg confidence: 0.77)
- Token cost: 67,662 input · 0 output

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
- [[_COMMUNITY_Dynamo Entrypoint|Dynamo Entrypoint]]
- [[_COMMUNITY_PR Template|PR Template]]

## God Nodes (most connected - your core abstractions)
1. `find_similar_views()` - 22 edges
2. `IndexDiagnosticAccumulator` - 21 edges
3. `_collect_canonical_points_for_context()` - 20 edges
4. `_load_symbol_raster()` - 20 edges
5. `str` - 18 edges
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
- `TOKEN_SIMILARITY weighted Jaccard (pseudocode)` --semantically_similar_to--> `Token Similarity (weighted Jaccard)`  [INFERRED] [semantically similar]
  src/pseudocode_pipeline_v0.1.0.txt → docs/similarity-matching.md
- `GEOM_SIMILARITY cosine (pseudocode)` --semantically_similar_to--> `Geometry Similarity (cosine/histogram distance)`  [INFERRED] [semantically similar]
  src/pseudocode_pipeline_v0.1.0.txt → docs/similarity-matching.md
- `EXPLAIN_MATCH (pseudocode)` --semantically_similar_to--> `Match Explainability (shared tokens, geometry diffs)`  [INFERRED] [semantically similar]
  src/pseudocode_pipeline_v0.1.0.txt → docs/similarity-matching.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Feature Extraction Pipeline (tokens + geometry fingerprint + fine metrics)** — src_pseudocode_pipeline_extract_features, docs_pipeline_step4_provenance, docs_pipeline_step5_geometry_fingerprint, claude_md_viewfeatures, docs_detail_indexing_feature_storage [INFERRED 0.85]
- **Two-Stage Similarity Ranking (Stage-1 token/geom, Stage-2 raster re-rank)** — src_pseudocode_pipeline_find_similar_views, src_pseudocode_symbol_cache_stage2_rerank, docs_similarity_combined_score, docs_similarity_confidence_tiers, docs_pipeline_step8_confidence_ranking [INFERRED 0.85]
- **Cache Layer Architecture (in-memory, disk, symbol, view raster)** — docs_feature_cache_review_view_feature_cache, docs_feature_cache_review_symbol_cache, docs_runtime_storage_two_layer_cache, src_pseudocode_symbol_cache_symbolcache, src_pseudocode_symbol_cache_viewrastersignature [INFERRED 0.85]

## Communities (44 total, 3 thin omitted)

### Community 0 - "View Feature Cache"
Cohesion: 0.09
Nodes (49): _bundle_from_dict(), _bundle_to_dict(), cache_file_for_view(), deserialize_cache_entry(), _doc_scope_from_bundle(), _doc_scope_from_source(), get_cached_bundle_with_diagnostics(), invalidate_cache_record() (+41 more)

### Community 1 - "Legacy Similarity Script"
Cohesion: 0.07
Nodes (61): _add_token(), _bbox(), bbox_aspect_ratio(), bbox_diagonal(), bin_index(), build_token_df(), _build_token_idf(), _category_name() (+53 more)

### Community 2 - "Symbol Raster Pipeline"
Cohesion: 0.08
Nodes (46): _actual_instance_length_ft(), _apply_canonical_instance_transform(), _build_symbol_instance_context(), _cache_file_path(), _cleanup_export_tmp_dir(), _collect_canonical_points_for_context(), _collect_points_for_element(), collect_raster_points_for_view() (+38 more)

### Community 3 - "Similarity Search Pipeline"
Cohesion: 0.08
Nodes (48): legacy_view_features_from_search(), Compatibility adapter for the existing stage-1 similarity scorer., ViewFeatures, _build_state_context(), _bundle_source_scope(), collect_token_data_for_view(), _doc_provenance(), _doc_scoped_cache_path() (+40 more)

### Community 4 - "Symbol Cache Layer"
Cohesion: 0.11
Nodes (42): aggregate_symbol_descriptors(), build_symbol_descriptor(), build_validity_token(), compute_cache_stats(), cosine_sim(), descriptor_similarity_best_of_variants(), descriptor_similarity_variant(), DescriptorVariant (+34 more)

### Community 5 - "IO Paths and File Routing"
Cohesion: 0.09
Nodes (40): ensure_dir(), resolve_contact_sheets_dir(), resolve_contacts_dir(), resolve_many_to_many_dir(), resolve_output_root(), resolve_preview_cache_dir(), run_stamp(), _cand_file_name() (+32 more)

### Community 6 - "Feature Cache Abstraction"
Cohesion: 0.11
Nodes (22): FeatureCache, Disk-backed JSON cache for ViewFeatures (roadmap track).  NOTE: The active v0.3, In-process + disk-backed cache for extracted ViewFeatures dicts.      Parameters, Return cached features dict or None., Store features dict and flush to disk., Remove all entries for a given view_id (any element_count)., Wipe the entire cache (memory + disk)., _make_cache() (+14 more)

### Community 7 - "Config and Fine Metrics"
Cohesion: 0.14
Nodes (22): default_idf_for_doc_count(), bbox_aspect_ratio(), build_fine_metrics(), linework_density(), bin_index(), geom_fingerprint_knn(), k_nearest_neighbors(), normalize_l1() (+14 more)

### Community 8 - "Symbol Raster Analysis Scripts"
Cohesion: 0.17
Nodes (24): analyze_base_groups(), approx_symmetric_chamfer(), bbox_stats(), build_equivalence_labels(), build_recommendations(), compare_schema(), dedupe_quantized_points(), discover_files() (+16 more)

### Community 9 - "Symbol Raster Regression Tests"
Cohesion: 0.19
Nodes (20): _clear_symbol_raster_memory_cache(), _load_symbol_raster(), test_apply_canonical_instance_transform_handles_rotation_mirror_and_translation(), test_cache_miss_skips_retained_png_when_debug_artifacts_disabled(), test_cache_miss_uses_canonical_bounds_not_instance_obb_with_retained_artifacts(), test_collect_canonical_points_line_based_uses_canonical_bounds_for_export_pixels(), test_collect_canonical_points_records_export_pixel_metadata(), test_collect_canonical_points_uses_memory_after_disk_hit() (+12 more)

### Community 10 - "View Preview Export"
Cohesion: 0.19
Nodes (18): _build_contact_folder_for_results(), _find_exported_preview_file(), generate_and_cache_view_preview(), get_cached_view_preview(), _has_required_resolution(), _png_size(), _preview_file_path(), _preview_filename() (+10 more)

### Community 11 - "Dynamo Thin Runner"
Cohesion: 0.18
Nodes (15): _candidate_entrypoints(), _candidate_roots(), _expand_repo_root(), _load_script_text(), _normalize_inputs(), _pop_import_paths(), _project_import_paths(), _push_import_paths() (+7 more)

### Community 12 - "Index Diagnostic Accumulator"
Cohesion: 0.14
Nodes (6): IndexDiagnosticAccumulator, normalize_stage_timings(), Accumulates per-view stats incrementally as bundles are extracted., Append one JSON Lines record for this view to path., test_normalize_stage_timings_filters_invalid_rows(), test_same_view_repeats_of_first_seen_type_remain_cold_for_temperature()

### Community 13 - "PR Comment Auditor"
Cohesion: 0.24
Nodes (13): annotate_staleness(), _fetch_all_threads(), fetch_merged_prs(), _first_nonempty_line(), _graphql(), is_file_stale(), main(), Execute a GitHub GraphQL query; raise on HTTP or API errors. (+5 more)

### Community 14 - "Diagnostic Sidecars"
Cohesion: 0.19
Nodes (8): build_config_snapshot(), distribution_stats(), percentile(), Collects timing checkpoints and builds the search sidecar payload., resolve_search_sidecar_path(), SearchDiagnosticBuilder, _utc_now_iso(), test_distribution_stats_non_empty_and_empty()

### Community 15 - "Sidecar Path Resolution"
Cohesion: 0.17
Nodes (11): resolve_index_sidecar_path(), write_json_sidecar(), resolve_cache_root(), build_token_df_from_features(), build_token_idf(), check_feature_richness(), find_similar_views(), apply_geom_dominant_suppression() (+3 more)

### Community 16 - "Architecture Docs (CLAUDE.md)"
Cohesion: 0.18
Nodes (12): Architecture Principles (Deterministic, Explainable, Scale-tolerant, Model-first), Revit Detail Intelligence Project, sample_view_fingerprints() diagnostic mode, ViewFeatures (feature container), Architecture Diagram (Mermaid flowchart), Drafting View Indexing, Feature Storage (token multiset + geometry fingerprint), Detail Indexing Document (+4 more)

### Community 17 - "Symbol Cache Pseudocode"
Cohesion: 0.20
Nodes (12): build_symbol_descriptor_family_doc (Mode A), build_symbol_descriptor_isolated_render (Mode B), build_symbol_cache (orchestration + coverage), DescriptorVariant (uniform/anisotropic normalization), normalize_image_variant (image preprocessing), Stage1Result (data model), Stage2Result (data model), SymbolCache (data model) (+4 more)

### Community 18 - "Scoring Config and Calibration"
Cohesion: 0.18
Nodes (11): CONFIG dict (tunable parameters), Composite Scoring Formula, Ground Truth Dataset for Validation, Confidence Threshold Calibration, Calibration and Validation Document, Step 7: Similarity Matching, Combined Similarity Score (weighted composite), Confidence Tiers (HIGH/MED/LOW) (+3 more)

### Community 19 - "Cache Temperature Diagnostics"
Cohesion: 0.18
Nodes (7): classify_cache_temperature(), Collects symbol-raster lookup diagnostics for one view., ViewSymbolRasterPerfAccumulator, test_cache_temperature_is_unchanged_by_cache_layer_field(), test_classify_cache_temperature_deterministic(), test_repeated_type_misses_stay_cold_without_run_seen_bias(), test_view_symbol_perf_cohorts_and_zero_symbol_views()

### Community 20 - "Sidecar Unit Tests"
Cohesion: 0.33
Nodes (9): _bundle(), _jsonl_bundle(), test_extract_bundle_with_cache_returns_tuple(), test_finalize_cache_temperature_summary(), test_flush_view_record_appends_across_calls(), test_flush_view_record_creates_jsonl(), test_flush_view_record_survives_missing_optional_fields(), test_index_diagnostic_accumulator_finalize_with_flags_and_stopwords() (+1 more)

### Community 21 - "Symbol Raster Diagnostic Tests"
Cohesion: 0.35
Nodes (10): _clear_symbol_raster_memory_cache(), _load_symbol_raster(), test_cache_entry_validation_rejects_invalid_points_payload(), test_cache_entry_validation_requires_schema_and_pipeline_version(), test_collect_points_emits_cache_lookup_summary(), test_collect_points_emits_miss_summary_on_rebuild_export_failure(), test_collect_raster_points_accepts_diagnostic_callback(), test_collect_raster_points_applies_per_instance_transforms_after_group_lookup() (+2 more)

### Community 22 - "Architecture Similarity Diagram"
Cohesion: 0.22
Nodes (9): Architecture Diagram: Similarity Pipeline (Mermaid), Symbol Cache (in similarity pipeline diagram), Visual Re-ranking (Stage-2 raster re-rank), feature_cache.py (roadmap, not on runtime path), Feature Cache Review (April 2026), symbol_cache.py (in-memory, no disk persistence), Geometry Similarity (cosine/histogram distance), stage2_rerank (two-stage integration) (+1 more)

### Community 23 - "Pipeline Architecture Docs"
Cohesion: 0.22
Nodes (9): 8-Step Pipeline Architecture, Step 1: Section Candidate Generation, Step 2: Geometry Extraction, Step 3: Endpoint Clustering, Step 4: Provenance Extraction, Step 8: Confidence Ranking, Index Aggregate Timing Fields (stage_timing_summary), Stage Timing Diagnostics Document (+1 more)

### Community 24 - "Pipeline Pseudocode"
Cohesion: 0.42
Nodes (9): EXPLAIN_MATCH (pseudocode), EXTRACT_FEATURES (pseudocode), FIND_SIMILAR_VIEWS (pseudocode), FINE_SIMILARITY Gaussian (pseudocode), GEOM_FINGERPRINT_KNN (pseudocode), GEOM_SIMILARITY cosine (pseudocode), ROBUST_SCALE (pseudocode), TOKEN_SIMILARITY weighted Jaccard (pseudocode) (+1 more)

### Community 25 - "Runtime Storage Design"
Cohesion: 0.25
Nodes (8): view_feature_cache.py (production runtime path), Contact Folder Output (per-seed ranked PNGs), Many-to-many Mode (find_similar_views_many_to_many), Runtime Storage and v0.3.2 Operational Notes, Global Runs Index CSV (edge list for clustering), Symbol Raster Debug Artifact Retention (CONFIG flag), Two-layer Cache (in-memory + disk per view), Validity Token (deterministic invalidation)

### Community 26 - "Output Formatting"
Cohesion: 0.32
Nodes (5): Return Dynamo-friendly score rows in a stable field order.      Row order:, to_dynamo_score_list(), Dynamo (CPython3) script for Revit 2025. Feature-based similarity matching for d, test_to_dynamo_score_list_can_omit_header(), test_to_dynamo_score_list_field_order()

### Community 27 - "Ranking and Similarity Metrics"
Cohesion: 0.32
Nodes (4): explain_match(), fine_similarity(), gaussian_sim(), top_shared_bins()

### Community 28 - "Verification Notes"
Cohesion: 0.33
Nodes (6): find_similar_views() main algorithm, golden_compare.py (score parity harness), Harness Verification Note (golden compare), DSE modular package (src/dse/), Dynamo Thin Runner (src/dynamo_thin_runner.py), README: Revit Detail Intelligence

### Community 29 - "Golden Test Harness"
Cohesion: 0.53
Nodes (5): _compare_results(), _float_close(), Golden output harness for Dynamo/Revit environment.  Usage inside Dynamo CPython, run_golden_compare(), _run_script()

### Community 30 - "Geometry Fingerprint Docs"
Cohesion: 0.50
Nodes (5): Histogram Construction (edge length + angle), Neighborhood Graph (k-NN), Geometry Fingerprint Document, Scale Normalization (characteristic length), Step 5: Geometry Fingerprint

## Knowledge Gaps
- **36 isolated node(s):** `object`, `bool`, `str`, `int`, `object` (+31 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `collect_token_data_for_view()` connect `Similarity Search Pipeline` to `Legacy Similarity Script`?**
  _High betweenness centrality (0.152) - this node is a cross-community bridge._
- **Why does `ViewFeatures` connect `Legacy Similarity Script` to `Symbol Cache Layer`?**
  _High betweenness centrality (0.091) - this node is a cross-community bridge._
- **Why does `type_signature()` connect `Legacy Similarity Script` to `Symbol Raster Pipeline`, `Similarity Search Pipeline`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `find_similar_views()` (e.g. with `resolve_view_cache_root()` and `build_config_snapshot()`) actually correct?**
  _`find_similar_views()` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `IndexDiagnosticAccumulator` (e.g. with `find_similar_views()` and `index_views()`) actually correct?**
  _`IndexDiagnosticAccumulator` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `str` (e.g. with `ViewFeatureBundle` and `ViewPresentationSummary`) actually correct?**
  _`str` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Execute a GitHub GraphQL query; raise on HTTP or API errors.`, `Return the complete list of review-thread nodes for a PR, fetching     continuat`, `Return a list of PR dicts, each with unresolved review threads, merged     withi` to the rest of the system?**
  _72 weakly-connected nodes found - possible documentation gaps or missing edges._