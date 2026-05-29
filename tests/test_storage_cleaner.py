"""Tests for permission-tolerant storage cleanup."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from services import storage_cleaner


def test_safe_delete_file(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    assert storage_cleaner.safe_delete(f) is True
    assert not f.exists()


def test_safe_delete_missing_returns_true(tmp_path: Path):
    assert storage_cleaner.safe_delete(tmp_path / "nope.txt") is True


def test_safe_delete_directory(tmp_path: Path):
    d = tmp_path / "sub"
    d.mkdir()
    (d / "x.txt").write_text("x")
    assert storage_cleaner.safe_delete(d) is True
    assert not d.exists()


def test_safe_delete_protects_gitkeep(tmp_path: Path):
    g = tmp_path / ".gitkeep"
    g.write_text("")
    assert storage_cleaner.safe_delete(g) is False
    assert g.exists()


def test_empty_directory_keeps_markers(tmp_path: Path):
    (tmp_path / ".gitkeep").write_text("")
    (tmp_path / "a.log").write_text("a")
    (tmp_path / "b.log").write_text("b")
    removed = storage_cleaner.empty_directory(tmp_path)
    assert removed == 2
    assert (tmp_path / ".gitkeep").exists()


def test_cleanup_stale_only_removes_old(tmp_path: Path):
    old = tmp_path / "old.log"
    new = tmp_path / "new.log"
    old.write_text("x")
    new.write_text("x")
    # Backdate `old` by 10 days.
    ten_days_ago = time.time() - 10 * 86400
    os.utime(old, (ten_days_ago, ten_days_ago))
    removed = storage_cleaner.cleanup_stale(tmp_path, max_age_days=5)
    assert removed == 1
    assert new.exists()
    assert not old.exists()


def test_safe_delete_readonly_file(tmp_path: Path):
    f = tmp_path / "ro.txt"
    f.write_text("x")
    f.chmod(0o400)  # read-only
    # Should still succeed without prompting / blocking.
    assert storage_cleaner.safe_delete(f) is True
    assert not f.exists()


@pytest.mark.asyncio
async def test_safe_delete_async_with_timeout(tmp_path: Path):
    f = tmp_path / "async.txt"
    f.write_text("x")
    ok = await storage_cleaner.safe_delete_async(f, timeout=2.0)
    assert ok is True
    assert not f.exists()


def test_run_cleanup_cycle_returns_dict(tmp_path: Path, monkeypatch):
    # Should never raise even with empty dirs.
    res = storage_cleaner.run_cleanup_cycle()
    assert isinstance(res, dict)
