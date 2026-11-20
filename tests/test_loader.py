"""Loader tests against the pinned GTFS snapshot."""

from __future__ import annotations

import datetime as dt

import pytest

from ets_sim.config import load_config, project_path
from ets_sim.loader import active_service_ids, build_timetable, gtfs_time_to_seconds, read_feed


@pytest.fixture(scope="module")
def built():
    cfg = load_config()
    feed = read_feed(project_path(cfg["data"]["snapshot_zip"]))
    return feed, build_timetable(feed, cfg)


def test_time_parsing_past_midnight():
    assert gtfs_time_to_seconds("25:30:00") == 91800
    assert gtfs_time_to_seconds("00:00:05") == 5
    with pytest.raises(ValueError):
        gtfs_time_to_seconds("25:30")


def test_calendar(built):
    feed, _ = built
    assert "ets" in active_service_ids(feed, dt.date(2026, 11, 20))
    assert "ets" not in active_service_ids(feed, dt.date(2027, 1, 1))


def test_line_km_runs_padang_besar_to_jb(built):
    _, tt = built
    km = dict(zip(tt.stations["station"], tt.stations["line_km"]))
    assert km["PADANG BESAR"] == 0
    assert km["JB SENTRAL"] == pytest.approx(902.5, abs=1.0)
    assert km["KL SENTRAL"] < km["SEREMBAN"] < km["GEMAS"]


def test_cleaning_rules(built):
    _, tt = built
    issues = tt.quality.groupby("issue")["trip_id"].apply(list).to_dict()
    assert "9624" in issues["exact_duplicate_dropped"]
    assert "9624" not in set(tt.trips["trip_id"])
    assert "HAT YAI" not in set(tt.stop_times["station"])
    assert tt.trips.set_index("trip_id").loc["1004", "international"]
    butterworth = tt.stations.set_index("station").loc["BUTTERWORTH"]
    assert butterworth["branch_junction"] == "BUKIT MERTAJAM"
    assert 5 < butterworth["branch_km"] < 15


def test_times_monotonic(built):
    _, tt = built
    for _, g in tt.stop_times.groupby("trip_id"):
        assert (g["dep_s"].to_numpy() >= g["arr_s"].to_numpy()).all()
        assert (g["arr_s"].to_numpy()[1:] >= g["dep_s"].to_numpy()[:-1]).all()


def test_real_timetable_without_disruption_only_has_timetable_conflicts(built):
    """On the real network, every minute of delay in a zero-disruption run traces to a timetable conflict."""
    from ets_sim.model import SimParams, simulate
    from ets_sim.topology import Topology
    from ets_sim.train import trips_from_frames

    _, tt = built
    res = simulate(Topology(tt.stations, 5.0), trips_from_frames(tt.trips, tt.stop_times),
                   SimParams(p_origin=0.0, p_stop=0.0))
    added = res.increments[res.increments["amount_s"] > 0]
    assert added["root_id"].str.startswith("C:").all()
    assert (res.events["delay_s"] - res.events["ledger_s"]).abs().max() < 1e-6
