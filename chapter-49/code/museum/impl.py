"""Pick which implementation a museum test imports: IMPL=buggy | quickpatch | fixed (default fixed)."""
import importlib
import os


def load(package: str, module_names=("buggy", "quickpatch", "fixed")):
    name = os.environ.get("IMPL", "fixed")
    if name not in module_names:
        raise SystemExit(f"IMPL must be one of {module_names}, not {name!r}")
    return importlib.import_module(f"{package}.{name}")
