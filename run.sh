#!/usr/bin/env bash
# Starts backend (port 8000) and frontend (port 5173). Ctrl+C stops both.
set -e
cd "$(dirname "$0")"

if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -r backend/requirements.txt
fi
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install)
fi

(cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000) &
BACK=$!
trap 'kill $BACK 2>/dev/null' EXIT
cd frontend && npm run dev
