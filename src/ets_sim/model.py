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

Section outages (SectionOutage) model incidents such as an overhead line or signalling
failure: from start_s, the outage takes every sub-block of the section ahead of any waiting
train and holds it until the end. A train already inside the section stops at the next
sub-block. A train waiting for a block the outage held records the wait as cause `outage`.

Every wait and recovery is attributed through events.DelayLedger. See events.py.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import simpy

from ets_sim.events import DelayLedger, EventLog, attribute_outage, attribute_wait
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
    # Recovery model. None: minimum running time is distance at line speed (idealised).
    # A number: minimum time is the scheduled time with a benchmark running time supplement
    # removed (see Supplement), never faster than line speed.
    running_supplement_pct: float | None = None
    supplement_min_per_100km: float = 0.0

    @property
    def supplement(self) -> "Supplement | None":
        if self.running_supplement_pct is None:
            return None
        return Supplement(self.running_supplement_pct, self.supplement_min_per_100km)

    def no_disruption(self) -> "SimParams":
        """Same parameters with primary delays switched off."""
        from dataclasses import replace
        return replace(self, p_origin=0.0, p_stop=0.0)


@dataclass(frozen=True)
class Supplement:
    """A running time supplement in the UIC 451-1 form: scheduled = minimum * (1 + pct/100)
    plus per_100km minutes for every 100 km. The model inverts it to get the minimum."""

    pct: float
    per_100km_min: float = 0.0

    def minimum_s(self, scheduled_s: float, km: float) -> float:
        return (scheduled_s - self.per_100km_min * 60 * km / 100) / (1 + self.pct / 100)


def params_from_config(cfg: dict, **overrides) -> SimParams:
    """Build SimParams from config.yaml (minutes converted to seconds), then apply overrides."""
    pd_cfg, ops, plat = cfg["primary_delay"], cfg["operations"], cfg["platforms"]
    model = ops.get("recovery_model", "line_speed")
    if model not in ("line_speed", "supplement"):
        raise ValueError(f"operations.recovery_model must be line_speed or supplement, not {model!r}")
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
        running_supplement_pct=float(ops["running_supplement_pct"]) if model == "supplement" else None,
        supplement_min_per_100km=float(ops.get("supplement_min_per_100km", 0.0)),
    )
    values.update(overrides)
    return SimParams(**values)


@dataclass(frozen=True)
class SectionOutage:
    """No train may enter the track between two stations from start_s to start_s + duration_s.

    The stations do not have to be adjacent: every section on the path between them is
    closed. both_directions=False closes only the from_station -> to_station track.
    """

    name: str
    from_station: str
    to_station: str
    start_s: float
    duration_s: float
    both_directions: bool = True

    @property
    def root_id(self) -> str:
        return f"O:{self.name}"


@dataclass
class SimResult:
    events: pd.DataFrame
    increments: pd.DataFrame
    # One row per resource use: t_req when the train asked for it (reached the signal),
    # t_in when it got it, t_out when it let go. Only with record_occupancy=True.
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


def plan_trip(trip: Trip, topo: Topology, line_speed_kmh: float,
              supplement: Supplement | None = None) -> tuple[_Leg, ...]:
    """Expand a trip into the sub-blocks it occupies, with scheduled and minimum times.

    Between two stops the scheduled running time is spread over all sub-blocks in
    proportion to their length, including sections past stations the train does not
    stop at. The minimum time is distance at line speed, or with a supplement the
    scheduled time with that supplement removed, whichever is longer.
    """
    legs = []
    base_runs = trip.base_run_s or trip.leg_run_s()
    for a, b, base_run_s in zip(trip.stops, trip.stops[1:], base_runs):
        path = topo.path(a.station, b.station)
        blocks = [blk for x, y in zip(path, path[1:]) for blk in topo.sub_blocks(x, y)]
        total_km = sum(blk.length_km for blk in blocks)
        run_s = b.arr_s - a.dep_s
        if run_s < 0:
            raise ValueError(f"Trip {trip.trip_id}: negative running time {a.station}->{b.station}")
        leg_min_s = total_km / line_speed_kmh * 3600
        if supplement is not None:
            # From the published running time, so an added buffer stays recoverable slack.
            leg_min_s = max(leg_min_s, supplement.minimum_s(base_run_s, total_km))
        steps, t = [], a.dep_s
        for blk in blocks:
            share = blk.length_km / total_km
            steps.append(_BlockStep(blk, t, run_s * share, leg_min_s * share))
            t += run_s * share
        legs.append(_Leg(tuple(steps), f"{a.station}->{b.station}"))
    return tuple(legs)


def total_slack_s(trips: list[Trip], topo: Topology, line_speed_kmh: float,
                  supplement: Supplement | None = None) -> tuple[float, int]:
    """Sum of recoverable running slack over all trips, and the count of sub-blocks whose
    scheduled time is below the minimum (slack clamped to 0)."""
    slack, infeasible = 0.0, 0
    for trip in trips:
        for leg in plan_trip(trip, topo, line_speed_kmh, supplement):
            for s in leg.steps:
                if s.sched_run_s < s.min_run_s:
                    infeasible += 1
                else:
                    slack += s.sched_run_s - s.min_run_s
    return slack, infeasible


