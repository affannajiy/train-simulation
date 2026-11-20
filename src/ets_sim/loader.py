"""GTFS static loader: KTMB feed -> clean ETS stations, trips and stop times.

Run:
    python -m ets_sim.loader              # use the pinned snapshot from config.yaml
    python -m ets_sim.loader --download   # fetch today's feed into data/raw first

Outputs (data/processed/):
    stations.csv      one row per station: name, stop_id, lat, lon, line_km, branch info
    trips.csv         one row per trip: origin, destination, times, flags
    stop_times.csv    one row per trip stop, times as seconds from service-day start
    data_quality.csv  every row dropped, truncated or flagged, with the reason
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import statistics
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import requests

from ets_sim.config import load_config, project_path

REQUIRED_FILES = ("routes.txt", "trips.txt", "stops.txt", "stop_times.txt", "calendar.txt")

# Line km increases in the southbound direction (direction_id 1), so Padang Besar is km 0.
# Verified against the 2026-11-20 feed: direction 1 trips run Padang Besar -> JB Sentral.
SOUTHBOUND_DIRECTION = 1


@dataclass
class Timetable:
    """Clean loader output. All times are integer seconds from service-day start."""

    stations: pd.DataFrame
    trips: pd.DataFrame
    stop_times: pd.DataFrame
    quality: pd.DataFrame
    feed_name: str = ""


@dataclass
class _QualityLog:
    rows: list[dict] = field(default_factory=list)

    def add(self, issue: str, trip_id: str = "", detail: str = "") -> None:
        self.rows.append({"issue": issue, "trip_id": trip_id, "detail": detail})

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=["issue", "trip_id", "detail"])


# ---------------------------------------------------------------- reading


def download_feed(url: str, dest_dir: Path, timeout_s: int = 60) -> Path:
    """Download the static feed to dest_dir/ktmb_gtfs_<date>.zip and return the path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=timeout_s)
    resp.raise_for_status()
    # Validate it is a zip before writing, so a server error page never becomes "the feed".
    zipfile.ZipFile(io.BytesIO(resp.content)).testzip()
    path = dest_dir / f"ktmb_gtfs_{dt.date.today().isoformat()}.zip"
    path.write_bytes(resp.content)
    return path


def read_feed(zip_path: Path) -> dict[str, pd.DataFrame]:
    """Read every .txt file in the GTFS zip as strings. Fails if a core file is missing."""
    frames: dict[str, pd.DataFrame] = {}
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        missing = [f for f in REQUIRED_FILES if f not in names]
        if missing:
            raise ValueError(f"{zip_path.name} is missing GTFS files: {missing}")
        for name in names:
            if name.endswith(".txt"):
                with zf.open(name) as fh:
                    frames[name[:-4]] = pd.read_csv(fh, dtype=str, keep_default_na=False)
    return frames


def gtfs_time_to_seconds(value: str) -> int:
    """'25:30:00' -> 91800. GTFS allows hours >= 24 for trips that run past midnight."""
    parts = value.strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"Bad GTFS time: {value!r}")
    h, m, s = (int(p) for p in parts)
    return h * 3600 + m * 60 + s


def active_service_ids(feed: dict[str, pd.DataFrame], date: dt.date) -> set[str]:
    """Service ids running on `date`, from calendar.txt plus calendar_dates.txt exceptions."""
    cal = feed["calendar"]
    ymd = date.strftime("%Y%m%d")
    weekday = date.strftime("%A").lower()
    in_range = (cal["start_date"] <= ymd) & (cal["end_date"] >= ymd) & (cal[weekday] == "1")
    active = set(cal.loc[in_range, "service_id"])
    exc = feed.get("calendar_dates")
    if exc is not None and len(exc):
        today = exc[exc["date"] == ymd]
        active |= set(today.loc[today["exception_type"] == "1", "service_id"])
        active -= set(today.loc[today["exception_type"] == "2", "service_id"])
    return active


# ---------------------------------------------------------------- cleaning


def _select_trips(feed, routes, date, log: _QualityLog) -> pd.DataFrame:
    trips = feed["trips"]
    trips = trips[trips["route_id"].isin(routes)].copy()
    if trips.empty:
        raise ValueError(f"No trips found for routes {routes}")
    services = active_service_ids(feed, date)
    inactive = trips[~trips["service_id"].isin(services)]
    for tid in inactive["trip_id"]:
        log.add("inactive_on_service_date", tid, date.isoformat())
    trips = trips[trips["service_id"].isin(services)]
    if trips.empty:
        raise ValueError(f"No {routes} trips run on {date}; check network.service_date")
    trips["direction_id"] = trips["direction_id"].astype(int)
    return trips[["trip_id", "route_id", "service_id", "direction_id"]]


