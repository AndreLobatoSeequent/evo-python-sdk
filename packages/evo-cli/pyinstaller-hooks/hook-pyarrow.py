# Overrides pyinstaller-hooks-contrib's hook-pyarrow.py, which
# unconditionally bundles every DLL/.lib and submodule pyarrow ships
# (collect_dynamic_libs('pyarrow') grabs the whole package directory).
# evo-cli only ever imports pyarrow's core, .compute, .csv, and .parquet
# APIs (see evo-blockmodels/evo-objects sources) - verified that importing
# all three does not transitively load the Flight RPC, Substrait, Acero, or
# Dataset components. Those alone account for ~20MB of native libraries
# (arrow_flight.dll, arrow_substrait.dll, arrow_dataset.dll, ...) plus
# several MB of build-time-only .lib import libraries that are never
# needed at runtime.
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

_EXCLUDED_SUBSTRINGS = ("flight", "substrait", "dataset", "acero")


def _is_excluded(path: str) -> bool:
    lowered = path.lower()
    return lowered.endswith(".lib") or any(s in lowered for s in _EXCLUDED_SUBSTRINGS)


hiddenimports = collect_submodules(
    "pyarrow",
    filter=lambda name: "tests" not in name and not any(s in name for s in _EXCLUDED_SUBSTRINGS),
)
# collect_data_files sweeps up every non-.py file in the package directory
# (including the same DLLs/.lib files handled below), so it needs the same
# exclusion filter - otherwise it silently re-adds everything binaries drops.
datas = [(src, dest) for src, dest in collect_data_files("pyarrow") if not _is_excluded(src)]
binaries = [(src, dest) for src, dest in collect_dynamic_libs("pyarrow") if not _is_excluded(src)]