# ------------------------------------------------------------------ resources


class _Tracked:
    """A SimPy resource that remembers who released it last (the train that blocked the next one).

    A priority resource so a section outage can go ahead of trains already queuing. Trains all
    use the default priority, so among trains the order stays first come, first served.
    """

    __slots__ = ("res", "last_releaser")

    def __init__(self, env: simpy.Environment, capacity: int):
        self.res = simpy.PriorityResource(env, capacity=capacity)
        self.last_releaser: str | None = None


# ------------------------------------------------------------------ simulation


class Simulation:
    def __init__(self, topo: Topology, trips: list[Trip], params: SimParams, seed: int = 0,
                 forced_delays: dict[tuple[str, int], float] | None = None,
                 record_occupancy: bool = False,
                 outages: list[SectionOutage] | None = None):
        ids = [t.trip_id for t in trips]
        if len(ids) != len(set(ids)):
            raise ValueError("Trip ids must be unique")
        self.outages = list(outages or [])
        self._outage_blocks = {o.root_id: _outage_blocks(o, topo) for o in self.outages}
        if len(self._outage_blocks) != len(self.outages):
            raise ValueError("Outage names must be unique")
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
        self._plans = {t.trip_id: plan_trip(t, topo, params.line_speed_kmh, params.supplement) for t in trips}

    # -------------------------------------------------- public

    def run(self) -> SimResult:
        # Outage processes start first so that at the same instant they reach a block before a train.
        for outage in self.outages:
            self.env.process(self._outage(outage))
        for trip in self.trips:
            self.env.process(self._train(trip))
        self.env.run()
        events, increments = self.log.frames()
        occ = None
        if self._occupancy is not None:
            occ = pd.DataFrame(self._occupancy, columns=["resource", "trip_id", "t_req", "t_in", "t_out"])
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
            if blocker in self._outage_blocks:
                attribute_outage(self.log, trip_id, ledger, blocker, wait, self.env.now, location, ltype)
            else:
                attribute_wait(self.log, trip_id, ledger, blocker or "", self.ledgers.get(blocker),
                               wait, self.env.now, location, ltype)
        return req, t0

    def _outage(self, outage: SectionOutage):
        """Take every sub-block of the closed section, ahead of queuing trains, until the end."""
        yield self.env.timeout(outage.start_s)
        held = [(res, res.res.request(priority=-1))
                for res in (self._block(blk) for blk in self._outage_blocks[outage.root_id])]
        yield self.env.timeout(outage.duration_s)
        for res, req in held:
            if req.triggered:
                res.last_releaser = outage.root_id
                res.res.release(req)
            else:
                req.cancel()  # a train never left this block during the outage

    def _release(self, held, trip_id: str) -> None:
        res, req, name, t_req, t_in = held
        res.last_releaser = trip_id
        res.res.release(req)
        if self._occupancy is not None:
            self._occupancy.append((name, trip_id, t_req, t_in, self.env.now))

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
                req, t_req = yield from self._acquire(res, tid, ledger, f"{blk.section[0]}->{blk.section[1]}",
                                                      "block")
                if held:
                    self._release(held, tid)
                held = (res, req, f"{blk.section[0]}->{blk.section[1]}#{blk.index}", t_req, env.now)

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
            preq, t_req = yield from self._acquire(plat, tid, ledger, stop.station, "platform")
            self._release(held, tid)
            held = (plat, preq, f"platform:{stop.station}:{trip.direction_id}", t_req, env.now)
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


def _outage_blocks(outage: SectionOutage, topo: Topology) -> tuple[SubBlock, ...]:
    """Every sub-block the outage closes. Raises ValueError for an unknown station or bad times."""
    for s in (outage.from_station, outage.to_station):
        if s not in topo.stations:
            raise ValueError(f"Outage {outage.name}: {s!r} is not a station in the topology")
    if outage.from_station == outage.to_station:
        raise ValueError(f"Outage {outage.name}: from and to station are the same")
    if outage.start_s < 0 or outage.duration_s <= 0:
        raise ValueError(f"Outage {outage.name}: start must be >= 0 and duration > 0")
    path = topo.path(outage.from_station, outage.to_station)
    pairs = list(zip(path, path[1:]))
    if outage.both_directions:
        pairs += [(b, a) for a, b in pairs]
    return tuple(blk for a, b in pairs for blk in topo.sub_blocks(a, b))


def simulate(topo: Topology, trips: list[Trip], params: SimParams, seed: int = 0, **kwargs) -> SimResult:
    """Convenience wrapper: build and run one replication."""
    return Simulation(topo, trips, params, seed, **kwargs).run()
