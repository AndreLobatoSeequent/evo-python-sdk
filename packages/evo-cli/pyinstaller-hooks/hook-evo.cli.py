# evo.cli's subcommands (auth, admin, blockmodels, ...) are imported lazily by
# dotted string path in evo.cli._lazy.LazySubcommand._load(), so PyInstaller's
# static analysis never sees those imports and silently drops the modules from
# the frozen build - which surfaces at runtime as e.g.
# `ModuleNotFoundError: No module named 'evo.cli.auth'`. Force them all in.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = collect_submodules("evo.cli")
# SKILL.md is a non-Python data file read at runtime via Path(__file__).parent;
# static analysis misses it, so we collect it explicitly.
datas = collect_data_files("evo.cli.skills", includes=["**/*.md"])
