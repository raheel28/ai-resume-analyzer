import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("STATIC_DIR", str(ROOT / "frontend" / "dist"))
os.environ.setdefault("METRICS_DISABLED", "1")

from app.main import app
