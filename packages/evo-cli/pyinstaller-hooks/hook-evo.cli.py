# evo.cli's subcommands (auth, admin, blockmodels, ...) are imported lazily by
# dotted string path in evo.cli._lazy.LazySubcommand._load(), so PyInstaller's
# static analysis never sees those imports and silently drops the modules from
# the frozen build - which surfaces at runtime as e.g.
# `ModuleNotFoundError: No module named 'evo.cli.auth'`. Force them all in.
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("evo.cli")
