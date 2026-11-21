"""The Streamlit app as a whole, plus the guard against stale modules on a hot redeploy."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from module_freshness import ensure_fresh  # noqa: E402


def test_app_runs_without_exception():
    """Runs the whole script headless with default settings. Catches a caller and a callee
    that disagree (the 2026-11-20 outage) before the push, not on the hosted app."""
    from streamlit.testing.v1 import AppTest

    # The app may re-import ets_sim (see module_freshness). Put back the copies the other test
    # modules already hold, so later tests do not mix classes from two imports.
    saved = {n: m for n, m in sys.modules.items() if n.split(".")[0] == "ets_sim"}
    try:
        at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=300).run()
    finally:
        for n in [n for n in sys.modules if n.split(".")[0] == "ets_sim"]:
            del sys.modules[n]
        sys.modules.update(saved)
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) > 0


def test_one_failing_tab_does_not_blank_the_page(monkeypatch):
    """Break the Bottlenecks tab only. It shows a plain error; every other tab still renders."""
    from streamlit.testing.v1 import AppTest

    saved = {n: m for n, m in sys.modules.items() if n.split(".")[0] == "ets_sim"}
    try:
        # Import a fresh, stamped ets_sim so the app keeps it (and our patch) instead of re-importing.
        ensure_fresh("ets_sim", ROOT / "src" / "ets_sim")
        metrics = importlib.import_module("ets_sim.metrics")

        def broken(*_a, **_k):
            raise RuntimeError("forced failure for the test")

        monkeypatch.setattr(metrics, "bottlenecks", broken)
        at = AppTest.from_file(str(ROOT / "app" / "streamlit_app.py"), default_timeout=300).run()
    finally:
        for n in [n for n in sys.modules if n.split(".")[0] == "ets_sim"]:
            del sys.modules[n]
        sys.modules.update(saved)

    assert not at.exception or all("forced failure" in str(e.value) for e in at.exception)
    errors = [e.value for e in at.error]
    assert any("Bottlenecks tab could not finish" in e for e in errors), errors
    assert sum("could not finish" in e for e in errors) == 1, errors  # only that tab failed
    assert len(at.tabs) == 7
    assert len(at.tabs[6].markdown) > 0  # a tab after the broken one still rendered


def _write(pkg_dir: Path, body: str, mtime: int) -> None:
    f = pkg_dir / "__init__.py"
    f.write_text(body, encoding="utf-8")
    os.utime(f, ns=(mtime, mtime))


@pytest.fixture
def fake_pkg(tmp_path, monkeypatch):
    pkg_dir = tmp_path / "freshpkg"
    pkg_dir.mkdir()
    monkeypatch.syspath_prepend(str(tmp_path))
    yield pkg_dir
    for name in [n for n in sys.modules if n.split(".")[0] == "freshpkg"]:
        del sys.modules[name]


def test_ensure_fresh_reloads_changed_source(fake_pkg):
    _write(fake_pkg, "def section(title, note=''):\n    return 2\n", 1_000_000_000_000_000_000)
    assert ensure_fresh("freshpkg", fake_pkg) is False  # first import, nothing stale
    old = sys.modules["freshpkg"]
    with pytest.raises(TypeError):
        old.section("t", "n", "guide")

    # Same files: the loaded module is kept.
    assert ensure_fresh("freshpkg", fake_pkg) is False
    assert sys.modules["freshpkg"] is old

    # A deploy changes the signature: the stale copy is dropped and the new one imported.
    _write(fake_pkg, "def section(title, note='', guide=''):\n    return 3\n", 1_000_000_001_000_000_000)
    assert ensure_fresh("freshpkg", fake_pkg) is True
    assert sys.modules["freshpkg"].section("t", "n", "guide") == 3


def test_ensure_fresh_drops_unstamped_module(fake_pkg):
    """A process that imported the package before this guard existed holds no stamp; it must
    be treated as stale so the first deploy carrying the guard also heals the running app."""
    _write(fake_pkg, "X = 1\n", 1_000_000_000_000_000_000)
    import freshpkg  # noqa: F401  (plain import, no stamp)
    assert ensure_fresh("freshpkg", fake_pkg) is True
