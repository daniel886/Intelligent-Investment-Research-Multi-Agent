"""Probe B: confirm that shutil.rmtree silently ignores onerror= when
ignore_errors=True is also set, AND that onerror= is deprecated in 3.12+.

We replicate storage_cleaner._on_rmtree_error and verify it never gets called.
"""
from __future__ import annotations
import os
import shutil
import stat
import sys
import tempfile
import warnings
from pathlib import Path


def main() -> int:
    issues = 0
    called = {"onerror": 0}

    def _on_err(func, target, exc_info):
        called["onerror"] += 1

    # Build a directory we cannot remove on first try (read-only file).
    tmp = Path(tempfile.mkdtemp(prefix="probe_b_"))
    nested = tmp / "sub"
    nested.mkdir()
    f = nested / "locked.txt"
    f.write_text("x")
    # Strip write perm from the parent so unlink fails on POSIX.
    try:
        os.chmod(nested, 0o555)
    except OSError:
        pass

    # Case 1: ignore_errors=True + onerror=cb → cb should NOT fire (signature
    # of the contradiction in storage_cleaner.py:139,160).
    with warnings.catch_warnings(record=True) as warned:
        warnings.simplefilter("always")
        called["onerror"] = 0
        shutil.rmtree(tmp, ignore_errors=True, onerror=_on_err)

    print(f"[probe_b] ignore_errors=True + onerror={_on_err.__name__}: callback fired {called['onerror']} times")
    if called["onerror"] > 0:
        print("[probe_b] WARN: callback fired — would not have happened in 3.12 with ignore_errors=True")
    else:
        print("[probe_b] CONFIRMED: ignore_errors=True silently disables onerror=")
        issues = 1

    # Restore perms then full clean.
    try:
        os.chmod(tmp / "sub", 0o755)
    except FileNotFoundError:
        pass
    shutil.rmtree(tmp, ignore_errors=True)

    # Case 2: detect the deprecation if running on >=3.12.
    py_major, py_minor = sys.version_info[:2]
    print(f"[probe_b] python={py_major}.{py_minor}")
    if (py_major, py_minor) >= (3, 12):
        print("[probe_b] On Python 3.12+, shutil.rmtree(onerror=...) is DEPRECATED — must migrate to onexc=")

    return issues


if __name__ == "__main__":
    raise SystemExit(main())
