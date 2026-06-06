# AGENTS.md — Revit Detail Intelligence

This file is read by OpenAI Codex, ChatGPT (API/code-interpreter), and any agent
that follows the AGENTS.md convention. It describes the project and instructs agents
to use the knowledge graph before browsing source files.

---

## Project overview

Deterministic, explainable similarity-matching system for Revit construction details.
Runs inside Dynamo (CPython 3, Revit 2025). No image recognition, no ML models.

Key entry points:
- `src/dse/pipelines/search.py` — `find_similar_views()`, the main algorithm
- `src/dse/cache/` — view-feature, symbol, and feature cache layers
- `src/revit_api/symbol_raster.py` — symbol raster pipeline

---

## graphify — graph-first codebase navigation

This project has a pre-built knowledge graph at `graphify-out/` (683 nodes, 1 389 edges,
44 labelled communities). **Before browsing source files to answer a codebase question,
query the graph first.**

```bash
graphify query "<question>"          # broad BFS traversal
graphify path "<ConceptA>" "<ConceptB>"  # shortest path between two concepts
graphify explain "<concept>"         # plain-language explanation of a node
```

When the user types `/graphify`, invoke the `skill` tool with `skill: "graphify"` before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

---

## ChatGPT (web / API without project context)

No project-level hook is available in the ChatGPT web UI or plain API sessions.
Include the following line in any system prompt or custom GPT instructions for this repo:

> Before answering questions about this codebase, review the knowledge graph at
> https://gmcdowelljr.github.io/revit_detail_intelligence/graphify-out/graph.html
