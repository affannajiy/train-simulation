"""Poll the KTMB vehicle-position feed and append rows to one CSV per UTC day.

Run once:
    python logger/fetch_realtime.py --once
Run the GitHub Actions loop (poll every 60 s for 55 min, values from config.yaml):
    python logger/fetch_realtime.py

Output: <realtime_dir>/YYYY-MM-DD.csv (UTC date of observation). A failed poll is
reported on stderr and skipped; the loop keeps going so one bad response never loses
the rest of the hour.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import time
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from decode_feed import COLUMNS, decode  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def fetch(url: str, timeout_s: int, retries: int = 2) -> bytes:
    """GET with a timeout and a short capped backoff."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, timeout=timeout_s)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(min(2 ** attempt * 2, 10))
    raise RuntimeError(f"fetch failed after {retries + 1} attempts: {last_error}")


def append_rows(out_dir: Path, rows: list[dict]) -> Path | None:
    """Append rows to today's CSV, writing the header only when the file is new."""
    if not rows:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    day = rows[0]["observed_at_utc"][:10]
    path = out_dir / f"{day}.csv"
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        if new:
            writer.writeheader()
        writer.writerows(rows)
    return path


def poll_once(url: str, timeout_s: int, out_dir: Path, bbox: dict) -> int:
    observed = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    rows = decode(fetch(url, timeout_s), observed, bbox)
    append_rows(out_dir, rows)
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "config.yaml"))
    parser.add_argument("--out-dir", help="override data.realtime_dir")
    parser.add_argument("--once", action="store_true", help="poll a single time and exit")
    args = parser.parse_args(argv)

    with open(args.config, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    url = cfg["data"]["realtime_vehicle_url"]
    timeout_s = int(cfg["data"]["http_timeout_s"])
    lcfg = cfg["realtime_logger"]
    out_dir = Path(args.out_dir) if args.out_dir else PROJECT_ROOT / cfg["data"]["realtime_dir"]

    deadline = time.monotonic() + (0 if args.once else lcfg["run_duration_min"] * 60)
    polls = failures = 0
    while True:
        started = time.monotonic()
        try:
            n = poll_once(url, timeout_s, out_dir, lcfg["bbox"])
            print(f"{dt.datetime.now(dt.timezone.utc):%H:%M:%S} vehicles={n}", flush=True)
        except Exception as exc:  # report and keep polling; see module docstring
            failures += 1
            print(f"poll failed: {exc}", file=sys.stderr, flush=True)
        polls += 1
        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.0, lcfg["poll_interval_s"] - (time.monotonic() - started)))
    print(f"done: {polls} polls, {failures} failed")
    # Non-zero exit only if every poll failed, so the workflow shows red for a dead feed.
    return 1 if failures == polls else 0


if __name__ == "__main__":
    sys.exit(main())
