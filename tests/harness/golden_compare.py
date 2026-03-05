"""Golden output harness for Dynamo/Revit environment.

Usage inside Dynamo CPython/Revit Python host:
  from tests.harness.golden_compare import run_golden_compare
  report = run_golden_compare(IN[0], IN[1], top_n=5)
"""

from pathlib import Path

EPS = 1e-9


def _run_script(path, in_values):
    globals_dict = {"IN": in_values, "OUT": None}
    code = Path(path).read_text()
    exec(compile(code, str(path), "exec"), globals_dict, globals_dict)
    return globals_dict.get("OUT")


def _float_close(a, b, eps=EPS):
    return abs(float(a) - float(b)) <= eps


def _compare_results(old, new):
    deltas = []
    if not isinstance(old, list) or not isinstance(new, list):
        if old != new:
            deltas.append("Output type/value mismatch")
        return deltas

    old_ids = [r.get("candidate_view_id") for r in old]
    new_ids = [r.get("candidate_view_id") for r in new]
    if old_ids != new_ids:
        deltas.append("Top-N ordering differs")

    for idx, (o, n) in enumerate(zip(old, new)):
        for key in ("score_tokens", "score_geom", "score_fine", "score_total"):
            if not _float_close(o.get(key, 0.0), n.get(key, 0.0)):
                deltas.append("Row {} {} differs: {} vs {}".format(idx, key, o.get(key), n.get(key)))
    return deltas


def run_golden_compare(query_view, corpus_views, top_n=5, sample_n=None, sample_seed=0):
    in_values = [query_view, corpus_views, top_n, sample_n, sample_seed]
    old_out = _run_script("tests/harness/dynamo_view_similarity_legacy.py", in_values)
    new_out = _run_script("src/dynamo_view_similarity.py", in_values)

    deltas = _compare_results(old_out, new_out)
    return {
        "old_output": old_out,
        "new_output": new_out,
        "deltas": deltas,
        "matches": len(deltas) == 0,
        "compared": {
            "ordering": True,
            "scores": ["score_tokens", "score_geom", "score_fine", "score_total"],
            "structure": "list/dict text-compatible structure",
        },
        "note": "Only FamilyInstance type-name resolution is expected to differ where old output had <none>/<unknown-type>.",
    }