def _prepare_stop_times(feed, trips, stops) -> pd.DataFrame:
    st = feed["stop_times"]
    st = st[st["trip_id"].isin(trips["trip_id"])].copy()
    st["stop_sequence"] = st["stop_sequence"].astype(int)
    st["arr_s"] = st["arrival_time"].map(gtfs_time_to_seconds)
    st["dep_s"] = st["departure_time"].map(gtfs_time_to_seconds)
    if (st["shape_dist_traveled"] == "").any():
        raise ValueError("shape_dist_traveled is missing for some stops; line km cannot be derived")
    st["dist_km"] = st["shape_dist_traveled"].astype(float)
    st = st.merge(stops[["stop_id", "stop_name"]], on="stop_id", how="left", validate="many_to_one")
    if st["stop_name"].isna().any():
        raise ValueError("stop_times references stop_ids not in stops.txt")
    st = st.rename(columns={"stop_name": "station"})
    st = st.merge(trips[["trip_id", "direction_id"]], on="trip_id")
    return st.sort_values(["trip_id", "stop_sequence"]).reset_index(drop=True)[
        ["trip_id", "direction_id", "stop_sequence", "stop_id", "station", "arr_s", "dep_s", "dist_km"]
    ]


def _truncate_excluded(st: pd.DataFrame, excluded: list[str], log: _QualityLog):
    """Drop stops at excluded stations. Returns stop_times and the set of truncated trips."""
    hit = st["station"].isin(excluded)
    truncated = set(st.loc[hit, "trip_id"])
    for tid in sorted(truncated):
        names = ", ".join(st.loc[hit & (st["trip_id"] == tid), "station"])
        log.add("truncated_at_excluded_station", tid, f"removed: {names}")
    return st[~hit].reset_index(drop=True), truncated


def _drop_exact_duplicates(st: pd.DataFrame, log: _QualityLog) -> pd.DataFrame:
    """Trips with identical (stop, arr, dep) sequences: keep the lowest trip_id."""
    sig = st.groupby("trip_id").apply(
        lambda g: tuple(zip(g["stop_id"], g["arr_s"], g["dep_s"])), include_groups=False
    )
    keep: dict[tuple, str] = {}
    drop: set[str] = set()
    for tid in sorted(sig.index, key=_trip_sort_key):
        s = sig[tid]
        if s in keep:
            drop.add(tid)
            log.add("exact_duplicate_dropped", tid, f"same timetable as trip {keep[s]}")
        else:
            keep[s] = tid
    return st[~st["trip_id"].isin(drop)].reset_index(drop=True)


def _trip_sort_key(trip_id: str):
    return (0, int(trip_id), "") if trip_id.isdigit() else (1, 0, trip_id)


def _fix_trip_ends(st: pd.DataFrame) -> pd.DataFrame:
    """Origin arrives when it departs; destination departs when it arrives."""
    st = st.copy()
    first = st.groupby("trip_id")["stop_sequence"].transform("min") == st["stop_sequence"]
    last = st.groupby("trip_id")["stop_sequence"].transform("max") == st["stop_sequence"]
    st.loc[first, "arr_s"] = st.loc[first, "dep_s"]
    st.loc[last, "dep_s"] = st.loc[last, "arr_s"]
    return st


def _check_times(st: pd.DataFrame, log: _QualityLog) -> None:
    for tid, g in st.groupby("trip_id"):
        arr, dep = g["arr_s"].to_numpy(), g["dep_s"].to_numpy()
        if (dep < arr).any() or (arr[1:] < dep[:-1]).any():
            raise ValueError(f"Trip {tid} has times that go backwards")
        if len(g) < 2:
            raise ValueError(f"Trip {tid} has fewer than 2 stops after cleaning")


def _flag_same_minute_departures(st: pd.DataFrame, log: _QualityLog) -> None:
    origins = st.loc[st.groupby("trip_id")["stop_sequence"].idxmin()]
    for (station, dep), g in origins.groupby(["station", "dep_s"]):
        if len(g) > 1:
            ids = ", ".join(sorted(g["trip_id"], key=_trip_sort_key))
            log.add("same_minute_departure", ids, f"{station} at {_fmt(dep)}")


def _fmt(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}"


