"""
Dynamo thin runner.

Loads and executes the main similarity entrypoint from a Documents checkout:
  %USERPROFILE%\Documents\revit_detail_intelligence

The runner forwards IN[x] to the loaded script and returns its OUT unchanged.
"""

import os
import sys

# Module reloading for development (ensures latest code is used)
RELOAD_MODULES = True


def _clear_project_modules():
    if not RELOAD_MODULES:
        return
    modules_to_remove = [
        key
        for key in list(sys.modules.keys())
        if key == "dse" or key.startswith("dse.") or key == "dynamo_view_similarity"
    ]
    for mod in modules_to_remove:
        del sys.modules[mod]


REPO_ROOT_RAW = r"%USERPROFILE%\Documents\revit_detail_intelligence"


def _expand_repo_root(path_raw):
    expanded = os.path.expandvars(path_raw)
    expanded = os.path.expanduser(expanded)
    return os.path.normpath(expanded)


def _candidate_roots():
    # Primary requested path.
    roots = [_expand_repo_root(REPO_ROOT_RAW)]

    # Fallback when env expansion differs by host.
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        roots.append(
            os.path.normpath(
                os.path.join(userprofile, "Documents", "revit_detail_intelligence")
            )
        )

    roots.append(
        os.path.normpath(os.path.expanduser("~/Documents/revit_detail_intelligence"))
    )

    deduped = []
    for root in roots:
        if root not in deduped:
            deduped.append(root)
    return deduped


def _candidate_entrypoints(repo_root):
    return [
        os.path.join(repo_root, "src", "dynamo_view_similarity.py"),
        os.path.join(repo_root, "dynamo_view_similarity.py"),
    ]




def _repo_root_from_entrypoint(path):
    entry_dir = os.path.dirname(path)
    if os.path.basename(entry_dir).lower() == "src":
        return os.path.dirname(entry_dir)
    return entry_dir


def _project_import_paths(path):
    repo_root = _repo_root_from_entrypoint(path)
    src_root = os.path.join(repo_root, "src")
    return [src_root, repo_root]


def _push_import_paths(paths):
    added = []
    for candidate in paths:
        if candidate and os.path.isdir(candidate) and candidate not in sys.path:
            sys.path.insert(0, candidate)
            added.append(candidate)
    return added


def _pop_import_paths(added):
    for candidate in added:
        try:
            sys.path.remove(candidate)
        except ValueError:
            pass

def _load_script_text(path):
    with open(path, "r") as f:
        return f.read()


def _run_loaded_script(path, in_values):
    scope = {"IN": in_values, "OUT": None, "__file__": path, "__name__": "__main__"}
    code = _load_script_text(path)

    added_paths = _push_import_paths(_project_import_paths(path))
    try:
        exec(compile(code, path, "exec"), scope, scope)
    finally:
        _pop_import_paths(added_paths)

    return scope.get("OUT")


def _resolve_entrypoint():
    checked = []
    for repo_root in _candidate_roots():
        for candidate in _candidate_entrypoints(repo_root):
            checked.append(candidate)
            if os.path.exists(candidate):
                return candidate, checked
    return None, checked


_entrypoint, _checked = _resolve_entrypoint()

if _entrypoint is None:
    OUT = {
        "error": "Could not find dynamo_view_similarity.py in expected Documents checkout paths.",
        "checked": _checked,
    }
else:
    _clear_project_modules()
    in_values = globals().get("IN", [])
    OUT = _run_loaded_script(_entrypoint, in_values)
