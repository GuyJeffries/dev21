#!/bin/bash
# Installs Python 3.13 deps (bpy, Pillow, pytest, ruff) so tests and linters work in cloud sessions.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"
uv sync
