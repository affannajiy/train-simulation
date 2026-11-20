"""Find and read logged realtime CSVs, locally or from the repo's realtime-data branch.

The logger (GitHub Actions) commits one CSV per UTC day to the `realtime-data` branch.
A local checkout can restore them into data/realtime/. A hosted app has no such folder,
so it reads them over HTTPS from raw.githubusercontent.com instead. raw.githubusercontent
cannot list a folder, so the remote side probes the last N UTC dates by file name; this
avoids the GitHub API and its 60-requests-per-hour unauthenticated limit.
"""

from __future__ import annotations

import datetime as dt
import io
import re
from pathlib import Path

import pandas as pd
import requests

from ets_sim.config import project_path

RAW_BASE = "https://raw.githubusercontent.com"
_REPO_RE = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")


def remote_base(cfg: dict) -> str | None:
    """Base URL of the branch's realtime folder, or None when no repo is configured."""
    repo = str(cfg["data"].get("realtime_repo", "")).strip()
    if not repo or repo.startswith("OWNER/") or not _REPO_RE.match(repo):
        return None
    branch = str(cfg["data"].get("realtime_branch", "realtime-data"))
    return f"{RAW_BASE}/{repo}/{branch}/data/realtime"


def local_days(cfg: dict) -> dict[str, Path]:
    d = project_path(cfg["data"]["realtime_dir"])
    return {f.stem: f for f in sorted(d.glob("*.csv"))}


def remote_days(cfg: dict, today: dt.date | None = None) -> dict[str, str]:
    """Probe the last N UTC dates on the branch; return {day: url} for the ones that exist."""
    base = remote_base(cfg)
    if base is None:
        return {}
    n = int(cfg["data"].get("realtime_remote_days", 7))
    today = today or dt.datetime.now(dt.timezone.utc).date()
    timeout = min(int(cfg["data"].get("http_timeout_s", 60)), 10)
    found: dict[str, str] = {}
    with requests.Session() as s:
        for i in range(n - 1, -1, -1):  # oldest first, so the newest ends up last
            day = (today - dt.timedelta(days=i)).isoformat()
            url = f"{base}/{day}.csv"
            try:
                if s.head(url, timeout=timeout, allow_redirects=True).status_code == 200:
                    found[day] = url
            except requests.RequestException:
                continue
    return found


# Identifier columns stay text even when every value looks numeric (labels like "303").
_TEXT_COLUMNS = {c: str for c in ("entity_id", "trip_id", "route_id", "vehicle_id", "vehicle_label", "stop_id")}


def read_day(source: str | Path, timeout_s: int = 30) -> pd.DataFrame:
    """Read one day's CSV from a local path or a URL."""
    if isinstance(source, Path):
        df = pd.read_csv(source, dtype=_TEXT_COLUMNS)
    else:
        resp = requests.get(source, timeout=timeout_s)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), dtype=_TEXT_COLUMNS)
    if "bad_position" in df.columns:
        # Always boolean, so `~df["bad_position"]` works even on a partly malformed file.
        df["bad_position"] = df["bad_position"].astype(str).str.strip().str.lower() == "true"
    return df
