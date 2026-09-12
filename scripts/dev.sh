#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
RUNTIME_BIN="${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies"
if [ -x "$RUNTIME_BIN/node/bin/node" ]; then
  export PATH="$RUNTIME_BIN/node/bin:$RUNTIME_BIN/bin/fallback:$PATH"
fi
if [ ! -x .venv/bin/python ] || [ ! -d frontend/node_modules ]; then
  echo 'Install the Python and frontend dependencies first; see README.md.' >&2
  exit 1
fi
.venv/bin/python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT INT TERM
cd frontend
node node_modules/vite/bin/vite.js --host 127.0.0.1
