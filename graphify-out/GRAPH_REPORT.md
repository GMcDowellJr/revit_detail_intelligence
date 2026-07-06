# Graph Report - .  (2026-07-06)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 710 nodes · 1307 edges · 48 communities (41 shown, 7 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 134 edges (avg confidence: 0.76)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `390392b2`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_dynamo_view_similarity_legacy.py|dynamo_view_similarity_legacy.py]]
- [[_COMMUNITY_symbol_raster.py|symbol_raster.py]]
- [[_COMMUNITY_IndexDiagnosticAccumulator|IndexDiagnosticAccumulator]]
- [[_COMMUNITY_symbol_cache.py|symbol_cache.py]]
- [[_COMMUNITY_view_feature_cache.py|view_feature_cache.py]]
- [[_COMMUNITY_io_paths.py|io_paths.py]]
- [[_COMMUNITY_graphify|graphify]]
- [[_COMMUNITY_geometry_2d.py|geometry_2d.py]]
- [[_COMMUNITY_analyze_symbol_raster_cache.py|analyze_symbol_raster_cache.py]]
- [[_COMMUNITY_collect.py|collect.py]]
- [[_COMMUNITY_test_search_index_and_cache_loading.py|test_search_index_and_cache_loading.py]]
- [[_COMMUNITY_test_symbol_raster_cache_regressions.py|test_symbol_raster_cache_regressions.py]]
- [[_COMMUNITY_feature_cache.py|feature_cache.py]]
- [[_COMMUNITY_preview_export.py|preview_export.py]]
- [[_COMMUNITY_dynamo_thin_runner.py|dynamo_thin_runner.py]]
- [[_COMMUNITY_test_feature_cache.py|test_feature_cache.py]]
- [[_COMMUNITY_audit_unresolved_comments.py|audit_unresolved_comments.py]]
- [[_COMMUNITY_Revit Detail Intelligence Project|Revit Detail Intelligence Project]]
- [[_COMMUNITY_Architecture Diagram Similarity Pipeline (Mermaid)|Architecture Diagram: Similarity Pipeline (Mermaid)]]
- [[_COMMUNITY_Symbol Cache + View Raster Pipeline Pseudocode v0.2.1|Symbol Cache + View Raster Pipeline Pseudocode v0.2.1]]
- [[_COMMUNITY_test_symbol_raster_diagnostics.py|test_symbol_raster_diagnostics.py]]
- [[_COMMUNITY_8-Step Pipeline Architecture|8-Step Pipeline Architecture]]
- [[_COMMUNITY_FIND_SIMILAR_VIEWS (pseudocode)|FIND_SIMILAR_VIEWS (pseudocode)]]
- [[_COMMUNITY_graphify reference extra exports and benchmark|graphify reference: extra exports and benchmark]]
- [[_COMMUNITY_Similarity Matching Document|Similarity Matching Document]]
- [[_COMMUNITY_Runtime Storage and v0.3.2 Operational Notes|Runtime Storage and v0.3.2 Operational Notes]]
- [[_COMMUNITY_to_dynamo_score_list|to_dynamo_score_list]]
- [[_COMMUNITY_graphify|graphify]]
- [[_COMMUNITY_find_similar_views() main algorithm|find_similar_views() main algorithm]]
- [[_COMMUNITY_golden_compare.py|golden_compare.py]]
- [[_COMMUNITY_Geometry Fingerprint Document|Geometry Fingerprint Document]]
- [[_COMMUNITY_graphify reference add a URL and watch a folder|graphify reference: add a URL and watch a folder]]
- [[_COMMUNITY_graphify reference query, path, explain|graphify reference: query, path, explain]]
- [[_COMMUNITY_graphify reference incremental update and cluster-only|graphify reference: incremental update and cluster-only]]
- [[_COMMUNITY_graphify reference commit hook and native CLAUDE.md integration|graphify reference: commit hook and native CLAUDE.md integration]]
- [[_COMMUNITY_graphify reference GitHub clone and cross-repo merge|graphify reference: GitHub clone and cross-repo merge]]
- [[_COMMUNITY_graphify reference transcribe video and audio|graphify reference: transcribe video and audio]]
- [[_COMMUNITY_find_similar_views|find_similar_views]]
- [[_COMMUNITY_extraction-spec|extraction-spec.md]]
- [[_COMMUNITY_Contributing Branch + CI-gated Workflow|Contributing: Branch + CI-gated Workflow]]
- [[_COMMUNITY_Dynamo INOUT Entrypoint Interface|Dynamo IN/OUT Entrypoint Interface]]
- [[_COMMUNITY_Pull Request Template|Pull Request Template]]