# ---------------------------------------------------------------- line km


def compute_line_km(st: pd.DataFrame, branch_termini: set[str], tol_km: float,
                    log: _QualityLog) -> dict[str, float]:
    """Main-line km per station, km 0 at the northern end.

    Each trip's shape_dist_traveled counts from its own origin. A southbound trip gives
    km = offset + dist and a northbound one km = offset - dist. Starting from the trip with
    the most main-line stops, every other trip's offset is fitted on stations already
    placed, and its remaining stations are added. Branch termini are excluded here.
    """
    main = st[~st["station"].isin(branch_termini)]
    sign = main["direction_id"].map(lambda d: 1.0 if d == SOUTHBOUND_DIRECTION else -1.0)
    main = main.assign(signed=main["dist_km"] * sign)
    groups = {tid: g for tid, g in main.groupby("trip_id")}

    ref = max(groups, key=lambda t: len(groups[t]))
    km = dict(zip(groups[ref]["station"], groups[ref]["signed"]))
    pending = set(groups) - {ref}
    while pending:
        progressed = False
        for tid in sorted(pending, key=_trip_sort_key):
            g = groups[tid]
            known = g[g["station"].isin(km)]
            if known.empty:
                continue
            offsets = [km[s] - v for s, v in zip(known["station"], known["signed"])]
            offset = statistics.median(offsets)
            spread = max(offsets) - min(offsets)
            if spread > tol_km:
                log.add("km_inconsistency", tid, f"offset spread {spread:.2f} km")
            for s, v in zip(g["station"], g["signed"]):
                km.setdefault(s, offset + v)
            pending.discard(tid)
            progressed = True
        if not progressed:
            raise ValueError(f"Trips {sorted(pending)} share no station with the rest of the line")

    base = min(km.values())
    return {s: round(v - base, 3) for s, v in km.items()}


def compute_branch_lengths(st: pd.DataFrame, km: dict[str, float],
                           branches: list[dict]) -> dict[str, float]:
    """Spur length junction -> terminus, from trips that run onto the branch."""
    lengths: dict[str, float] = {}
    for br in branches:
        term, junc = br["terminus"], br["junction"]
        if junc not in km:
            raise ValueError(f"Branch junction {junc} is not on the main line")
        estimates = []
        for _, g in st[st["trip_id"].isin(st.loc[st["station"] == term, "trip_id"])].groupby("trip_id"):
            t_dist = g.loc[g["station"] == term, "dist_km"].iloc[0]
            for s, d in zip(g["station"], g["dist_km"]):
                if s in km:
                    estimates.append(abs(d - t_dist) - abs(km[s] - km[junc]))
        if not estimates:
            raise ValueError(f"No trip serves branch terminus {term}")
        length = statistics.median(estimates)
        if length <= 0:
            raise ValueError(f"Branch {junc}-{term} has non-positive length {length:.2f}")
        lengths[term] = round(length, 3)
    return lengths


# ---------------------------------------------------------------- main build


def build_timetable(feed: dict[str, pd.DataFrame], cfg: dict) -> Timetable:
    net = cfg["network"]
    log = _QualityLog()
    date = dt.date.fromisoformat(str(net["service_date"]))

    trips = _select_trips(feed, net["routes"], date, log)
    stops = feed["stops"]
    st = _prepare_stop_times(feed, trips, stops)
    st, truncated = _truncate_excluded(st, net.get("excluded_stations", []), log)
    st = _drop_exact_duplicates(st, log)
    st = _fix_trip_ends(st)
    _check_times(st, log)
    _flag_same_minute_departures(st, log)

    branches = net.get("branches", [])
    termini = {b["terminus"] for b in branches}
    km = compute_line_km(st, termini, float(net["km_consistency_tolerance_km"]), log)
    spur = compute_branch_lengths(st, km, branches)

    # Stations
    used = st.drop_duplicates("station")[["station", "stop_id"]]
    coords = stops.rename(columns={"stop_name": "station"})[["stop_id", "stop_lat", "stop_lon"]]
    stations = used.merge(coords, on="stop_id", how="left")
    if stations["station"].duplicated().any():
        raise ValueError("Two stop_ids share one stop_name; station names must be unique")
    stations["lat"] = stations["stop_lat"].astype(float)
    stations["lon"] = stations["stop_lon"].astype(float)
    junction_of = {b["terminus"]: b["junction"] for b in branches}
    stations["branch_junction"] = stations["station"].map(junction_of).fillna("")
    stations["branch_km"] = stations["station"].map(spur).fillna(0.0)
    stations["line_km"] = [
        km[s] if s in km else km[junction_of[s]] for s in stations["station"]
    ]
    stations = stations.sort_values(["line_km", "branch_km"]).reset_index(drop=True)[
        ["station", "stop_id", "lat", "lon", "line_km", "branch_junction", "branch_km"]
    ]

    # Trips
    ends = st.groupby("trip_id").agg(
        direction_id=("direction_id", "first"),
        origin=("station", "first"),
        destination=("station", "last"),
        n_stops=("station", "size"),
        dep_s=("dep_s", "first"),
        arr_s=("arr_s", "last"),
    ).reset_index()
    ends["international"] = ends["trip_id"].isin(truncated)
    ends = ends.merge(trips[["trip_id", "route_id"]], on="trip_id")
    ends = ends.sort_values(["dep_s", "trip_id"]).reset_index(drop=True)

    stop_times = st[["trip_id", "stop_sequence", "station", "arr_s", "dep_s", "dist_km"]]
    return Timetable(stations, ends, stop_times.reset_index(drop=True), log.frame())


