"""Trip data and timetable transforms.

A Trip is the timetable of one train. Transforms (buffer, shifted copy) return new Trips
and never change the original, so every scenario starts from the same timetable.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd


@dataclass(frozen=True)
class Stop:
    station: str
    arr_s: float  # scheduled arrival, seconds from service-day start
    dep_s: float  # scheduled departure


@dataclass(frozen=True)
class Trip:
    trip_id: str
    direction_id: int
    stops: tuple[Stop, ...]
    international: bool = False
    synthetic: bool = False  # added by the frequency stress test
    # Scheduled running time per leg in the published timetable, kept when a buffer is added,
    # so a supplement-based minimum running time stays physical. Empty: use the current times.
    base_run_s: tuple[float, ...] = ()

    def leg_run_s(self) -> tuple[float, ...]:
        return tuple(b.arr_s - a.dep_s for a, b in zip(self.stops, self.stops[1:]))

    @property
    def origin(self) -> str:
        return self.stops[0].station

    @property
    def destination(self) -> str:
        return self.stops[-1].station

    @property
    def journey_s(self) -> float:
        return self.stops[-1].arr_s - self.stops[0].dep_s


def trips_from_frames(trips: pd.DataFrame, stop_times: pd.DataFrame) -> list[Trip]:
    """Build Trip objects from the loader's trips.csv and stop_times.csv."""
    out = []
    by_trip = {tid: g.sort_values("stop_sequence") for tid, g in stop_times.groupby("trip_id")}
    for r in trips.itertuples():
        g = by_trip[r.trip_id]
        stops = tuple(Stop(s, float(a), float(d)) for s, a, d in zip(g["station"], g["arr_s"], g["dep_s"]))
        out.append(Trip(str(r.trip_id), int(r.direction_id), stops, bool(r.international)))
    return out


def apply_buffer(trip: Trip, buffer_s: float) -> Trip:
    """Add buffer_s to the whole journey, spread over legs in proportion to running time.

    Dwell times are unchanged. The origin departure is unchanged, so every later scheduled
    time moves later by the buffer added up to that point.
    """
    if buffer_s == 0:
        return trip
    runs = list(trip.leg_run_s())
    total = sum(runs)
    if total <= 0:
        raise ValueError(f"Trip {trip.trip_id} has no running time to spread a buffer over")
    stops = [trip.stops[0]]
    shift = 0.0
    for stop, run in zip(trip.stops[1:], runs):
        shift += buffer_s * run / total
        stops.append(Stop(stop.station, stop.arr_s + shift, stop.dep_s + shift))
    return replace(trip, stops=tuple(stops), base_run_s=trip.base_run_s or tuple(runs))


def shifted_copy(trip: Trip, offset_s: float, new_id: str) -> Trip:
    """Same stopping pattern and running times, every time moved by offset_s."""
    stops = tuple(Stop(s.station, s.arr_s + offset_s, s.dep_s + offset_s) for s in trip.stops)
    return replace(trip, trip_id=new_id, stops=stops, synthetic=True)


def add_synthetic_trips(trips: list[Trip], n_extra: int, offset_s: float) -> list[Trip]:
    """Add n_extra copies of existing trips, picked evenly across the day, shifted by offset_s.

    Copies are spread over the timetable so extra traffic is not bunched at one hour.
    If n_extra exceeds the number of trips, a second round uses 2 * offset_s, and so on.
    """
    if n_extra <= 0:
        return list(trips)
    ordered = sorted(trips, key=lambda t: t.stops[0].dep_s)
    extra = []
    for k in range(n_extra):
        round_no, pos = divmod(k, len(ordered))
        # A prime stride jumps around the day instead of copying consecutive departures,
        # and visits every trip once per round because it shares no factor with the count.
        idx = (pos * 7919) % len(ordered)
        base = ordered[idx]
        extra.append(shifted_copy(base, offset_s * (round_no + 1), f"{base.trip_id}+S{k}"))
    return list(trips) + extra
