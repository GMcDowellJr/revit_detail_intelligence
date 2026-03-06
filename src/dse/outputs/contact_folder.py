import csv
import json
import os
import re
import shutil

from dse.io_paths import ensure_dir, resolve_contacts_dir, run_stamp


def _slug(txt):
    value = str(txt or "unknown").strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value.strip("_") or "unknown"


def _copy_if_present(src, dst):
    if not src or not os.path.exists(src):
        return False
    ensure_dir(os.path.dirname(dst))
    shutil.copy2(src, dst)
    return True


def _seed_file_name(seed):
    return "seed__{}__id_{}.png".format(_slug(seed.get("display_name")), int(seed.get("view_id", 0)))


def _cand_file_name(row):
    return "rank_{:02d}__score_{:.3f}__conf_{}__{}__id_{}.png".format(
        int(row.get("rank", 0)),
        float(row.get("total_score", 0.0)),
        _slug(str(row.get("confidence_level", "low")).lower()),
        _slug(row.get("candidate_display_name")),
        int(row.get("candidate_view_id", 0)),
    )


def create_contact_folder(seed, candidate_rows, config, run_id=None):
    contacts_root = ensure_dir(resolve_contacts_dir(config))
    rid = run_id or run_stamp("run")
    folder_name = "seed_{}".format(int(seed.get("view_id", 0)))
    folder_path = ensure_dir(os.path.join(contacts_root, folder_name))

    seed_file = _seed_file_name(seed)
    seed_out = os.path.join(folder_path, seed_file)
    _copy_if_present(seed.get("preview_path"), seed_out)

    rows_out = []
    ordered = sorted(candidate_rows, key=lambda r: (int(r.get("rank", 0)), -float(r.get("total_score", 0.0))))
    for row in ordered:
        file_name = _cand_file_name(row)
        png_out = os.path.join(folder_path, file_name)
        _copy_if_present(row.get("preview_path"), png_out)
        new_row = dict(row)
        new_row["contact_png"] = file_name
        rows_out.append(new_row)

    results_path = os.path.join(folder_path, "results.json")
    with open(results_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "run_id": rid,
                "seed_view_id": seed.get("view_id"),
                "seed_display_name": seed.get("display_name"),
                "seed_png": seed_file,
                "results": rows_out,
            },
            handle,
            indent=2,
            sort_keys=True,
        )

    runs_index = os.path.join(contacts_root, "runs_index.csv")
    exists = os.path.exists(runs_index)
    with open(runs_index, "a", encoding="utf-8", newline="") as handle:
        fields = [
            "run_id",
            "seed_view_id",
            "candidate_view_id",
            "rank",
            "total_score",
            "confidence_level",
            "seed_display_name",
            "candidate_display_name",
            "contact_folder",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        if not exists:
            writer.writeheader()
        for row in rows_out:
            writer.writerow(
                {
                    "run_id": rid,
                    "seed_view_id": int(seed.get("view_id", 0)),
                    "candidate_view_id": int(row.get("candidate_view_id", 0)),
                    "rank": int(row.get("rank", 0)),
                    "total_score": "{:.6f}".format(float(row.get("total_score", 0.0))),
                    "confidence_level": str(row.get("confidence_level", "low")).lower(),
                    "seed_display_name": seed.get("display_name", ""),
                    "candidate_display_name": row.get("candidate_display_name", ""),
                    "contact_folder": folder_name,
                }
            )

    return {
        "run_id": rid,
        "contact_folder": folder_path,
        "results_path": results_path,
        "runs_index": runs_index,
        "row_count": len(rows_out),
    }
