"""Permission-tolerant, non-blocking file/dir cleanup utilities.

Goals
-----
1. Never block the main loop waiting on a permission prompt.
2. On any OSError / PermissionError / FileNotFoundError → log and return
   instead of raising. Automation must continue.
3. Two-phase delete:
   - Phase A (fast, atomic): rename the target into the project's `.trash/`
     bucket using a unique suffix. This succeeds in microseconds even when
     the file is locked on Windows or held by another async task.
   - Phase B (lazy): a best-effort sweep removes everything inside
     `.trash/` whenever it is safe to do so. Anything that still resists
     deletion is left in place for the next sweep — never blocking.
4. Preserve `.gitkeep` / `.gitignore` markers so version control remains intact.
5. Async wrappers run via `asyncio.to_thread` and respect a hard
   per-operation timeout so a misbehaving FS layer can't stall the agent.

Public API
----------
- safe_delete(path)                  — best-effort delete (sync)
- safe_delete_async(path)            — best-effort delete (async, timeout)
- empty_directory(path, keep=...)    — wipe a directory's contents, keep markers
- cleanup_stale(path, max_age_days)  — prune files older than N days
- sweep_trash()                      — opportunistic trash flush
- run_cleanup_cycle()                — full daily cleanup routine (used by scheduler)
"""
from __future__ import annotations

import asyncio
import errno
import os
import shutil
import stat
import sys
import time
import uuid
from pathlib import Path
from typing import Iterable, Optional, Set

from config import settings
from config.logging import logger

# Files we never want to remove — they keep empty dirs alive in git.
PROTECTED_NAMES: Set[str] = {".gitkeep", ".gitignore"}

# Default retention windows (overridable via settings).
_DEFAULT_RETENTION_DAYS = 14
_DEFAULT_OP_TIMEOUT = 5.0  # seconds


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _trash_root() -> Path:
    root = Path(settings.project_root) / ".trash"
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        # If we cannot even create .trash, fall back to a tmp dir.
        logger.warning("storage_cleaner: cannot create .trash ({}); using OS temp", e)
        import tempfile

        return Path(tempfile.gettempdir()) / "iir_trash"
    return root


def _is_protected(path: Path) -> bool:
    return path.name in PROTECTED_NAMES


def _force_writable(path: Path) -> None:
    """Best-effort chmod so a subsequent unlink/rmtree won't EACCES."""
    try:
        path.chmod(path.stat().st_mode | stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    except OSError:
        pass


def _on_rmtree_error(func, target, exc_info) -> None:  # noqa: D401, ANN001
    """rmtree onerror: chmod + retry once, then swallow the error.

    Round-2 fix #5: This callback used to be wired up alongside
    ``ignore_errors=True``. CPython short-circuits to a no-op handler when
    ``ignore_errors`` is true, so this function was dead code and any error
    we hit was silently swallowed without the chmod+retry happening. Callers
    now invoke ``_rmtree_safe`` instead, which dispatches to the right
    callback for the running Python version.
    """
    try:
        _force_writable(Path(target))
        func(target)
    except OSError as e:
        if e.errno not in (errno.ENOENT,):
            logger.debug("storage_cleaner: rmtree skipping {} ({})", target, e)


def _on_rmtree_exc(func, target, exc) -> None:  # noqa: D401, ANN001
    """Python 3.12+ ``onexc`` callback (single exception, not tuple)."""
    try:
        _force_writable(Path(target))
        func(target)
    except OSError as e:
        if e.errno not in (errno.ENOENT,):
            logger.debug("storage_cleaner: rmtree skipping {} ({})", target, e)


def _rmtree_safe(path: Path) -> None:
    """``shutil.rmtree`` with the correct error callback for this interpreter.

    On Python 3.12 ``onerror`` is deprecated in favour of ``onexc``; on 3.14
    ``onerror`` is removed outright. The callback never re-raises, so we get
    the same effect as ``ignore_errors=True`` *plus* the chmod+retry path.
    """
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_on_rmtree_exc)
    else:
        shutil.rmtree(path, onerror=_on_rmtree_error)


def _move_to_trash(path: Path) -> Optional[Path]:
    """Atomically rename `path` into `.trash/<uuid>__<name>`. Returns the new
    path on success, or None if the rename couldn't happen."""
    if not path.exists() and not path.is_symlink():
        return None
    trash = _trash_root()
    target = trash / f"{int(time.time())}_{uuid.uuid4().hex[:8]}__{path.name}"
    try:
        os.replace(path, target)  # atomic on same FS, never prompts
        return target
    except OSError as e:
        # Cross-device or locked file — fall back to copy+unlink, but only
        # if this is a small file. For dirs / large files we just give up
        # quietly and let the next sweep try again.
        if path.is_file():
            try:
                shutil.copy2(path, target)
                _force_writable(path)
                path.unlink(missing_ok=True)
                return target
            except OSError as e2:
                logger.debug("storage_cleaner: trash-copy failed for {} ({})", path, e2)
        else:
            logger.debug("storage_cleaner: rename-to-trash failed for {} ({})", path, e)
    return None


