"""Keep the ets_sim package in step with the files on disk.

Why this exists: Streamlit Community Cloud pulls a new commit into the running process and
reruns the script. Streamlit reloads modules under app/, but ets_sim lives in src/, so the
old ets_sim modules stay in sys.modules. A commit that changes a function signature in both
places then fails with a TypeError (2026-11-20: style.section() gained a guide argument).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_STAMP = "_source_fingerprint"


def fingerprint(src_dir: Path) -> tuple[tuple[str, int, int], ...]:
    """(relative path, mtime_ns, size) of every .py and .html file below src_dir, sorted."""
    files = sorted(p for p in src_dir.rglob("*") if p.suffix in {".py", ".html"} and p.is_file())
    out = []
    for p in files:
        st = p.stat()
        out.append((p.relative_to(src_dir).as_posix(), st.st_mtime_ns, st.st_size))
    return tuple(out)


def ensure_fresh(package: str, src_dir: Path) -> bool:
    """Import package; if a loaded copy is older than the files in src_dir, drop it and its
    submodules first. Returns True when stale modules were dropped (the caller should then
    clear caches that may hold objects built by the old code)."""
    fp = fingerprint(src_dir)
    loaded = sys.modules.get(package)
    if loaded is not None and getattr(loaded, _STAMP, None) == fp:
        return False
    stale = loaded is not None
    for name in [n for n in sys.modules if n == package or n.startswith(package + ".")]:
        del sys.modules[name]
    importlib.invalidate_caches()
    setattr(importlib.import_module(package), _STAMP, fp)
    return stale
