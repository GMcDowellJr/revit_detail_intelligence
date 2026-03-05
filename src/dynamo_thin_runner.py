"""
Dynamo thin runner.

Loads and executes the main similarity entrypoint from a Documents checkout:
  C:\\Users\\%USERPROFILE%\\Documents\\revit_detail_intelligence

The runner forwards IN[x] to the loaded script and returns its OUT unchanged.
"""

import os


REPO_ROOT_RAW = r"C:\Users\%USERPROFILE%\Documents\revit_detail_intelligence"


def _expand_repo_root(path_raw):
    expanded = os.path.expandvars(path_raw)
    expanded = os.path.expanduser(expanded)
    return os.path.normpath(expanded)


def _candidate_entrypoints(repo_root):
    return [
        os.path.join(repo_root, "src", "dynamo_view_similarity.py"),
        os.path.join(repo_root, "dynamo_view_similarity.py"),
    ]


def _load_script_text(path):
    with open(path, "r") as f:
        return f.read()


def _run_loaded_script(path, in_values):
    scope = {"IN": in_values, "OUT": None}
    code = _load_script_text(path)
    exec(compile(code, path, "exec"), scope, scope)
    return scope.get("OUT")


def _resolve_entrypoint(repo_root):
    for candidate in _candidate_entrypoints(repo_root):
        if os.path.exists(candidate):
            return candidate
    return None


_repo_root = _expand_repo_root(REPO_ROOT_RAW)
_entrypoint = _resolve_entrypoint(_repo_root)

if _entrypoint is None:
    OUT = {
        "error": "Could not find dynamo_view_similarity.py under {}".format(_repo_root),
        "checked": _candidate_entrypoints(_repo_root),
    }
else:
    in_values = globals().get("IN", [])
    OUT = _run_loaded_script(_entrypoint, in_values)