## God Nodes (most connected - your core abstractions)
1. `_collect_canonical_points_for_context()` - 20 edges
2. `_load_symbol_raster()` - 20 edges
3. `graphify` - 20 edges
4. `IndexDiagnosticAccumulator` - 18 edges
5. `ViewFeatureCacheEntry` - 16 edges
6. `ViewSearchFeatures` - 15 edges
7. `extract_features()` - 15 edges
8. `ViewStateSignature` - 14 edges
9. `ViewPresentationSummary` - 14 edges
10. `_make_cache()` - 14 edges

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
- **DSE Pipeline Cache** — src_dse_pipelines_search_find_similar_views, src_dse_cache_, src_revit_api_symbol_raster_symbol_raster_pipeline [EXTRACTED 0.75]

## Communities (48 total, 7 thin omitted)

### Community 0 - "dynamo_view_similarity_legacy.py"
Cohesion: 0.07
Nodes (60): _add_token(), _bbox(), bbox_aspect_ratio(), bbox_diagonal(), bin_index(), build_token_df(), _build_token_idf(), _category_name() (+52 more)

### Community 1 - "symbol_raster.py"
Cohesion: 0.08
Nodes (46): _actual_instance_length_ft(), _apply_canonical_instance_transform(), _build_symbol_instance_context(), _cache_file_path(), _cleanup_export_tmp_dir(), _collect_canonical_points_for_context(), _collect_points_for_element(), collect_raster_points_for_view() (+38 more)

### Community 2 - "IndexDiagnosticAccumulator"
Cohesion: 0.07
Nodes (31): classify_cache_temperature(), distribution_stats(), IndexDiagnosticAccumulator, normalize_stage_timings(), percentile(), Collects symbol-raster lookup diagnostics for one view., Accumulates per-view stats incrementally as bundles are extracted., Append one JSON Lines record for this view to path. (+23 more)

### Community 3 - "symbol_cache.py"
Cohesion: 0.11
Nodes (38): object, aggregate_symbol_descriptors(), build_symbol_descriptor(), build_validity_token(), compute_cache_stats(), cosine_sim(), descriptor_similarity_variant(), DescriptorVariant (+30 more)

### Community 4 - "view_feature_cache.py"
Cohesion: 0.16
Nodes (39): _bundle_from_dict(), _bundle_to_dict(), cache_file_for_view(), deserialize_cache_entry(), _doc_scope_from_bundle(), _doc_scope_from_source(), get_cached_bundle_with_diagnostics(), invalidate_cache_record() (+31 more)

### Community 5 - "io_paths.py"
Cohesion: 0.10
Nodes (39): ensure_dir(), resolve_contacts_dir(), resolve_many_to_many_dir(), resolve_output_root(), resolve_preview_cache_dir(), run_stamp(), _cand_file_name(), _copy_if_present() (+31 more)

### Community 6 - "graphify"
Cohesion: 0.05
Nodes (35): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files, Part C - Merge AST + semantic into final extraction (+27 more)

### Community 7 - "geometry_2d.py"
Cohesion: 0.09
Nodes (25): bbox_aspect_ratio(), build_fine_metrics(), linework_density(), bin_index(), geom_fingerprint_knn(), k_nearest_neighbors(), normalize_l1(), robust_scale() (+17 more)

### Community 8 - "analyze_symbol_raster_cache.py"
Cohesion: 0.17
Nodes (24): analyze_base_groups(), approx_symmetric_chamfer(), bbox_stats(), build_equivalence_labels(), build_recommendations(), compare_schema(), dedupe_quantized_points(), discover_files() (+16 more)

### Community 9 - "collect.py"
Cohesion: 0.12
Nodes (14): category_name(), category_type_label(), classify_view_kind(), coerce_view(), current_doc(), element_type_name_from_params(), first_item(), get_model_elements_contributing_to_view() (+6 more)

### Community 10 - "test_search_index_and_cache_loading.py"
Cohesion: 0.13
Nodes (11): _bundle(), test_find_similar_views_looks_up_scoped_candidate_preview(), test_find_similar_views_resolves_candidate_previews_after_top_n_trim(), test_index_jsonl_truncated_at_start_of_run(), test_index_views_counts_preview_failures(), test_index_views_counts_preview_failures_when_generate_returns_none(), test_index_views_second_run_hits_disk_from_doc_scoped_cache(), test_index_views_writes_doc_scoped_cache_files() (+3 more)

### Community 11 - "test_symbol_raster_cache_regressions.py"
Cohesion: 0.19
Nodes (20): _clear_symbol_raster_memory_cache(), _load_symbol_raster(), test_apply_canonical_instance_transform_handles_rotation_mirror_and_translation(), test_cache_miss_skips_retained_png_when_debug_artifacts_disabled(), test_cache_miss_uses_canonical_bounds_not_instance_obb_with_retained_artifacts(), test_collect_canonical_points_line_based_uses_canonical_bounds_for_export_pixels(), test_collect_canonical_points_records_export_pixel_metadata(), test_collect_canonical_points_uses_memory_after_disk_hit() (+12 more)

