import os
from datetime import datetime

WINDOWS_BASE = r"C:\temp\revit_detail_intelligence"


def resolve_cache_root(config):
    return config.get("cache_root") or os.path.join(WINDOWS_BASE, "cache")


def resolve_output_root(config):
    return config.get("output_root") or os.path.join(WINDOWS_BASE, "output")


def resolve_contact_sheets_dir(config):
    return config.get("contact_sheets_dir") or os.path.join(resolve_output_root(config), "contact_sheets")


def resolve_many_to_many_dir(config):
    return config.get("many_to_many_output_dir") or os.path.join(resolve_output_root(config), "many_to_many")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def run_stamp(prefix="run"):
    return "{}-{}".format(prefix, datetime.utcnow().strftime("%Y%m%dT%H%M%SZ"))
