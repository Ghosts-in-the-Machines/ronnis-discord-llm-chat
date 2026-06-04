#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

source venv/bin/activate
python -m pip install --quiet -r requirements.txt

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
  echo "[SYSTEM] Created .env from .env.example. Fill in DISCORD_BOT_TOKEN before production use."
fi

mkdir -p data

cleanup() {
  [ -n "${HANDLER_PID:-}" ] && kill "$HANDLER_PID" 2>/dev/null || true
  [ -n "${WORKER_PID:-}" ] && kill "$WORKER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[SYSTEM] Starting Discord handler..."
python src/discord/handler.py &
HANDLER_PID=$!

echo "[SYSTEM] Starting Discord worker..."
python src/worker.py &
WORKER_PID=$!

wait "$HANDLER_PID" "$WORKER_PID"