### Community 12 - "feature_cache.py"
Cohesion: 0.17
Nodes (6): Disk-backed JSON cache for ViewFeatures (roadmap track).  NOTE: The active v0.3, In-process + disk-backed cache for extracted ViewFeatures dicts.      Parameters, Return cached features dict or None., Store features dict and flush to disk., Remove all entries for a given view_id (any element_count)., Wipe the entire cache (memory + disk).

### Community 13 - "preview_export.py"
Cohesion: 0.22
Nodes (16): _find_exported_preview_file(), generate_and_cache_view_preview(), get_cached_view_preview(), _has_required_resolution(), _png_size(), _preview_file_path(), _preview_filename(), Return cached full-resolution preview PNG path for a view. (+8 more)

### Community 14 - "dynamo_thin_runner.py"
Cohesion: 0.18
Nodes (15): _candidate_entrypoints(), _candidate_roots(), _expand_repo_root(), _load_script_text(), _normalize_inputs(), _pop_import_paths(), _project_import_paths(), _push_import_paths() (+7 more)

### Community 15 - "test_feature_cache.py"
Cohesion: 0.31
Nodes (15): _make_cache(), Tests for src/dse/cache/feature_cache.py, _sample_features(), test_clear_wipes_all_entries(), test_corrupt_cache_file_starts_fresh(), test_disk_file_is_valid_json(), test_get_miss_returns_none(), test_invalidate_nonexistent_view_is_noop() (+7 more)

### Community 16 - "audit_unresolved_comments.py"
Cohesion: 0.24
Nodes (13): annotate_staleness(), _fetch_all_threads(), fetch_merged_prs(), _first_nonempty_line(), _graphql(), is_file_stale(), main(), Execute a GitHub GraphQL query; raise on HTTP or API errors. (+5 more)

### Community 17 - "Revit Detail Intelligence Project"
Cohesion: 0.18
Nodes (12): Architecture Principles (Deterministic, Explainable, Scale-tolerant, Model-first), Revit Detail Intelligence Project, sample_view_fingerprints() diagnostic mode, ViewFeatures (feature container), Architecture Diagram (Mermaid flowchart), Drafting View Indexing, Feature Storage (token multiset + geometry fingerprint), Detail Indexing Document (+4 more)

### Community 18 - "Architecture Diagram: Similarity Pipeline (Mermaid)"
Cohesion: 0.17
Nodes (12): Architecture Diagram: Similarity Pipeline (Mermaid), Symbol Cache (in similarity pipeline diagram), Visual Re-ranking (Stage-2 raster re-rank), feature_cache.py (roadmap, not on runtime path), Feature Cache Review (April 2026), symbol_cache.py (in-memory, no disk persistence), view_feature_cache.py (production runtime path), Two-layer Cache (in-memory + disk per view) (+4 more)

### Community 19 - "Symbol Cache + View Raster Pipeline Pseudocode v0.2.1"
Cohesion: 0.22
Nodes (11): build_symbol_descriptor_family_doc (Mode A), build_symbol_descriptor_isolated_render (Mode B), build_symbol_cache (orchestration + coverage), DescriptorVariant (uniform/anisotropic normalization), normalize_image_variant (image preprocessing), Stage1Result (data model), SymbolCache (data model), SymbolDescriptor (data model) (+3 more)

### Community 20 - "test_symbol_raster_diagnostics.py"
Cohesion: 0.35
Nodes (10): _clear_symbol_raster_memory_cache(), _load_symbol_raster(), test_cache_entry_validation_rejects_invalid_points_payload(), test_cache_entry_validation_requires_schema_and_pipeline_version(), test_collect_points_emits_cache_lookup_summary(), test_collect_points_emits_miss_summary_on_rebuild_export_failure(), test_collect_raster_points_accepts_diagnostic_callback(), test_collect_raster_points_applies_per_instance_transforms_after_group_lookup() (+2 more)

### Community 21 - "8-Step Pipeline Architecture"
Cohesion: 0.22
Nodes (9): 8-Step Pipeline Architecture, Step 1: Section Candidate Generation, Step 2: Geometry Extraction, Step 3: Endpoint Clustering, Step 4: Provenance Extraction, Step 8: Confidence Ranking, Index Aggregate Timing Fields (stage_timing_summary), Stage Timing Diagnostics Document (+1 more)

