"""Vercel entrypoint: one Python function serves the API and the built React frontend.

The backend's modules import from the `app` package inside backend/, so backend/ goes
on sys.path before the FastAPI app is imported.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

# Vite builds the frontend into frontend/dist during the Vercel build step.
os.environ.setdefault("STATIC_DIR", str(ROOT / "frontend" / "dist"))
# The function filesystem is read-only apart from /tmp, so skip the JSONL metrics file.
os.environ.setdefault("METRICS_DISABLED", "1")

from app.main import app  # noqa: E402,F401
