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

from dse.pipelines.search import find_similar_views, sample_view_fingerprints
from dse.revit_api.collect import coerce_view, coerce_views, current_doc


doc = current_doc()
query_input = IN[0] if len(IN) > 0 else None
corpus_input = IN[1] if len(IN) > 1 else []
top_n = IN[2] if len(IN) > 2 and IN[2] is not None else 5
sample_n = IN[3] if len(IN) > 3 else None
sample_seed = IN[4] if len(IN) > 4 and IN[4] is not None else 0

query_view = coerce_view(query_input, fallback_doc=doc)
corpus_views = coerce_views(corpus_input, fallback_doc=doc)

if sample_n is not None:
    OUT = sample_view_fingerprints(corpus_views, sample_n, seed=sample_seed)
elif query_view is None:
    OUT = {
        "error": "IN[0] must resolve to a Revit DB.View (View, wrapped View, ElementId, int, or single-item list)."
    }
else:
    OUT = find_similar_views(query_view, corpus_views, top_n)
