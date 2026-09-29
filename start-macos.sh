#!/usr/bin/env bash
# Starts Välituki for development: FastAPI backend + Vite dev server (the dev server proxies /api to the backend).
# Ports are overridable: BACKEND_PORT=8030 FRONTEND_PORT=5196 ./start-macos.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8020}"
FRONTEND_PORT="${FRONTEND_PORT:-5195}"

PYTHON="$ROOT/backend/.venv/bin/python"
NODE_BIN="${NODE_BIN:-$HOME/.local/node20/bin}"

[ -x "$PYTHON" ] || { echo "Missing venv: $PYTHON (see README: Käynnistys)" >&2; exit 1; }
if [ -x "$NODE_BIN/node" ]; then export PATH="$NODE_BIN:$PATH"; fi
command -v npm >/dev/null || { echo "npm not found (Node.js 20+ required)" >&2; exit 1; }

export ALLOWED_ORIGINS="http://localhost:$FRONTEND_PORT,http://127.0.0.1:$FRONTEND_PORT"
export VITE_PROXY_TARGET="http://127.0.0.1:$BACKEND_PORT"

echo "Starting backend on http://127.0.0.1:$BACKEND_PORT"
"$PYTHON" -m uvicorn app.main:app --app-dir "$ROOT/backend" --host 127.0.0.1 --port "$BACKEND_PORT" &
BACKEND_PID=$!

echo "Starting frontend on http://127.0.0.1:$FRONTEND_PORT"
npm --prefix "$ROOT/frontend" run dev -- --port "$FRONTEND_PORT" --strictPort --host 127.0.0.1 &
FRONTEND_PID=$!

trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null' EXIT INT TERM

echo ""
echo "Välituki:       http://127.0.0.1:$FRONTEND_PORT"
echo "Backend health: http://127.0.0.1:$BACKEND_PORT/api/health"
wait
