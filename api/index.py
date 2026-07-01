"""Vercel serverless entrypoint.

Vercel detects the FastAPI `app` here and serves it for /api/* (see vercel.json).
The backend package lives in ../backend; add it to the path and re-export `app`.
On Vercel, config.READONLY is auto-enabled via the VERCEL env var, so the bundled
SQLite is opened immutably and no writes are attempted (config comes per-request).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from server import app  # noqa: E402,F401  (re-exported for Vercel)
