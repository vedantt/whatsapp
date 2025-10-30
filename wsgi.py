#!/usr/bin/env python3
# WSGI entrypoint for PythonAnywhere (or any WSGI host)
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Environment defaults (override in host env)
os.environ.setdefault("FLASK_ENV", "production")

# Import Flask app
from app import app as application  # noqa: E402
