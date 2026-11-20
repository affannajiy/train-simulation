"""Verification tests for the benchmark-based recovery model and the punctuality profile."""

from __future__ import annotations

import pandas as pd
import pytest

from ets_sim import metrics
from ets_sim.model import SimParams, Supplement, simulate, total_slack_s
from tests.test_model import NO_DELAY, TOPO, trip


def test_supplement_inverts_uic_formula():
    s = Supplement(4.0, 1.0)
    minimum = 1000.0
    scheduled = minimum * 1.04 + 60 * 200 / 100  # 200 km
    assert s.minimum_s(scheduled, 200) == pytest.approx(minimum)


def test_supplement_limits_recovery():
    # A->B 20 km scheduled 900 s. Line speed 120 km/h allows 300 s of slack; a 7% supplement
    # allows only 900 - 900/1.07 = 58.9 s.
    t = trip("1", ("A", 0, 0), ("B", 900, 900))
    p = SimParams(p_origin=0.0, p_stop=0.0, line_speed_kmh=120.0, running_supplement_pct=7.0)
    res = simulate(TOPO, [t], p, forced_delays={("1", 0): 420.0})
    arr = res.events.query("kind == 'arr'")["delay_s"].iloc[0]
    assert arr == pytest.approx(420.0 - (900 - 900 / 1.07))


def test_supplement_never_faster_than_line_speed():
    # Scheduled 610 s for 20 km at 120 km/h (minimum 600 s). 7% would give 570 s, below line speed.
    t = trip("1", ("A", 0, 0), ("B", 610, 610))
    p = SimParams(p_origin=0.0, p_stop=0.0, line_speed_kmh=120.0, running_supplement_pct=7.0)
    slack, _ = total_slack_s([t], TOPO, p.line_speed_kmh, p.supplement)
    assert slack == pytest.approx(10.0)


def test_buffer_is_recoverable_under_supplement_model():
    # A 120 s buffer must add 120 s of slack, not raise the minimum running time with it.
    from ets_sim.train import apply_buffer
    t = trip("1", ("A", 0, 0), ("B", 900, 900))
    p = SimParams(p_origin=0.0, p_stop=0.0, line_speed_kmh=120.0, running_supplement_pct=7.0)
    base, _ = total_slack_s([t], TOPO, p.line_speed_kmh, p.supplement)
    buffered, _ = total_slack_s([apply_buffer(t, 120)], TOPO, p.line_speed_kmh, p.supplement)
    assert buffered - base == pytest.approx(120.0)


def test_line_speed_mode_unchanged():
    t = trip("1", ("A", 0, 0), ("B", 900, 900))
    res = simulate(TOPO, [t], NO_DELAY, forced_delays={("1", 0): 420.0})
    assert res.events.query("kind == 'arr'")["delay_s"].iloc[0] == pytest.approx(120.0)


def test_punctuality_profile_thresholds():
    ev = pd.DataFrame({"kind": ["arr"] * 4, "is_destination": [True, True, False, False],
                       "delay_s": [0.0, 240.0, 120.0, 900.0]})
    out = metrics.punctuality_profile(ev, [3, 5])
    assert out["on_time_dest_3min_pct"] == pytest.approx(50.0)
    assert out["on_time_dest_5min_pct"] == pytest.approx(100.0)
    assert out["on_time_all_3min_pct"] == pytest.approx(50.0)
    assert out["on_time_all_5min_pct"] == pytest.approx(75.0)
