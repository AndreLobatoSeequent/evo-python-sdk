#!/usr/bin/env bash
# Builds the evo-cli wheel and validates it in a clean virtual environment.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

echo "Building evo-cli wheel..."
uv build --package evo-cli

wheel="$(ls -t dist/evo_cli-*.whl | head -n1)"
if [ -z "$wheel" ]; then
    echo "No evo-cli wheel found in dist/" >&2
    exit 1
fi

echo "Validating $(basename "$wheel") in a clean virtual environment..."
uv venv --clear .venv-wheel-test
uv pip install --python .venv-wheel-test/bin/python "$wheel"
.venv-wheel-test/bin/evo --help

echo "Wheel build and validation succeeded: $(basename "$wheel")"
