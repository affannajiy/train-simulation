"""SimPy model of ETS trains on the shared fixed-block railway.

One train's lifecycle:
  1. Wait until its scheduled origin departure, apply any primary delay.
  2. For each sub-block on the way to the next stop: request it while still holding the
     current one (a train cannot leave its block until the block ahead is free), release
     the one behind, then run. A late train runs faster, down to the minimum time at line
     speed, which is how it recovers slack.
  3. At a stop: request a platform while still holding the approach block, release the
     block, dwell. A late train can cut its dwell to min_dwell. A train never departs
     before its scheduled time. A primary delay may be added at departure.
  4. Trains passing a station without stopping do not use a platform.

Every wait and recovery is attributed through events.DelayLedger. See events.py.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import simpy

from ets_sim.events import DelayLedger, EventLog, attribute_wait
from ets_sim.topology import SubBlock, Topology
from ets_sim.train import Trip


@dataclass(frozen=True)
class SimParams:
    line_speed_kmh: float = 140.0
    min_dwell_s: float = 60.0
    p_origin: float = 0.30
    origin_median_s: float = 180.0
    origin_sigma: float = 0.8
    p_stop: float = 0.05
    stop_median_s: float = 90.0
    stop_sigma: float = 0.8
    cap_s: float = 3600.0
    platforms_default: int = 2
    platform_overrides: dict = field(default_factory=dict)

    def no_disruption(self) -> "SimParams":
        """Same parameters with primary delays switched off."""
        from dataclasses import replace
        return replace(self, p_origin=0.0, p_stop=0.0)


def params_from_config(cfg: dict, **overrides) -> SimParams:
    """Build SimParams from config.yaml (minutes converted to seconds), then apply overrides."""
    pd_cfg, ops, plat = cfg["primary_delay"], cfg["operations"], cfg["platforms"]
    values = dict(
        line_speed_kmh=float(ops["line_speed_kmh"]),
        min_dwell_s=float(ops["min_dwell_min"]) * 60,
        p_origin=float(pd_cfg["p_origin"]),
        origin_median_s=float(pd_cfg["origin_median_min"]) * 60,
        origin_sigma=float(pd_cfg["origin_sigma"]),
        p_stop=float(pd_cfg["p_stop"]),
        stop_median_s=float(pd_cfg["stop_median_min"]) * 60,
        stop_sigma=float(pd_cfg["stop_sigma"]),
        cap_s=float(pd_cfg["cap_min"]) * 60,
        platforms_default=int(plat["default_per_direction"]),
        platform_overrides=dict(plat.get("overrides") or {}),
    )
    values.update(overrides)
    return SimParams(**values)


@dataclass
class SimResult:
    events: pd.DataFrame
    increments: pd.DataFrame
    occupancy: pd.DataFrame | None = None


# ------------------------------------------------------------------ plan


@dataclass(frozen=True)
class _BlockStep:
    block: SubBlock
    sched_entry_s: float
    sched_run_s: float
    min_run_s: float


@dataclass(frozen=True)
class _Leg:
    steps: tuple[_BlockStep, ...]
    label: str  # "FROM->TO" stop to stop


def plan_trip(trip: Trip, topo: Topology, line_speed_kmh: float) -> tuple[_Leg, ...]:
    """Expand a trip into the sub-blocks it occupies, with scheduled and minimum times.

    Between two stops the scheduled running time is spread over all sub-blocks in
    proportion to their length, including sections past stations the train does not
    stop at.
    """
    legs = []
    for a, b in zip(trip.stops, trip.stops[1:]):
        path = topo.path(a.station, b.station)
        blocks = [blk for x, y in zip(path, path[1:]) for blk in topo.sub_blocks(x, y)]
        total_km = sum(blk.length_km for blk in blocks)
        run_s = b.arr_s - a.dep_s
        if run_s < 0:
            raise ValueError(f"Trip {trip.trip_id}: negative running time {a.station}->{b.station}")
        steps, t = [], a.dep_s
        for blk in blocks:
            sched = run_s * blk.length_km / total_km
            steps.append(_BlockStep(blk, t, sched, blk.length_km / line_speed_kmh * 3600))
            t += sched
        legs.append(_Leg(tuple(steps), f"{a.station}->{b.station}"))
    return tuple(legs)


def total_slack_s(trips: list[Trip], topo: Topology, line_speed_kmh: float) -> tuple[float, int]:
    """Sum of recoverable running slack over all trips, and the count of sub-blocks whose
    scheduled time is below the minimum at line speed (slack clamped to 0)."""
    slack, infeasible = 0.0, 0
    for trip in trips:
        for leg in plan_trip(trip, topo, line_speed_kmh):
            for s in leg.steps:
                if s.sched_run_s < s.min_run_s:
                    infeasible += 1
                else:
                    slack += s.sched_run_s - s.min_run_s
    return slack, infeasible


# ------------------------------------------------------------------ resources


class _Tracked:
    """A SimPy resource that remembers who released it last (the train that blocked the next one)."""

    __slots__ = ("res", "last_releaser")

    def __init__(self, env: simpy.Environment, capacity: int):
        self.res = simpy.Resource(env, capacity=capacity)
        self.last_releaser: str | None = None


# ------------------------------------------------------------------ simulation


class Simulation:
    def __init__(self, topo: Topology, trips: list[Trip], params: SimParams, seed: int = 0,
                 forced_delays: dict[tuple[str, int], float] | None = None,
                 record_occupancy: bool = False):
        ids = [t.trip_id for t in trips]
        if len(ids) != len(set(ids)):
            raise ValueError("Trip ids must be unique")
        self.topo = topo
        self.trips = trips
        self.p = params
        self.seed = int(seed)
        self.forced = dict(forced_delays or {})
        self.env = simpy.Environment()
        self.log = EventLog()
        self.ledgers: dict[str, DelayLedger] = {}
        self._blocks: dict[tuple, _Tracked] = {}
        self._platforms: dict[tuple, _Tracked] = {}
        self._occupancy: list[tuple] | None = [] if record_occupancy else None
        self._plans = {t.trip_id: plan_trip(t, topo, params.line_speed_kmh) for t in trips}

    # -------------------------------------------------- public

    def run(self) -> SimResult:
        for trip in self.trips:
            self.env.process(self._train(trip))
        self.env.run()
        events, increments = self.log.frames()
        occ = None
        if self._occupancy is not None:
            occ = pd.DataFrame(self._occupancy, columns=["resource", "trip_id", "t_in", "t_out"])
        return SimResult(events, increments, occ)

    # -------------------------------------------------- helpers

    def _rng(self, trip_id: str) -> np.random.Generator:
        # One stream per train, keyed by (seed, trip_id): common random numbers across scenarios.
        return np.random.default_rng(np.random.SeedSequence([self.seed, zlib.crc32(trip_id.encode())]))

    def _primary(self, rng, trip_id: str, stop_index: int, origin: bool) -> float:
        # Always draw both numbers so the stream stays aligned whatever p is.
        u, z = rng.random(), rng.standard_normal()
        if (trip_id, stop_index) in self.forced:
            return float(self.forced[(trip_id, stop_index)])
        p = self.p.p_origin if origin else self.p.p_stop
        if u >= p:
            return 0.0
        median = self.p.origin_median_s if origin else self.p.stop_median_s
        sigma = self.p.origin_sigma if origin else self.p.stop_sigma
        return min(self.p.cap_s, median * math.exp(sigma * z))

    def _block(self, blk: SubBlock) -> _Tracked:
        res = self._blocks.get(blk.key)
        if res is None:
            res = self._blocks[blk.key] = _Tracked(self.env, 1)
        return res

    def _platform(self, station: str, direction: int) -> _Tracked:
        key = (station, direction)
        res = self._platforms.get(key)
        if res is None:
            cap = int(self.p.platform_overrides.get(station, self.p.platforms_default))
            res = self._platforms[key] = _Tracked(self.env, cap)
        return res

    def _acquire(self, res: _Tracked, trip_id: str, ledger: DelayLedger, location: str, ltype: str):
        req = res.res.request()
        t0 = self.env.now
        yield req
        wait = self.env.now - t0
        if wait > 0:
            blocker = res.last_releaser
            attribute_wait(self.log, trip_id, ledger, blocker or "", self.ledgers.get(blocker),
                           wait, self.env.now, location, ltype)
        return req

    def _release(self, held, trip_id: str) -> None:
        res, req, name, t_in = held
        res.last_releaser = trip_id
        res.res.release(req)
        if self._occupancy is not None:
            self._occupancy.append((name, trip_id, t_in, self.env.now))

    def _add_primary(self, trip_id: str, ledger: DelayLedger, station: str, seconds: float) -> None:
        root = f"P:{trip_id}@{station}"
        ledger.add(root, seconds)
        self.log.increment(trip_id, self.env.now, station, "station", "primary", seconds, root)

    def _flush_recovery(self, trip_id: str, removed: dict[str, float], location: str, ltype: str) -> None:
        for root, amount in removed.items():
            self.log.increment(trip_id, self.env.now, location, ltype, "recovery", -amount, root)

    # -------------------------------------------------- train process

    def _train(self, trip: Trip):
        env, tid, log = self.env, trip.trip_id, self.log
        rng = self._rng(tid)
        ledger = self.ledgers[tid] = DelayLedger()
        legs = self._plans[tid]
        last = len(trip.stops) - 1

        yield env.timeout(trip.stops[0].dep_s)
        extra = self._primary(rng, tid, 0, origin=True)
        if extra > 0:
            self._add_primary(tid, ledger, trip.origin, extra)
            yield env.timeout(extra)

        held = None
        for i, leg in enumerate(legs):
            removed: dict[str, float] = {}
            for j, step in enumerate(leg.steps):
                blk = step.block
                res = self._block(blk)
                req = yield from self._acquire(res, tid, ledger, f"{blk.section[0]}->{blk.section[1]}", "block")
                if held:
                    self._release(held, tid)
                held = (res, req, f"{blk.section[0]}->{blk.section[1]}#{blk.index}", env.now)

                if j == 0:
                    stop = trip.stops[i]
                    log.event(tid, stop.station, "dep", i, stop.dep_s, env.now, ledger.total, True, False)
                elif blk.index == 0:
                    log.event(tid, blk.section[0], "pass", None, step.sched_entry_s, env.now, ledger.total,
                              False, False)

                delay = env.now - step.sched_entry_s
                slack = max(0.0, step.sched_run_s - step.min_run_s)
                rec = min(max(delay, 0.0), slack)
                if rec > 0:
                    for r, a in ledger.recover(rec).items():
                        removed[r] = removed.get(r, 0.0) + a
                yield env.timeout(step.sched_run_s - rec)
            self._flush_recovery(tid, removed, leg.label, "run")

            # Arrive at the next stop: get a platform while still holding the approach block.
            stop = trip.stops[i + 1]
            plat = self._platform(stop.station, trip.direction_id)
            preq = yield from self._acquire(plat, tid, ledger, stop.station, "platform")
            self._release(held, tid)
            held = (plat, preq, f"platform:{stop.station}:{trip.direction_id}", env.now)
            is_dest = i + 1 == last
            log.event(tid, stop.station, "arr", i + 1, stop.arr_s, env.now, ledger.total, True, is_dest)
            if is_dest:
                self._release(held, tid)
                return

            # Dwell, shortened if late, never departing early.
            sched_dwell = stop.dep_s - stop.arr_s
            min_dwell = min(self.p.min_dwell_s, sched_dwell)
            depart = max(stop.dep_s, env.now + min_dwell)
            rec = (env.now - stop.arr_s) - (depart - stop.dep_s)
            if rec > 0:
                self._flush_recovery(tid, ledger.recover(rec), stop.station, "dwell")
            extra = self._primary(rng, tid, i + 1, origin=False)
            if extra > 0:
                self._add_primary(tid, ledger, stop.station, extra)
                depart += extra
            yield env.timeout(depart - env.now)


def simulate(topo: Topology, trips: list[Trip], params: SimParams, seed: int = 0, **kwargs) -> SimResult:
    """Convenience wrapper: build and run one replication."""
    return Simulation(topo, trips, params, seed, **kwargs).run()