def load_processed(cfg: dict) -> Timetable:
    """Read the CSVs written by `main`. Run the loader first if they are missing."""
    d = project_path(cfg["data"]["processed_dir"])
    if not (d / "trips.csv").exists():
        raise FileNotFoundError(f"{d / 'trips.csv'} not found. Run: python -m ets_sim.loader")
    dtypes = {"trip_id": str, "stop_id": str}
    stations = pd.read_csv(d / "stations.csv", dtype=dtypes, keep_default_na=False)
    stations["branch_km"] = stations["branch_km"].astype(float)
    return Timetable(
        stations=stations,
        trips=pd.read_csv(d / "trips.csv", dtype=dtypes),
        stop_times=pd.read_csv(d / "stop_times.csv", dtype=dtypes),
        quality=pd.read_csv(d / "data_quality.csv", dtype=dtypes, keep_default_na=False),
    )


def write_processed(tt: Timetable, feed_name: str, cfg: dict) -> Path:
    """Write the four processed CSVs and return the folder."""
    out = project_path(cfg["data"]["processed_dir"])
    out.mkdir(parents=True, exist_ok=True)
    tt.stations.to_csv(out / "stations.csv", index=False)
    tt.trips.assign(feed=feed_name).to_csv(out / "trips.csv", index=False)
    tt.stop_times.to_csv(out / "stop_times.csv", index=False)
    tt.quality.to_csv(out / "data_quality.csv", index=False)
    return out


def load_or_build(cfg: dict) -> Timetable:
    """Read the processed CSVs; if they are missing, build them from the pinned snapshot.

    A fresh clone or a hosted deploy has no data/processed/ (it is not committed), so this
    keeps the app working without a manual loader run. The snapshot gives the same
    timetable as `python -m ets_sim.loader`.
    """
    try:
        return load_processed(cfg)
    except FileNotFoundError:
        zip_path = project_path(cfg["data"]["snapshot_zip"])
        tt = build_timetable(read_feed(zip_path), cfg)
        try:
            write_processed(tt, zip_path.name, cfg)
        except OSError:
            # Read-only file system: use the in-memory timetable as built.
            tt.trips = tt.trips.assign(feed=zip_path.name)
            return tt
        return load_processed(cfg)  # re-read so dtypes match a normal run exactly


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="path to config.yaml")
    parser.add_argument("--download", action="store_true", help="fetch today's feed instead of the snapshot")
    parser.add_argument("--feed", help="path to a GTFS zip (overrides snapshot)")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    if args.download:
        zip_path = download_feed(cfg["data"]["gtfs_static_url"], project_path(cfg["data"]["raw_dir"]),
                                 int(cfg["data"]["http_timeout_s"]))
    else:
        zip_path = Path(args.feed) if args.feed else project_path(cfg["data"]["snapshot_zip"])

    tt = build_timetable(read_feed(zip_path), cfg)
    out = write_processed(tt, zip_path.name, cfg)

    print(f"Feed: {zip_path.name}")
    print(f"Stations: {len(tt.stations)}  Trips: {len(tt.trips)}  Stop rows: {len(tt.stop_times)}")
    print(f"Data quality notes: {len(tt.quality)}")
    if len(tt.quality):
        print(tt.quality.groupby("issue").size().to_string())
    print(f"Written to {out}")


if __name__ == "__main__":
    main()
