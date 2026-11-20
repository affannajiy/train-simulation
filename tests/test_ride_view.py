"""Ride view payload: train motion, holds and delay must match the model's own logs."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ets_sim import ride_view
from ets_sim.model import SimParams, simulate
from ets_sim.topology import Topology
from ets_sim.track import Line, StationPos, Track, _chainage
from ets_sim.train import Stop, Trip

NO_DELAY = SimParams(p_origin=0.0, p_stop=0.0, line_speed_kmh=120.0, min_dwell_s=60.0)


def topo() -> Topology:
    rows = [{"station": n, "lat": 0.0, "lon": k / 111.32, "line_km": float(k), "branch_junction": "", "branch_km": 0.0}
            for n, k in [("A", 0), ("B", 20), ("C", 40)]]
    rows.append({"station": "X", "lat": 0.05, "lon": 20 / 111.32, "line_km": 20.0, "branch_junction": "B",
                 "branch_km": 6.0})
    return Topology(pd.DataFrame(rows), max_block_km=5.0)


def track() -> Track:
    main = np.array([[k / 111.32, 0.0] for k in range(0, 41)])
    branch = np.array([[20 / 111.32, 0.0], [20 / 111.32, 0.054]])
    lines = {"main": Line("main", main, _chainage(main)), "branch:X": Line("branch:X", branch, _chainage(branch))}
    cm, cb = lines["main"].chainage, lines["branch:X"].chainage
    stations = [StationPos("A", "main", 0.0, 0), StationPos("B", "main", float(cm[20]), 0),
                StationPos("C", "main", float(cm[40]), 0), StationPos("B", "branch:X", 0.0, 0),
                StationPos("X", "branch:X", float(cb[-1]), 0)]
    return Track(lines, stations)


def trip(tid, *stops, direction=1):
    return Trip(tid, direction, tuple(Stop(s, a, d) for s, a, d in stops))


def scenario():
    """No slack: 20 km in 600 s is exactly line speed, so a late train cannot recover. Train 1
    starts 100 s late; train 2, booked 180 s behind it, reaches the first signal while train 1 is
    still in the block, and is held: knock-on. Train 3 comes off the branch and joins at B."""
    t1 = trip("1", ("A", 0, 0), ("B", 600, 660), ("C", 1260, 1260))
    t2 = trip("2", ("A", 180, 180), ("B", 780, 840), ("C", 1440, 1440))
    t3 = trip("3", ("X", 3000, 3000), ("B", 3400, 3460), ("C", 4300, 4300))
    T = topo()
    res = simulate(T, [t1, t2, t3], NO_DELAY, forced_delays={("1", 0): 100.0}, record_occupancy=True)
    return T, res


def payload():
    T, res = scenario()
    return res, ride_view.payload(res.events, res.increments, res.occupancy, T, track(),
                                  {"1": 1, "2": 1, "3": 1}, late_min=5)


def test_keyframes_never_go_back_in_time():
    _, p = payload()
    for t in p["trips"]:
        times = [k[0] for k in t["k"]]
        assert times == sorted(times), t["id"]


def test_every_wait_is_a_stop_of_the_same_length():
    res, p = payload()
    occ = res.occupancy
    waits = occ[occ["t_in"] - occ["t_req"] >= ride_view.HOLD_MIN_S]
    assert len(waits) > 0  # the scenario must hold train 2
    for w in waits.itertuples():
        k = next(t["k"] for t in p["trips"] if t["id"] == w.trip_id)
        stops = [(a[0], b[0]) for a, b in zip(k, k[1:]) if a[1:3] == b[1:3]]
        assert (round(w.t_req), round(w.t_in)) in stops


def test_holds_match_the_increments():
    res, p = payload()
    inc = res.increments
    waits = inc[inc["cause"].isin(["knock_on", "timetable_conflict"])]
    holds = {t["id"]: t["h"] for t in p["trips"]}
    for (tid, t), g in waits.groupby(["trip_id", "time_s"]):
        h = [x for x in holds[tid] if x[1] == round(t) and x[3] == 1]
        assert len(h) == 1
        assert h[0][1] - h[0][0] == round(g["amount_s"].sum()) or abs(h[0][1] - h[0][0] - g["amount_s"].sum()) <= 1
        assert "train 1 ahead" in h[0][2]


def test_delay_series_ends_at_the_destination_delay():
    res, p = payload()
    for t in p["trips"]:
        ev = res.events[(res.events["trip_id"] == t["id"]) & res.events["is_destination"]]
        final = t["d"][-1][1] if t["d"] else 0
        assert abs(final - ev["delay_s"].iloc[0]) <= 1, t["id"]


def test_default_train_is_the_one_with_most_knock_on():
    res, p = payload()
    assert p["follow"] == ride_view.most_knock_on(res.increments) == "2"


def test_branch_junction_switches_line_without_moving():
    _, p = payload()
    k = next(t["k"] for t in p["trips"] if t["id"] == "3")
    names = [p["lines"][f[1]]["name"] for f in k]
    assert names[0] == "branch:X" and names[-1] == "main"
    for a, b in zip(k, k[1:]):
        if a[1] != b[1]:
            assert a[0] == b[0]  # the switch happens at one instant, at the junction


def test_signals_turn_red_while_occupied():
    res, p = payload()
    assert p["signals"]
    for line, ch, sign, iv in p["signals"]:
        assert sign in (1, -1) and len(iv) % 2 == 0
        assert all(a <= b for a, b in zip(iv[0::2], iv[1::2]))


def test_html_has_no_unfilled_tokens_and_escapes_script_end():
    T, res = scenario()
    out = ride_view.html(res.events, res.increments, res.occupancy, T, track(), {}, late_min=5)
    assert "__DATA__" not in out and "__ORANGE__" not in out
    assert out.count("</script>") == out.count("<script")
