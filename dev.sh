#!/usr/bin/env bash
# dev.sh - Single-command development runner

cleanup() {
  echo "Stopping services..."
  kill $(jobs -p) 2>/dev/null
  exit 0
}
trap cleanup SIGINT SIGTERM

echo "Starting BackseatCaster Backend (VideoToolbox enabled)..."
uv run uvicorn app.main:app --port 3001 --reload &

echo "Starting Next.js UI..."
(cd ui && npm run dev) &

wait
