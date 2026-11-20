"""Event recording and causal delay attribution.

Two tables come out of every run:

events      one row per train per station: scheduled vs actual time (arr, dep or pass).
increments  one row per change in a train's delay, with its cause:
              primary             a sampled (or forced) disruption at a departure
              knock_on            waiting for a block or platform held by a delayed train
              timetable_conflict  waiting behind a train that is itself on time, so the
                                  timetable itself does not leave enough room
              recovery            delay won back on slack running time or shortened dwell
                                  (amount is negative)

Attribution rule. Each train carries a DelayLedger: its current delay split by root cause
id. When train B waits w seconds behind train A, the part of w up to A's own current delay
is shared among A's root causes in proportion to A's ledger (knock_on), and any remainder
is a timetable_conflict. Recovery shrinks every entry of the ledger proportionally.
Because every change goes through the ledger, sum(ledger) always equals the train's current
delay, and adding up the increments never double counts a delay as it travels.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

EVENT_COLUMNS = ["trip_id", "station", "kind", "stop_index", "sched_s", "actual_s", "delay_s",
                 "ledger_s", "is_stop", "is_destination"]
INCREMENT_COLUMNS = ["trip_id", "time_s", "location", "location_type", "cause", "amount_s",
                     "root_id", "blocking_trip_id"]

_EPS = 1e-9


@dataclass
class DelayLedger:
    """A train's current delay, split by the root cause that produced each part."""

    parts: dict[str, float] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return sum(self.parts.values())

    def add(self, root_id: str, seconds: float) -> None:
        if seconds > 0:
            self.parts[root_id] = self.parts.get(root_id, 0.0) + seconds

    def shares(self, seconds: float) -> dict[str, float]:
        """Split `seconds` over the current roots in proportion to their size."""
        total = self.total
        if total <= _EPS or seconds <= 0:
            return {}
        return {r: seconds * v / total for r, v in self.parts.items()}

    def recover(self, seconds: float) -> dict[str, float]:
        """Remove up to `seconds` proportionally. Returns the amount removed per root."""
        total = self.total
        if total <= _EPS or seconds <= 0:
            return {}
        seconds = min(seconds, total)
        removed = {r: seconds * v / total for r, v in self.parts.items()}
        for r, v in removed.items():
            left = self.parts[r] - v
            if left > _EPS:
                self.parts[r] = left
            else:
                del self.parts[r]
        return removed


class EventLog:
    """Collects rows during a run and turns them into DataFrames at the end."""

    def __init__(self) -> None:
        self._events: list[tuple] = []
        self._increments: list[tuple] = []

    def event(self, trip_id, station, kind, stop_index, sched_s, actual_s, ledger_s, is_stop,
              is_destination) -> None:
        self._events.append((trip_id, station, kind, stop_index, sched_s, actual_s,
                             actual_s - sched_s, ledger_s, is_stop, is_destination))

    def increment(self, trip_id, time_s, location, location_type, cause, amount_s, root_id,
                  blocking_trip_id="") -> None:
        if abs(amount_s) > _EPS:
            self._increments.append((trip_id, time_s, location, location_type, cause, amount_s,
                                     root_id, blocking_trip_id))

    def frames(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        return (pd.DataFrame(self._events, columns=EVENT_COLUMNS),
                pd.DataFrame(self._increments, columns=INCREMENT_COLUMNS))


def attribute_wait(log: EventLog, victim_id: str, victim: DelayLedger, blocker_id: str,
                   blocker: DelayLedger | None, wait_s: float, time_s: float, location: str,
                   location_type: str) -> None:
    """Record a wait of `wait_s` and add it to the victim's ledger, following the rule above."""
    if wait_s <= _EPS:
        return
    blocker_delay = blocker.total if blocker else 0.0
    inherited = min(wait_s, blocker_delay)
    for root, amount in (blocker.shares(inherited) if blocker else {}).items():
        victim.add(root, amount)
        log.increment(victim_id, time_s, location, location_type, "knock_on", amount, root, blocker_id)
    rest = wait_s - inherited
    if rest > _EPS:
        root = f"C:{location}"
        victim.add(root, rest)
        log.increment(victim_id, time_s, location, location_type, "timetable_conflict", rest, root,
                      blocker_id)


def record_recovery(log: EventLog, trip_id: str, ledger: DelayLedger, seconds: float, time_s: float,
                    location: str, location_type: str) -> None:
    for root, amount in ledger.recover(seconds).items():
        log.increment(trip_id, time_s, location, location_type, "recovery", -amount, root)
