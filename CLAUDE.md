# CLAUDE.md — Revit Detail Intelligence

This file describes the codebase structure, development workflows, and conventions for AI assistants working in this repository.

---

## Project Purpose

This repository implements a **deterministic, explainable similarity matching system** for Revit construction details. It runs inside Dynamo (CPython3, Revit 2025) and compares section/drafting views based on extracted geometry fingerprints and semantic tokens — no image recognition, no ML models.

The system is intended as decision support: it surfaces candidate reuse opportunities, it does not automate detail placement or replace design judgment.

---

## Repository Layout

```
revit_detail_intelligence/
├── src/
│   ├── dynamo_view_similarity.py   # Main implementation (Dynamo script, ~952 lines)
│   └── pseudo-code.txt             # Algorithmic spec in pseudo-code
├── tests/
│   └── test_placeholder.py         # Placeholder; real tests TBD
├── docs/
│   ├── system-overview.md
│   ├── pipeline-architecture.md
│   ├── geometry-fingerprint.md
│   ├── similarity-matching.md
│   ├── detail-indexing.md
│   ├── calibration-and-validation.md
│   ├── architecture-diagram.md
│   └── architecture-diagram-similarity.md
├── .github/
│   ├── workflows/ci.yml            # GitHub Actions: lint + test on Python 3.11 & 3.12
│   └── pull_request_template.md
├── .pre-commit-config.yaml         # Ruff auto-fix + format
├── pyproject.toml                  # Ruff + pytest config
├── requirements-dev.txt            # pytest, ruff, pre-commit
├── CONTRIBUTING.md
└── README.md
```

---

## Primary Source File

**`src/dynamo_view_similarity.py`** is the only implementation file. It is a self-contained Dynamo CPython script. Key sections:

| Section | Lines | Description |
|---------|-------|-------------|
| Config / policy | 50–70 | `CONFIG` dict with tunable parameters |
| `ViewFeatures` class | 73–80 | Feature container (view_id, tokens, geom_fingerprint, fine_metrics) |
| Coercion helpers | 83–255 | Input normalization — Views, ElementIds, wrapped Dynamo objects |
| Token generation | 256–463 | Semantic tokens from model/annotation elements, type signatures, IDF weighting |
| Geometry functions | 464–599 | Curve extraction, endpoint clustering, point normalization, k-NN fingerprinting |
| Similarity metrics | 601–694 | Cosine similarity, weighted Jaccard token similarity, fine metrics |
| `find_similar_views()` | 840–880 | Main algorithm: extract → score → rank → top-N |
| `sample_view_fingerprints()` | 890–931 | Diagnostic mode: sample views and report full fingerprints |
| Dynamo entrypoint | 934–952 | `IN[0..4]` / `OUT` wiring |

### Dynamo IN/OUT interface

```
IN[0]  query view     — DB.View, wrapped Dynamo View, ElementId, int, or single-item list
IN[1]  corpus views   — list of same supported formats
IN[2]  topN           — optional int, default 5
IN[3]  sampleN        — optional int; triggers sampling mode when provided
IN[4]  sampleSeed     — optional int, default 0 (used only in sampling mode)

OUT    similarity mode  — list[dict] sorted descending by score_total
       sampling mode    — list[dict] with full fingerprint reports per view
```

### Scoring formula

```
score_total = w_tokens * score_tokens + w_geom * score_geom + w_fine * score_fine
```

Default weights: `w_tokens=0.55`, `w_geom=0.35`, `w_fine=0.10`.
When a view has fewer than `min_token_threshold` tokens, low-semantic weights apply: `w_tokens=0.20`, `w_geom=0.70`.

Confidence tiers: `HIGH >= 0.85`, `MED >= 0.65`, `LOW < 0.65`.

### Imports and Revit API