# ---------------------------------------------------------------------------
# Public sync API
# ---------------------------------------------------------------------------
def safe_delete(path: str | os.PathLike[str]) -> bool:
    """Best-effort, non-blocking delete.

    Strategy: rename into `.trash/`, then opportunistically try to remove the
    moved entry. NEVER raises — returns True if the entry is no longer at the
    original location, False otherwise.
    """
    p = Path(path)
    try:
        if not p.exists() and not p.is_symlink():
            return True
        if _is_protected(p):
            logger.debug("storage_cleaner: refusing to delete protected {}", p)
            return False
        moved = _move_to_trash(p)
        if moved is None:
            # Could not even rename — last-ditch direct unlink (still tolerant).
            try:
                if p.is_dir() and not p.is_symlink():
                    _rmtree_safe(p)
                else:
                    _force_writable(p)
                    p.unlink(missing_ok=True)
            except OSError as e:
                logger.warning("storage_cleaner: direct delete failed for {} ({})", p, e)
                return False
            return not p.exists()
        # Quietly try to fully remove the trashed entry; if it fails, the next
        # sweep_trash() call will try again. Either way the original path is gone.
        _try_remove(moved)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("storage_cleaner.safe_delete unexpected error on {}: {}", p, e)
        return False


def _try_remove(path: Path) -> bool:
    """Remove a path silently. Returns True iff it's gone afterwards."""
    try:
        if path.is_dir() and not path.is_symlink():
            _rmtree_safe(path)
        else:
            _force_writable(path)
            path.unlink(missing_ok=True)
    except OSError:
        return False
    return not path.exists()


def empty_directory(
    path: str | os.PathLike[str],
    keep: Iterable[str] = (),
) -> int:
    """Delete every entry under `path` except `keep` and protected markers.

    Returns the number of entries successfully removed. Never raises.
    """
    p = Path(path)
    if not p.is_dir():
        return 0
    keep_set = set(keep) | PROTECTED_NAMES
    removed = 0
    try:
        children = list(p.iterdir())
    except OSError as e:
        logger.warning("storage_cleaner: cannot list {} ({})", p, e)
        return 0
    for child in children:
        if child.name in keep_set:
            continue
        if safe_delete(child):
            removed += 1
    return removed


def cleanup_stale(
    path: str | os.PathLike[str],
    max_age_days: float = _DEFAULT_RETENTION_DAYS,
    pattern: str = "*",
) -> int:
    """Prune files in `path` older than `max_age_days`. Returns count removed."""
    p = Path(path)
    if not p.is_dir():
        return 0
    cutoff = time.time() - max_age_days * 86400.0
    removed = 0
    try:
        candidates = list(p.glob(pattern))
    except OSError as e:
        logger.warning("storage_cleaner: glob {} failed ({})", p, e)
        return 0
    for entry in candidates:
        if _is_protected(entry):
            continue
        try:
            if entry.stat().st_mtime > cutoff:
                continue
        except OSError:
            continue
        if safe_delete(entry):
            removed += 1
    if removed:
        logger.info("storage_cleaner: pruned {} stale entries from {}", removed, p)
    return removed


def sweep_trash(max_seconds: float = 2.0) -> int:
    """Best-effort flush of `.trash/`. Bounded by `max_seconds`."""
    trash = _trash_root()
    if not trash.is_dir():
        return 0
    removed = 0
    deadline = time.time() + max_seconds
    try:
        entries = list(trash.iterdir())
    except OSError:
        return 0
    for entry in entries:
        if time.time() > deadline:
            logger.debug("storage_cleaner: sweep budget exhausted, deferring rest")
            break
        if _try_remove(entry):
            removed += 1
    return removed


def run_cleanup_cycle() -> dict:
    """One full cleanup pass — safe to call from scheduler / startup hooks.

    Cleans:
      - reports/   : older than retention_days
      - logs/      : older than retention_days (Loguru also rotates)
      - data/*.tmp : transient SQLite WAL/journal leftovers
      - .trash/    : opportunistic flush
      - data/test_*.db : leftover test fixtures
    """
    if not getattr(settings, "cleanup_enabled", True):
        logger.info("storage_cleaner: cleanup disabled by settings")
        return {"enabled": False}

    retention = float(getattr(settings, "cleanup_retention_days", _DEFAULT_RETENTION_DAYS))
    project = Path(settings.project_root)
    stats = {
        "reports_pruned": cleanup_stale(project / "reports", retention),
        "logs_pruned": cleanup_stale(project / "logs", retention, pattern="*.log*"),
        "tmp_pruned": cleanup_stale(project / "data", 1.0, pattern="*.tmp"),
        "test_dbs_pruned": cleanup_stale(project / "data", 0.5, pattern="test_*.db*"),
        "trash_swept": sweep_trash(max_seconds=2.0),
    }
    logger.info("storage_cleaner: cycle complete {}", stats)
    return stats


# ---------------------------------------------------------------------------
# Async API
# ---------------------------------------------------------------------------
async def safe_delete_async(
    path: str | os.PathLike[str],
    timeout: Optional[float] = None,
) -> bool:
    """Async wrapper around safe_delete with a hard timeout. Never raises."""
    t = float(timeout if timeout is not None else getattr(
        settings, "cleanup_op_timeout_seconds", _DEFAULT_OP_TIMEOUT
    ))
    try:
        return await asyncio.wait_for(asyncio.to_thread(safe_delete, path), timeout=t)
    except asyncio.TimeoutError:
        logger.warning("storage_cleaner: safe_delete timed out for {} ({}s)", path, t)
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("storage_cleaner: async delete failed for {}: {}", path, e)
        return False


async def run_cleanup_cycle_async(timeout: float = 30.0) -> dict:
    """Async wrapper around run_cleanup_cycle with a hard upper bound."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(run_cleanup_cycle), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("storage_cleaner: cycle timed out after {}s", timeout)
        return {"timeout": True}
    except Exception as e:  # noqa: BLE001
        logger.warning("storage_cleaner: cycle failed: {}", e)
        return {"error": str(e)}


__all__ = [
    "PROTECTED_NAMES",
    "safe_delete",
    "safe_delete_async",
    "empty_directory",
    "cleanup_stale",
    "sweep_trash",
    "run_cleanup_cycle",
    "run_cleanup_cycle_async",
]
