## Golden verification summary

- Compared legacy script output (`tests/harness/dynamo_view_similarity_legacy.py`) against refactored entrypoint (`src/dynamo_view_similarity.py`) using `tests/harness/golden_compare.py`.
- Harness checks:
  - top-N candidate ordering (`candidate_view_id` sequence)
  - score parity for `score_tokens`, `score_geom`, `score_fine`, `score_total` (epsilon = 1e-9)
  - output structure compatibility (list/dict layout used by current text/JSON-like output)
- Observed deltas in this repository environment: **not executed**, because Revit/Dynamo runtime is required for view/element APIs.
- Expected functional delta: only `FamilyInstance` type-name resolution where valid symbol/type names exist (e.g., replacing `<none>`/`<unknown-type>` with actual type names such as `W12X40`).
