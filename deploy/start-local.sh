#!/usr/bin/env bash
# Start the discuss-room server detached from the calling shell.
# Survives terminal/Claude-session exit. Idempotent: re-running restarts.
set -euo pipefail

cd "$(dirname "$0")/.."

PID_FILE=".run/server.pid"
LOG_FILE=".run/server.log"
PORT="${DISCUSS_PORT:-8000}"
HOST="${DISCUSS_HOST:-127.0.0.1}"
DB="${DATABASE_URL:-sqlite:///./dev.db}"

mkdir -p .run

# Stop any prior instance owned by this PID file.
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "stopping existing server (pid $(cat "$PID_FILE"))..."
  kill "$(cat "$PID_FILE")" || true
  sleep 1
fi

# Also stop anything sitting on the port (uvicorn started outside this script).
if lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
  echo "freeing port $PORT..."
  lsof -ti tcp:"$PORT" | xargs kill || true
  sleep 1
fi

# DISCUSS_DEV_RELOAD=1 enables uvicorn --reload (watches *.py edits and
# restarts the worker). Templates/CSS/JS are already served per-request, so
# they don't need it. Off by default — leaving it always on slows startup
# and pulls in the watcher's file-descriptor cost.
RELOAD_FLAG=""
if [[ "${DISCUSS_DEV_RELOAD:-0}" == "1" || "${DISCUSS_DEV_RELOAD:-}" == "true" ]]; then
  RELOAD_FLAG="--reload --reload-dir server"
  echo "(hot reload enabled — watching server/)"
fi

echo "starting uvicorn on $HOST:$PORT (db=$DB)..."
DATABASE_URL="$DB" nohup uvicorn server.main:app \
  --host "$HOST" --port "$PORT" \
  $RELOAD_FLAG \
  >"$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
disown || true

sleep 1
if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "server up. pid=$(cat "$PID_FILE")  log=$LOG_FILE  url=http://$HOST:$PORT"
else
  echo "server failed to start. last log:"
  tail -20 "$LOG_FILE" >&2
  exit 1
fi
