"""Checks on the committed OSM track geometry against the GTFS stations it must match."""

from __future__ import annotations

import math

import pytest

from ets_sim.config import load_config, project_path
from ets_sim.loader import build_timetable, read_feed
from ets_sim.track import Track


@pytest.fixture(scope="module")
def data():
    cfg = load_config()
    tt = build_timetable(read_feed(project_path(cfg["data"]["snapshot_zip"])), cfg)
    return tt.stations.set_index("station"), Track.load(project_path(cfg["data"]["track_geojson"]))


def chord_m(a, b) -> float:
    lat = math.radians((a.lat + b.lat) / 2)
    return math.hypot(math.radians(b.lon - a.lon) * math.cos(lat), math.radians(b.lat - a.lat)) * 6371008.8


def test_every_station_sits_on_the_track(data):
    stations, track = data
    for name in stations.index:
        assert track.has(name), name
        for pos in track.positions(name).values():
            assert pos.snap_m <= 200, f"{name} is {pos.snap_m:.0f} m from the nearest track"


def test_main_line_chainage_follows_line_km(data):
    stations, track = data
    main = stations[stations["branch_junction"].isna() | (stations["branch_junction"] == "")]
    ch = [track.positions(s)["main"].chainage_m for s in main.sort_values("line_km").index]
    assert all(b > a for a, b in zip(ch, ch[1:]))


def test_no_section_takes_a_detour(data):
    # A shortest path that leaves the line (a gap in OSM, the wrong track of a double line) shows up
    # as a section far longer than the straight distance between its stations.
    stations, track = data
    main = stations[stations["branch_junction"].isna() | (stations["branch_junction"] == "")].sort_values("line_km")
    for a, b in zip(main.index, main.index[1:]):
        line, ca, cb = track.section(a, b)
        ratio = (cb - ca) / chord_m(stations.loc[a], stations.loc[b])
        assert 0.95 <= ratio <= 1.6, f"{a} to {b}: track is {ratio:.2f} x the straight distance"


def test_total_length_matches_gtfs(data):
    stations, track = data
    osm_km = track.positions("JB SENTRAL")["main"].chainage_m / 1000
    assert osm_km == pytest.approx(stations.loc["JB SENTRAL", "line_km"], rel=0.03)


def test_branch_section_uses_the_branch_line(data):
    _, track = data
    line, ca, cb = track.section("BUKIT MERTAJAM", "BUTTERWORTH")
    assert line.startswith("branch:") and ca == 0 and cb > 5000
    line, ca, cb = track.section("BUTTERWORTH", "BUKIT MERTAJAM")
    assert line.startswith("branch:") and cb == 0
