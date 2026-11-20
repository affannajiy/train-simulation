"""Verification tests: does the SimPy model behave correctly in controlled scenarios?"""

from __future__ import annotations

import pandas as pd
import pytest

from ets_sim.model import SimParams, simulate
from ets_sim.topology import Topology
from ets_sim.train import Stop, Trip, apply_buffer, shifted_copy


def line(*names_km, branch=None) -> Topology:
    rows = [{"station": n, "lat": 0.0, "lon": float(k), "line_km": float(k), "branch_junction": "", "branch_km": 0.0}
            for n, k in names_km]
    if branch:
        junction, name, km = branch
        rows.append({"station": name, "lat": 1.0, "lon": 0.0, "line_km": dict(names_km)[junction],
                     "branch_junction": junction, "branch_km": float(km)})
    return Topology(pd.DataFrame(rows), max_block_km=5.0)


NO_DELAY = SimParams(p_origin=0.0, p_stop=0.0, line_speed_kmh=120.0, min_dwell_s=60.0)


def trip(tid, *stops, direction=1):
    return Trip(tid, direction, tuple(Stop(s, a, d) for s, a, d in stops))


TOPO = line(("A", 0), ("B", 20), ("C", 40))


def test_zero_disruption_follows_timetable_exactly():
    t = trip("1", ("A", 0, 0), ("B", 900, 960), ("C", 1800, 1800))
    res = simulate(TOPO, [t], NO_DELAY)
    assert (res.events["delay_s"].abs() < 1e-6).all()
    assert res.increments.empty


def test_forced_delay_recovered_by_exact_slack():
    # A->B: 20 km scheduled 900 s. Minimum at 120 km/h = 600 s, so slack = 300 s.
    t = trip("1", ("A", 0, 0), ("B", 900, 900))
    res = simulate(TOPO, [t], NO_DELAY, forced_delays={("1", 0): 420.0})
    arr = res.events.query("kind == 'arr'")["delay_s"].iloc[0]
    assert arr == pytest.approx(120.0)
    inc = res.increments.groupby("cause")["amount_s"].sum()
    assert inc["primary"] == pytest.approx(420.0)
    assert inc["recovery"] == pytest.approx(-300.0)


def test_dwell_cut_to_minimum_when_late():
    # Running time exactly at minimum (no running slack); 5 min scheduled dwell at B, min dwell 1 min.
    t = trip("1", ("A", 0, 0), ("B", 600, 900), ("C", 1500, 1500))
    res = simulate(TOPO, [t], NO_DELAY, forced_delays={("1", 0): 180.0})
    ev = res.events.set_index(["station", "kind"])["delay_s"]
    assert ev[("B", "arr")] == pytest.approx(180.0)
    assert ev[("B", "dep")] == pytest.approx(0.0)  # 240 s of dwell slack absorbs 180 s
    assert ev[("C", "arr")] == pytest.approx(0.0)


def test_train_never_departs_early():
    t = trip("1", ("A", 0, 0), ("B", 900, 1200), ("C", 2100, 2100))
    res = simulate(TOPO, [t], NO_DELAY)
    dep = res.events.query("station == 'B' and kind == 'dep'")
    assert dep["actual_s"].iloc[0] >= 1200 - 1e-9


def test_knock_on_attributed_to_root_cause():
    # At 80 km/h, 40 km takes exactly the scheduled 1800 s, so there is no slack to recover.
    # L leaves 600 s late and holds the first 5 km block until 825 s; F wants it at 700 s.
    lead = trip("L", ("A", 0, 0), ("C", 1800, 1800))
    follow = trip("F", ("A", 700, 700), ("C", 2500, 2500))
    res = simulate(TOPO, [lead, follow], SimParams(p_origin=0, p_stop=0, line_speed_kmh=80.0),
                   forced_delays={("L", 0): 600.0})
    ko = res.increments.query("cause == 'knock_on'")
    assert not ko.empty
    assert set(ko["root_id"]) == {"P:L@A"}
    assert set(ko["blocking_trip_id"]) == {"L"}
    assert set(ko["trip_id"]) == {"F"}


def test_same_minute_departure_is_timetable_conflict():
    a = trip("1", ("A", 0, 0), ("C", 1800, 1800))
    b = trip("2", ("A", 0, 0), ("C", 1800, 1800))
    res = simulate(TOPO, [a, b], NO_DELAY)
    causes = set(res.increments.query("amount_s > 0")["cause"])
    assert causes == {"timetable_conflict"}


def test_block_exclusivity():
    trips = [trip(str(i), ("A", i * 60, i * 60), ("C", 1800 + i * 60, 1800 + i * 60)) for i in range(5)]
    res = simulate(TOPO, trips, SimParams(p_origin=1.0, p_stop=0.0, line_speed_kmh=120.0), seed=3,
                   record_occupancy=True)
    occ = res.occupancy[~res.occupancy["resource"].str.startswith("platform")]
    for _, g in occ.groupby("resource"):
        g = g.sort_values("t_in")
        assert (g["t_in"].to_numpy()[1:] >= g["t_out"].to_numpy()[:-1] - 1e-9).all()


def test_ledger_always_matches_delay():
    trips = [trip(str(i), ("A", i * 120, i * 120), ("B", 900 + i * 120, 960 + i * 120),
                  ("C", 1800 + i * 120, 1800 + i * 120)) for i in range(6)]
    res = simulate(TOPO, trips, SimParams(p_origin=0.8, p_stop=0.5, line_speed_kmh=120.0), seed=11)
    assert (res.events["delay_s"] - res.events["ledger_s"]).abs().max() < 1e-6


def test_same_seed_same_result_and_crn():
    trips = [trip(str(i), ("A", i * 300, i * 300), ("C", 1800 + i * 300, 1800 + i * 300)) for i in range(4)]
    p = SimParams(p_origin=0.5, p_stop=0.0, line_speed_kmh=120.0)
    r1, r2 = simulate(TOPO, trips, p, seed=5), simulate(TOPO, trips, p, seed=5)
    pd.testing.assert_frame_equal(r1.events, r2.events)
    # Common random numbers: the same train gets the same primary delay when another train is added.
    r3 = simulate(TOPO, trips + [shifted_copy(trips[0], 7200, "X")], p, seed=5)
    prim = lambda r: r.increments.query("cause == 'primary'").set_index("trip_id")["amount_s"]
    pd.testing.assert_series_equal(prim(r1), prim(r3).drop("X", errors="ignore"))


def test_branch_path_and_buffer():
    topo = line(("A", 0), ("J", 20), ("C", 40), branch=("J", "BR", 8))
    assert topo.path("BR", "C") == ("BR", "J", "C")
    t = trip("1", ("A", 0, 0), ("C", 1800, 1800))
    b = apply_buffer(t, 120)
    assert b.stops[-1].arr_s == pytest.approx(1920)
    assert b.stops[0].dep_s == 0
