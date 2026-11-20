"""Verification tests for section outages and the incident replay helpers."""

from __future__ import annotations

import pytest

from ets_sim import metrics
from ets_sim.model import SectionOutage, SimParams, simulate
from ets_sim.replay import hhmm_to_s, s_to_hhmm
from tests.test_model import TOPO, trip

# At 80 km/h, 20 km takes exactly the scheduled 900 s, so no running slack: delays stay put.
TIGHT = SimParams(p_origin=0.0, p_stop=0.0, line_speed_kmh=80.0, min_dwell_s=60.0)


def outage(start, dur, a="B", b="C", both=True, name="x"):
    return SectionOutage(name, a, b, start, dur, both)


def test_train_waits_exactly_until_outage_ends():
    # Train leaves B at 900 s; B->C closed from 600 s to 1500 s, so it leaves B 600 s late.
    t = trip("1", ("A", 0, 0), ("B", 900, 900), ("C", 1800, 1800))
    res = simulate(TOPO, [t], TIGHT, outages=[outage(600, 900)])
    ev = res.events.set_index(["station", "kind"])["delay_s"]
    assert ev[("C", "arr")] == pytest.approx(600.0)
    inc = res.increments
    assert set(inc["cause"]) == {"outage"}
    assert set(inc["root_id"]) == {"O:x"}
    assert inc["amount_s"].sum() == pytest.approx(600.0)


def test_outage_outside_train_time_has_no_effect():
    t = trip("1", ("A", 0, 0), ("B", 900, 900), ("C", 1800, 1800))
    res = simulate(TOPO, [t], TIGHT, outages=[outage(3600, 600)])
    assert (res.events["delay_s"].abs() < 1e-6).all()
    assert res.increments.empty


def test_train_inside_section_stops_at_next_block():
    # Train enters B->C (four 5 km blocks, 225 s each) at 900 s; outage starts at 1000 s.
    # It holds block 0 until 1125 s, block 1 is closed, so it waits until 1300 s.
    t = trip("1", ("A", 0, 0), ("B", 900, 900), ("C", 1800, 1800))
    res = simulate(TOPO, [t], TIGHT, outages=[outage(1000, 300)])
    arr = res.events.query("station == 'C' and kind == 'arr'")["delay_s"].iloc[0]
    assert arr == pytest.approx(1300 - 1125)


def test_follower_inherits_outage_root_as_knock_on():
    lead = trip("L", ("A", 0, 0), ("C", 1800, 1800))
    follow = trip("F", ("A", 400, 400), ("C", 2200, 2200))
    res = simulate(TOPO, [lead, follow], TIGHT, outages=[outage(0, 1200, a="B", b="C")])
    f = res.increments.query("trip_id == 'F' and amount_s > 0")
    assert set(f["root_id"]) == {"O:x"}
    assert "knock_on" in set(f["cause"])
    reach = metrics.incident_reach(res.events, res.increments, "O:x")
    assert set(reach["trip_id"]) == {"L", "F"}


def test_one_direction_outage_leaves_other_track_open():
    north = trip("N", ("C", 0, 0), ("A", 1800, 1800), direction=0)
    res = simulate(TOPO, [north], TIGHT, outages=[outage(0, 3600, a="B", b="C", both=False)])
    assert res.increments.empty
    res2 = simulate(TOPO, [north], TIGHT, outages=[outage(0, 3600, a="B", b="C", both=True)])
    assert res2.increments["amount_s"].sum() == pytest.approx(3600.0)


def test_ledger_matches_delay_with_outage_and_noise():
    trips = [trip(str(i), ("A", i * 120, i * 120), ("B", 900 + i * 120, 960 + i * 120),
                  ("C", 1800 + i * 120, 1800 + i * 120)) for i in range(6)]
    p = SimParams(p_origin=0.8, p_stop=0.5, line_speed_kmh=120.0)
    res = simulate(TOPO, trips, p, seed=11, outages=[outage(800, 700)])
    assert (res.events["delay_s"] - res.events["ledger_s"]).abs().max() < 1e-6


def test_outage_keeps_common_random_numbers():
    trips = [trip(str(i), ("A", i * 300, i * 300), ("C", 1800 + i * 300, 1800 + i * 300)) for i in range(4)]
    p = SimParams(p_origin=0.5, p_stop=0.0, line_speed_kmh=120.0)
    prim = lambda r: r.increments.query("cause == 'primary'").set_index("trip_id")["amount_s"].sort_index()
    a = simulate(TOPO, trips, p, seed=5)
    b = simulate(TOPO, trips, p, seed=5, outages=[outage(500, 900)])
    assert prim(a).to_dict() == pytest.approx(prim(b).to_dict())


def test_bad_outage_is_rejected():
    t = trip("1", ("A", 0, 0), ("C", 1800, 1800))
    with pytest.raises(ValueError):
        simulate(TOPO, [t], TIGHT, outages=[outage(0, 60, a="A", b="Z")])
    with pytest.raises(ValueError):
        simulate(TOPO, [t], TIGHT, outages=[outage(0, 0)])
    with pytest.raises(ValueError):
        simulate(TOPO, [t], TIGHT, outages=[outage(0, 60), outage(100, 60)])


def test_time_helpers_round_trip():
    assert hhmm_to_s("10:15") == 36900.0
    assert s_to_hhmm(36900.0) == "10:15"
    assert s_to_hhmm(hhmm_to_s("25:05")) == "25:05"
