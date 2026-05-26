#!/usr/bin/env bash
# Stop the discuss-room server started by start-local.sh.
set -euo pipefail

cd "$(dirname "$0")/.."

PID_FILE=".run/server.pid"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  pid="$(cat "$PID_FILE")"
  echo "stopping server (pid $pid)..."
  kill "$pid"
  for _ in 1 2 3 4 5; do
    sleep 0.5
    kill -0 "$pid" 2>/dev/null || break
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "did not exit cleanly; sending SIGKILL"
    kill -9 "$pid" || true
  fi
  rm -f "$PID_FILE"
  echo "stopped."
else
  echo "no running server (no pid file or process)"
fi
