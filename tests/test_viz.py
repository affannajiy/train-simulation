"""Tests for the dashboard chart builders, the live map sizing and the section tooltip."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ets_sim import live_map, style, viz
from tests.test_model import TOPO


def arrivals(rows):
    """rows: (trip_id, station, sched_s, delay_s, is_destination, rep)."""
    df = pd.DataFrame(rows, columns=["trip_id", "station", "sched_s", "delay_s", "is_destination", "rep"])
    return df.assign(kind="arr", actual_s=df["sched_s"] + df["delay_s"])


EV = arrivals([
    ("1", "B", 3600, 0, False, 0), ("1", "C", 4000, 120, True, 0),
    ("2", "B", 3700, 60, False, 0), ("2", "C", 4100, 600, True, 0),
    ("1", "B", 3600, 30, False, 1), ("1", "C", 4000, 240, True, 1),
    ("2", "B", 3700, 90, False, 1), ("2", "C", 4100, 300, True, 1),
])


def test_punctuality_curve_is_the_empirical_cdf():
    fig = viz.punctuality_curve(EV, late_min=5)
    all_stops, dest = fig.data
    x = np.asarray(all_stops.x)
    at = lambda tr, v: float(np.asarray(tr.y)[np.argmin(abs(x - v))])
    # All stops: delays 0, 0.5, 1, 1.5, 2, 4, 5, 10 min.
    assert at(all_stops, 0) == pytest.approx(12.5)
    assert at(all_stops, 2) == pytest.approx(62.5)
    assert at(all_stops, 5) == pytest.approx(87.5)  # "at most" t, same rule as metrics.on_time
    assert at(all_stops, 30) == pytest.approx(100.0)
    # Destinations: 2, 4, 5, 10 min.
    assert at(dest, 4.5) == pytest.approx(50.0)


def test_heatmap_orders_stations_by_line_and_blanks_thin_cells():
    fig = viz.station_hour_heatmap(EV, TOPO, min_arrivals=3)
    hm = fig.data[0]
    assert list(hm.y) == ["B", "C"]
    assert list(hm.x) == ["01:00"]
    z = np.asarray(hm.z, dtype=float)
    assert z[0, 0] == pytest.approx((0 + 60 + 30 + 90) / 4 / 60)
    assert z[1, 0] == pytest.approx((120 + 600 + 240 + 300) / 4 / 60)
    assert np.isnan(np.asarray(viz.station_hour_heatmap(EV, TOPO, min_arrivals=5).data[0].z, dtype=float)).all()


def test_heatmap_labels_hours_past_midnight():
    ev = arrivals([("1", "B", 25 * 3600, 0, True, 0)] * 3)
    assert list(viz.station_hour_heatmap(ev, TOPO).data[0].x) == ["01:00 +1"]


def test_delay_buildup_means_per_replication_then_across():
    fig = viz.delay_buildup(EV, TOPO, {"1": 1, "2": 1})
    line = [t for t in fig.data if t.mode == "lines+markers"]
    assert len(line) == 1 and line[0].name == "Southbound"
    # Station C: rep 0 mean (2 + 10) / 2 = 6, rep 1 mean (4 + 5) / 2 = 4.5, overall 5.25.
    y = dict(zip(np.asarray(line[0].x), np.asarray(line[0].y)))
    assert y[40.0] == pytest.approx(5.25)


def test_sankey_conserves_minutes():
    fig = viz.cause_sankey({"primary_min": 100, "outage_min": 0, "knock_on_min": 50,
                            "timetable_conflict_min": 30, "recovered_min": 40})
    s = fig.data[0]
    labels, value = list(s.node.label), list(s.link.value)
    assert "Outage" not in labels  # zero causes are left out
    added = labels.index("Delay added")
    into = sum(v for t, v in zip(s.link.target, value) if t == added)
    out = sum(v for src, v in zip(s.link.source, value) if src == added)
    assert into == pytest.approx(180) and out == pytest.approx(180)
    assert value[-2:] == [40, 140]


def test_sankey_caps_recovery_at_delay_added():
    s = viz.cause_sankey({"primary_min": 10, "recovered_min": 25}).data[0]
    assert list(s.link.value)[-2:] == [10, 0]


def test_corridor_places_sections_at_midpoint_and_sums_directions():
    bn = pd.DataFrame({"location": ["A->B", "B->A", "C"], "location_type": ["block", "block", "platform"],
                       "knock_on_min": [1.0, 2.0, 4.0], "timetable_conflict_min": [0.5, 0.0, 1.0]})
    fig = viz.corridor_bottlenecks(bn, TOPO)
    conflict, knock = fig.data
    by_km = dict(zip(np.asarray(knock.x), np.asarray(knock.y)))
    assert by_km == {10.0: 3.0, 40.0: 4.0}
    assert list(knock.customdata) == ["A ↔ B", "C platforms"]
    assert dict(zip(np.asarray(conflict.x), np.asarray(conflict.y)))[10.0] == pytest.approx(0.5)


def test_corridor_handles_no_bottlenecks():
    empty = pd.DataFrame(columns=["location", "location_type", "knock_on_min", "timetable_conflict_min",
                                  "secondary_min", "waits"])
    assert len(viz.corridor_bottlenecks(empty, TOPO).data[0].x) == 0


def test_spaced_labels_never_overlap_and_prefer_landmarks():
    from types import SimpleNamespace as S
    st = [S(name="A", line_km=0), S(name="B", line_km=5), S(name="KL SENTRAL", line_km=8),
          S(name="C", line_km=30), S(name="D", line_km=33)]
    kept = viz.spaced_labels(st, min_gap_km=10)
    km = [s.line_km for s in kept]
    assert all(b - a >= 10 for a, b in zip(km, km[1:]))
    assert "KL SENTRAL" in [s.name for s in kept]  # the landmark wins over its close neighbours
    assert [s.name for s in kept] == ["KL SENTRAL", "C"]


def test_marey_labels_fit_the_axis():
    ev = pd.DataFrame({"trip_id": ["1"] * 3, "station": ["A", "B", "C"], "kind": ["dep", "arr", "arr"],
                       "sched_s": [0, 900, 1800], "actual_s": [0, 900, 1800], "delay_s": [0, 0, 0]})
    fig = viz.marey_figure(ev, TOPO, pd.Timestamp("2026-01-01").date(), {"1": 1})
    assert list(fig.layout.yaxis.minor.tickvals) == [0.0, 20.0, 40.0]  # every station keeps a gridline
    ticks = list(fig.layout.yaxis.tickvals)
    gap = 40 * viz.LABEL_PX / viz.MAREY_PLOT_PX
    assert all(b - a >= gap for a, b in zip(ticks, ticks[1:]))


def test_live_map_height_tracks_map_and_board():
    assert live_map.height() == live_map.HEIGHT
    assert live_map.height(300, board=True) == live_map.HEIGHT - 140
    assert live_map.height(live_map.MAP_PX, board=False) == live_map.HEIGHT - live_map.BOARD_PX


def test_live_map_html_applies_size_options():
    ev = pd.DataFrame({"trip_id": ["1", "1"], "station": ["A", "B"], "kind": ["dep", "arr"],
                       "sched_s": [0, 900], "actual_s": [0, 900], "delay_s": [0, 0]})
    out = live_map.html(ev, TOPO, {"1": 1}, 5, map_px=280, board=False)
    assert "#map{height:280px" in out and "display:none" in out
    assert "__MAPH__" not in out and "__BOARD__" not in out


def test_section_guide_is_escaped_and_split_into_paragraphs():
    out = style.section("Title", "note", guide="a <b>\n\nsecond")
    assert 'class="ets-help"' in out and "&lt;b&gt;" in out
    assert out.count("<p>") == 2
    assert 'class="ets-help"' not in style.section("Title")


def test_station_name_keeps_abbreviations():
    assert style.station_name("KL SENTRAL") == "KL Sentral"
    assert style.station_name("JB SENTRAL") == "JB Sentral"
    assert style.station_name("PULAU SEBANG/TAMPIN") == "Pulau Sebang/Tampin"
    assert style.station_name("KUALA LUMPUR") == "Kuala Lumpur"
