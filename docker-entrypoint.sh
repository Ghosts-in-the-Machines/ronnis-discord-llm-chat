#!/bin/sh
set -eu

mkdir -p "${DATA_ROOT:-/app/data}"

cleanup() {
  if [ -n "${HANDLER_PID:-}" ]; then
    kill "$HANDLER_PID" 2>/dev/null || true
  fi
  if [ -n "${WORKER_PID:-}" ]; then
    kill "$WORKER_PID" 2>/dev/null || true
  fi
}

trap cleanup INT TERM EXIT

echo "[SYSTEM] Starting Discord handler..."
python /app/src/discord/handler.py &
HANDLER_PID=$!

echo "[SYSTEM] Starting Discord worker..."
python /app/src/worker.py &
WORKER_PID=$!

wait "$HANDLER_PID" "$WORKER_PID"