### Community 22 - "FIND_SIMILAR_VIEWS (pseudocode)"
Cohesion: 0.42
Nodes (9): EXPLAIN_MATCH (pseudocode), EXTRACT_FEATURES (pseudocode), FIND_SIMILAR_VIEWS (pseudocode), FINE_SIMILARITY Gaussian (pseudocode), GEOM_FINGERPRINT_KNN (pseudocode), GEOM_SIMILARITY cosine (pseudocode), ROBUST_SCALE (pseudocode), TOKEN_SIMILARITY weighted Jaccard (pseudocode) (+1 more)

### Community 23 - "graphify reference: extra exports and benchmark"
Cohesion: 0.25
Nodes (7): Step 6b - Wiki (only if --wiki flag), Step 7d - MCP server (only if --mcp flag), graphify reference: extra exports and benchmark, Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 24 - "Similarity Matching Document"
Cohesion: 0.25
Nodes (8): Ground Truth Dataset for Validation, Confidence Threshold Calibration, Calibration and Validation Document, Step 7: Similarity Matching, Confidence Tiers (HIGH/MED/LOW), Match Explainability (shared tokens, geometry diffs), Similarity Matching Document, Token Similarity (weighted Jaccard)

### Community 25 - "Runtime Storage and v0.3.2 Operational Notes"
Cohesion: 0.25
Nodes (8): Contact Folder Output (per-seed ranked PNGs), Many-to-many Mode (find_similar_views_many_to_many), Runtime Storage and v0.3.2 Operational Notes, Global Runs Index CSV (edge list for clustering), Symbol Raster Debug Artifact Retention (CONFIG flag), DSE modular package (src/dse/), Dynamo Thin Runner (src/dynamo_thin_runner.py), README: Revit Detail Intelligence

### Community 26 - "to_dynamo_score_list"
Cohesion: 0.32
Nodes (5): Return Dynamo-friendly score rows in a stable field order.      Row order:, to_dynamo_score_list(), Dynamo (CPython3) script for Revit 2025. Feature-based similarity matching for d, test_to_dynamo_score_list_can_omit_header(), test_to_dynamo_score_list_field_order()

### Community 27 - "graphify"
Cohesion: 0.29
Nodes (7): graphify, graphify explain, graphify path, graphify query, graphify update, Key Entry Points, Project Overview

### Community 28 - "find_similar_views() main algorithm"
Cohesion: 0.33
Nodes (6): CONFIG dict (tunable parameters), find_similar_views() main algorithm, Composite Scoring Formula, Combined Similarity Score (weighted composite), golden_compare.py (score parity harness), Harness Verification Note (golden compare)

### Community 29 - "golden_compare.py"
Cohesion: 0.53
Nodes (5): _compare_results(), _float_close(), Golden output harness for Dynamo/Revit environment.  Usage inside Dynamo CPython, run_golden_compare(), _run_script()

### Community 30 - "Geometry Fingerprint Document"
Cohesion: 0.50
Nodes (5): Histogram Construction (edge length + angle), Neighborhood Graph (k-NN), Geometry Fingerprint Document, Scale Normalization (characteristic length), Step 5: Geometry Fingerprint

### Community 31 - "graphify reference: add a URL and watch a folder"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 32 - "graphify reference: query, path, explain"
Cohesion: 0.50
Nodes (3): For /graphify explain, graphify reference: query, path, explain, For /graphify path

### Community 33 - "graphify reference: incremental update and cluster-only"
Cohesion: 0.50
Nodes (3): For --cluster-only, For --update (incremental re-extraction), graphify reference: incremental update and cluster-only

### Community 34 - "graphify reference: commit hook and native CLAUDE.md integration"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

## Knowledge Gaps
- **90 isolated node(s):** `Usage`, `Part A - Structural extraction for code files`, `Part C - Merge AST + semantic into final extraction`, `Step 9 - Save manifest, update cost tracker, clean up, and report`, `Interpreter guard for subcommands` (+85 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_safe_type_sig_parts()` connect `symbol_raster.py` to `dynamo_view_similarity_legacy.py`?**
  _High betweenness centrality (0.122) - this node is a cross-community bridge._
- **Why does `type_signature()` connect `dynamo_view_similarity_legacy.py` to `symbol_raster.py`?**
  _High betweenness centrality (0.121) - this node is a cross-community bridge._
- **Why does `ViewFeatures` connect `dynamo_view_similarity_legacy.py` to `symbol_cache.py`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `str` (e.g. with `ViewFeatureBundle` and `ViewPresentationSummary`) actually correct?**
  _`str` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `IndexDiagnosticAccumulator` (e.g. with `test_finalize_cache_temperature_summary()` and `test_flush_view_record_appends_across_calls()`) actually correct?**
  _`IndexDiagnosticAccumulator` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Usage`, `Part A - Structural extraction for code files`, `Part C - Merge AST + semantic into final extraction` to the rest of the system?**
  _125 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `dynamo_view_similarity_legacy.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06963645673323093 - nodes in this community are weakly interconnected._