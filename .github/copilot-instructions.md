# GitHub Copilot Instructions — Revit Detail Intelligence

## Graph-first codebase navigation

This project has a pre-built knowledge graph at `graphify-out/graph.json` (683 nodes,
1 389 edges, 44 labelled communities). When `graphify-out/graph.json` exists, **query
the graph before browsing source files** to answer questions about architecture,
relationships, or unfamiliar symbols.

```bash
# Broad question about the codebase
graphify query "<question>"

# Trace a relationship between two concepts
graphify path "<ConceptA>" "<ConceptB>"

# Plain-language explanation of a node or concept
graphify explain "<concept>"
```

Use `graphify-out/GRAPH_REPORT.md` only for broad architecture review when the above
commands don't surface enough context. Read raw source files to modify or debug
specific code, not to answer architecture questions.

After modifying code, run `graphify update .` to keep the graph current (AST-only,
no API cost).

---

## Project overview

Deterministic, explainable similarity-matching system for Revit construction details.
Runs inside Dynamo (CPython 3, Revit 2025). No image recognition, no ML models.

Key entry points:
- `src/dse/pipelines/search.py` — `find_similar_views()`, the main algorithm
- `src/dse/cache/` — view-feature, symbol, and feature cache layers
- `src/revit_api/symbol_raster.py` — symbol raster pipeline

See `graphify-out/GRAPH_REPORT.md` for god nodes and community structure.