The script uses `clr` (C# interop) and imports directly from `Autodesk.Revit.DB`. These imports are only available inside Dynamo/Revit; they are not installable via pip. Ruff per-file ignores for `dynamo_view_similarity.py` suppress:

- `E402` — module-level imports not at top (Dynamo requires `clr.AddReference` first)
- `E501` — line length (pragmatic for Revit API call chains)
- `F821` — undefined names (`IN`, `OUT` are injected by Dynamo at runtime)
- `B905` — bugbear zip-without-strict

Do not attempt to `import` or `from`-import Revit API symbols in other files unless running inside Dynamo.

---

## Development Workflow

### Required checks before committing

```bash
ruff check .    # lint (rules: E, F, B)
pytest          # run tests
```

Pre-commit hooks run both automatically on `git commit` (via `.pre-commit-config.yaml`).

### Branch and PR workflow

1. Create a branch — never commit directly to `main`.
2. Keep commits focused; avoid mixing unrelated concerns.
3. Open a PR; CI must be green before merging.
4. CI runs on Python 3.11 and 3.12.

### Commit message format

```
<type>: <short description>
```

Valid types: `ci`, `chore`, `docs`, `test`, `fix`, `feat`.
Avoid: `wip`, `stuff`, `misc`, vague filler.

---

## Code Conventions

- **Line length:** 100 characters (`pyproject.toml`).
- **Formatter:** `ruff format` (applied automatically by pre-commit).
- **Linter:** `ruff check` — rules E, F, B.
- **Target:** Python 3.11+; no type annotations (Dynamo compatibility).
- **Naming:** `snake_case` for functions and variables, `UPPER_SNAKE_CASE` for module-level constants.
- **No bare `except`:** Exceptions must be logged with context and re-raised, or follow an explicit documented policy (fail / skip / degrade). Silent failure is a bug.
- **No PyPI dependencies** in `src/`: the script runs in Dynamo's sandboxed CPython environment. Keep stdlib-only (`math`, `random`, `collections`).

---

## Testing

Tests live in `tests/`. Currently only a placeholder exists; real tests are expected as the implementation matures.

- Framework: `pytest` (run with `pytest` or `pytest -q`).
- Tests should cover failure modes, not just happy paths.
- CI is the source of truth — local test success does not override CI failure.

New behavior or policy changes must include tests.

---

## Architecture Principles

These must be preserved in all changes:

- **Deterministic** — given the same model state, outputs are identical.
- **Explainable** — every match is backed by interpretable token and geometry features, never an opaque score.
- **Scale-tolerant** — geometry fingerprints are normalized; dimensional variation does not break matching.
- **Model-first** — prefer signals from model elements over view graphics.

---

## Non-Goals

Do not implement:

- Image recognition on drawings.
- Automatic detail placement.
- ML/neural embedding models.
- Anything that replaces design judgment.

---

## Key Tunable Parameters (`CONFIG` dict)

| Key | Default | Purpose |
|-----|---------|---------|
| `kNN_k` | 3 | Neighbours used in geometry k-NN fingerprinting |
| `len_bins` | 9 edges | Normalized edge-length histogram buckets |
| `ang_bins_deg` | 12 edges | Angle histogram buckets (degrees) |
| `tol_coord` | 1/256 ft | Coordinate tolerance for endpoint clustering |
| `weights` | tokens=0.55, geom=0.35, fine=0.10 | Default composite score weights |
| `low_semantic_weights` | tokens=0.20, geom=0.70, fine=0.10 | Weights when token count < threshold |
| `min_token_threshold` | 4 | Minimum tokens before falling back to geometry-heavy weights |
| `confidence_thresholds` | HIGH≥0.85, MED≥0.65 | Tier cutoffs |
| `token_weights_by_kind` | varies | Per-kind IDF weight multipliers |

---

## Docs Reference

| File | Contents |
|------|----------|
| `docs/system-overview.md` | Objectives, key principles, intended users |
| `docs/pipeline-architecture.md` | 8-step pipeline description |
| `docs/geometry-fingerprint.md` | Geometry normalization and k-NN fingerprint construction |
| `docs/similarity-matching.md` | Token similarity, cosine similarity, composite scoring |
| `docs/detail-indexing.md` | How model-based and drafting views are indexed |
| `docs/calibration-and-validation.md` | Validation strategy and accuracy metrics |
| `docs/architecture-diagram.md` | Mermaid flowchart of the full similarity process |
| `docs/architecture-diagram-similarity.md` | Detailed implementation diagram for drafting views |

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
