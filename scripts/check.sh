#!/usr/bin/env bash
# The single pre-push check. CI runs exactly this script.
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
