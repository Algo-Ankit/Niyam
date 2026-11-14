#!/usr/bin/env bash
# Creates the project toolchain entirely inside the repo: no global installs,
# no PATH or profile edits, no Windows registry entries.
#   .tools/bootstrap  venv holding the uv binary
#   .tools/python     uv-managed CPython 3.12
#   .tools/uv-cache   uv package cache (set in pyproject.toml)
#   .venv             project environment
# Usage: bash scripts/bootstrap.sh   (needs any Python >= 3.8 on PATH to start)
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ "${OS:-}" == "Windows_NT" ]]; then bin="Scripts"; exe=".exe"; else bin="bin"; exe=""; fi
uv=".tools/bootstrap/$bin/uv$exe"

if [[ ! -x "$uv" ]]; then
  python -m venv .tools/bootstrap
  PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ".tools/bootstrap/$bin/python$exe" -m pip install --quiet "uv>=0.13,<0.14"
fi

export UV_PYTHON_INSTALL_DIR="$PWD/.tools/python"
"$uv" python install 3.12 --no-bin --no-registry
"$uv" venv --allow-existing --python 3.12 --managed-python
"$uv" sync
git config --local core.hooksPath .githooks

echo "Ready. Run commands with: $uv run <command>"
