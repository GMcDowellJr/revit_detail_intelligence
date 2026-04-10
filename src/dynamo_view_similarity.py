"""
Dynamo (CPython3) script for Revit 2025.
Feature-based similarity matching for detail / drafting views.
"""

import sys

# Module reloading for development (ensures latest code is used)
RELOAD_MODULES = True

if RELOAD_MODULES:
    modules_to_remove = [
        key for key in list(sys.modules.keys()) if key == "dse" or key.startswith("dse.")
    ]
    for mod in modules_to_remove:
        del sys.modules[mod]

from dse.pipelines.search import (
    find_similar_views,
    find_similar_views_many_to_many,
    index_views,
    sample_view_fingerprints,
)
from dse.output_format import to_dynamo_score_list
from dse.revit_api.collect import coerce_view, coerce_views, current_doc


doc = current_doc()
primary_input = IN[0] if len(IN) > 0 else None
mode_input = IN[1] if len(IN) > 1 else None
top_n = IN[2] if len(IN) > 2 and IN[2] is not None else 5
sample_n = None
if len(IN) > 3 and IN[3] is not None and not isinstance(IN[3], bool):
    sample_n = IN[3]
sample_seed = IN[4] if len(IN) > 4 and IN[4] is not None else 0
run_many_to_many = bool(IN[3]) if len(IN) > 3 and isinstance(IN[3], bool) else False

legacy_corpus_input = mode_input if not isinstance(mode_input, str) else []
query_view = coerce_view(primary_input, fallback_doc=doc)
corpus_views = coerce_views(legacy_corpus_input, fallback_doc=doc)

mode = "search"
if isinstance(mode_input, str):
    candidate = mode_input.strip().lower()
    if candidate in ("search", "index"):
        mode = candidate

if sample_n is not None:
    OUT = sample_view_fingerprints(corpus_views, sample_n, seed=sample_seed)
elif mode == "index":
    views_to_index = coerce_views(primary_input, fallback_doc=doc)
    summary = index_views(views_to_index)
    if run_many_to_many:
        summary["many_to_many"] = find_similar_views_many_to_many()
    OUT = summary
elif query_view is None:
    OUT = {
        "error": "IN[0] must resolve to a Revit DB.View (View, wrapped View, ElementId, int, or single-item list)."
    }
else:
    results = find_similar_views(query_view, top_n)
    OUT = to_dynamo_score_list(results, include_header=True)
