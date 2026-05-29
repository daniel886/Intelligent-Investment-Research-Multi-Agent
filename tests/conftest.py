"""Pytest fixtures."""
import asyncio
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True, scope="session")
def _clean_test_artifacts():
    """Remove leftover test SQLite/Chroma fixtures before and after the suite.

    Uses storage_cleaner.safe_delete so a permission/locked-file does NOT
    stall the test run — failures are logged and skipped silently.
    """
    try:
        from services.storage_cleaner import cleanup_stale, safe_delete
    except Exception:  # pragma: no cover - safety net for early import errors
        yield
        return

    data_dir = ROOT / "data"
    # Pre-test: clear yesterday's leftovers (>30 min old).
    cleanup_stale(data_dir, max_age_days=0.02, pattern="test_*.db*")
    yield
    # Post-test: best-effort wipe of any test_*.db / *.tmp file just produced.
    for pattern in ("test_*.db", "test_*.db-journal", "test_*.db-wal", "*.tmp"):
        for entry in data_dir.glob(pattern):
            safe_delete(entry)
