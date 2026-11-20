"""Ride along: a 3D view that follows one train down the line (MapLibre ground, three.js objects).

A demo view, not an analysis tool. It moves trains by sub-block, from the occupancy log, so a
train held at a signal visibly stops there, and it names the cause of each hold. Between
signals, motion is eased in and out of stops for display only: the model has no acceleration.

The whole day is sent to the browser once, like live_map. Track geometry comes from
OpenStreetMap (track.py); the model's own positions are GTFS line km, mapped onto the OSM line
by fraction along each section.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ets_sim import style
from ets_sim.topology import Topology
from ets_sim.track import ATTRIBUTION, Track

HEIGHT = 640          # iframe height, px
PRE_ROLL_S = 600      # a train is shown at its origin this long before it departs
POST_ROLL_S = 300     # and at its destination this long after it arrives
HOLD_MIN_S = 1.0      # shorter waits are not shown as holds


# ------------------------------------------------------------------ helpers


def _parse_block(resource: str) -> tuple[str, str, int]:
    """'A->B#3' -> ('A', 'B', 3)."""
    sec, idx = resource.rsplit("#", 1)
    a, b = sec.split("->")
    return a, b, int(idx)


def _mmss(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


def _root_text(root: str) -> str:
    if root.startswith("P:"):
        trip, _, station = root[2:].partition("@")
        return f"primary delay to {trip} at {style.station_name(station)}"
    if root.startswith("O:"):
        return f"outage {root[2:]}"
    if root.startswith("C:"):  # a timetable conflict that later travelled on as knock-on
        a, _, b = root[2:].partition("->")
        return f"timetable conflict between {style.station_name(a)} and {style.station_name(b)}"
    return root


def most_knock_on(increments: pd.DataFrame) -> str | None:
    """Trip with the most knock-on minutes; None when no train was held by a late one."""
    k = increments[increments["cause"] == "knock_on"].groupby("trip_id")["amount_s"].sum()
    return str(k.idxmax()) if len(k) and k.max() > 0 else None


# ------------------------------------------------------------------ payload


class _Positions:
    """Maps model positions (section, fraction by GTFS km) to (line index, chainage m)."""

    def __init__(self, topo: Topology, track: Track):
        self.topo, self.track = topo, track
        self.names = list(track.lines)
        self.index = {n: i for i, n in enumerate(self.names)}

    def block(self, a: str, b: str, k: int) -> tuple[tuple[int, float], tuple[int, float], int]:
        """(start, end, sign) of sub-block k of a->b. sign is +1 when chainage grows."""
        line, ca, cb = self.track.section(a, b)
        n = len(self.topo.sub_blocks(a, b))
        li = self.index[line]
        start = ca + (cb - ca) * k / n
        end = ca + (cb - ca) * (k + 1) / n
        return (li, start), (li, end), (1 if cb >= ca else -1)


def _keyframes(rows: pd.DataFrame, pos: _Positions) -> list[list]:
    """One trip's occupancy rows (in order) to keyframes [t, line, chainage, sign].

    The head of the train is at the start of a resource from t_req (it reached the signal)
    to t_in (it got the block), then runs to the end of the block by the next row's t_req.
    Equal consecutive positions mean the train is standing still."""
    out: list[list] = []
    end: tuple[int, float] | None = None
    sign = 1

    def add(t, p, s):
        kf = [int(round(t)), p[0], int(round(p[1])), s]
        if out and out[-1][1:3] == kf[1:3] and out[-1][0] == kf[0]:
            return
        out.append(kf)

    for r in rows.itertuples():
        if r.resource.startswith("platform:"):
            start = end  # a platform is where the last block ended: the station
            if start is None:
                continue
        else:
            start, blk_end, sign = pos.block(*_parse_block(r.resource))
        if end is not None and end != start:
            # The previous block ended on another line (branch junction): finish it there first.
            add(r.t_req, end, sign)
        add(r.t_req, start, sign)
        if r.t_in - r.t_req >= HOLD_MIN_S:
            add(r.t_in, start, sign)
        end = start if r.resource.startswith("platform:") else blk_end
    return out


def _delay_series(inc: pd.DataFrame) -> list[list[int]]:
    """[[time, delay so far]]: the running sum of a trip's increments. The ledger always equals the
    train's delay (events.py), so this is its delay between stations too. A wait is booked when it
    ends; the page adds the time already spent in a wait that is still going on."""
    inc = inc.sort_values("time_s", kind="stable")
    cum = inc["amount_s"].cumsum()
    return [[int(round(t)), int(round(c))] for t, c in zip(inc["time_s"], cum)]


def _holds(trip_id: str, rows: pd.DataFrame, inc: pd.DataFrame) -> list[list]:
    """[start, end, text, is_wait] for every wait at a signal or platform and every primary delay."""
    out = []
    for r in rows.itertuples():
        wait = r.t_in - r.t_req
        if wait < HOLD_MIN_S:
            continue
        here = inc[(inc["time_s"] - r.t_in).abs() < 1e-6]
        here = here[here["location_type"].isin(["block", "platform"])]
        if r.resource.startswith("platform:"):
            where = f"outside {style.station_name(r.resource.split(':')[1])}, waiting for a platform"
        else:
            a, b, k = _parse_block(r.resource)
            where = f"at the signal into {style.station_name(a)} to {style.station_name(b)}, block {k + 1}"
        parts = []
        for cause, g in here.groupby("cause"):
            mins = g["amount_s"].sum()
            blocker = g["blocking_trip_id"].iloc[0]
            if cause == "knock_on":
                top = g.groupby("root_id")["amount_s"].sum().idxmax()
                parts.append(f"Knock-on {_mmss(mins)}: train {blocker} ahead was late (root: {_root_text(top)}).")
            elif cause == "timetable_conflict":
                parts.append(f"Timetable conflict {_mmss(mins)}: train {blocker} ahead was on time, "
                             "so the timetable leaves no room.")
            elif cause == "outage":
                parts.append(f"Outage {_mmss(mins)}: {g['root_id'].iloc[0][2:]} closed the line ahead.")
        out.append([int(round(r.t_req)), int(round(r.t_in)),
                    f"{trip_id} held {_mmss(wait)} {where}. " + " ".join(parts), 1])
    for r in inc[inc["cause"] == "primary"].itertuples():
        out.append([int(round(r.time_s)), int(round(r.time_s + r.amount_s)),
                    f"{trip_id}: primary delay of {_mmss(r.amount_s)} at {style.station_name(r.location)} "
                    "(a random disruption, the start of a delay chain).", 0])
    return sorted(out)


def payload(events: pd.DataFrame, increments: pd.DataFrame, occupancy: pd.DataFrame, topo: Topology,
            track: Track, trip_dirs: dict[str, int], late_min: float, follow: str | None = None) -> dict:
    pos = _Positions(topo, track)
    occ = occupancy.sort_values(["trip_id", "t_in", "t_req"], kind="stable")
    inc_by_trip = dict(tuple(increments.groupby("trip_id")))
    ev = events.sort_values(["trip_id", "actual_s"], kind="stable")
    ev_by_trip = dict(tuple(ev.groupby("trip_id")))
    knock = increments[increments["cause"] == "knock_on"].groupby("trip_id")["amount_s"].sum()
    empty_inc = increments.iloc[:0]

    trips = []
    for tid, rows in occ.groupby("trip_id", sort=True):
        tid = str(tid)
        k = _keyframes(rows, pos)
        if len(k) < 2:
            continue
        e = ev_by_trip.get(tid, events.iloc[:0])
        stops = e[e["kind"].isin(["arr", "dep"])]
        trips.append({
            "id": tid, "dir": int(trip_dirs.get(tid, 0)),
            "from": style.station_name(e["station"].iloc[0]) if len(e) else "",
            "to": style.station_name(e["station"].iloc[-1]) if len(e) else "",
            "dep": int(round(e["sched_s"].iloc[0])) if len(e) else k[0][0],
            "knock": round(float(knock.get(tid, 0.0)) / 60, 1),
            "k": k,
            "d": _delay_series(inc_by_trip.get(tid, empty_inc)),
            "st": [[int(round(t)), style.station_name(s)] for t, s in zip(stops["actual_s"], stops["station"])],
            "h": _holds(tid, rows, inc_by_trip.get(tid, empty_inc)),
        })

    # Signals: one at the start of every sub-block that some train used, red while occupied.
    blocks = occ[~occ["resource"].str.startswith("platform:")].sort_values("t_in")
    signals = []
    for res, g in blocks.groupby("resource", sort=True):
        start, _, sign = pos.block(*_parse_block(res))
        iv = [int(round(v)) for pair in zip(g["t_in"], g["t_out"]) for v in pair]
        signals.append([start[0], int(round(start[1])), sign, iv])

    lines = []
    for name in pos.names:
        ln = track.lines[name]
        lines.append({"name": name, "x": [round(v, 6) for v in ln.lonlat[:, 0]],
                      "y": [round(v, 6) for v in ln.lonlat[:, 1]], "c": [round(v, 1) for v in ln.chainage]})
    stations = []
    for name in topo.stations:
        if not track.has(name):
            continue
        p = track.positions(name)
        line = "main" if "main" in p else next(iter(p))
        stations.append({"n": style.station_name(name), "l": pos.index[line], "c": round(p[line].chainage_m)})

    ids = [t["id"] for t in trips]
    follow = follow if follow in ids else most_knock_on(increments)
    if follow not in ids:
        follow = max(trips, key=lambda t: t["d"][-1][1] if t["d"] else 0)["id"] if trips else None
    return {"lines": lines, "stations": stations, "trips": trips, "signals": signals,
            "follow": follow, "late": float(late_min), "major": style.MAJOR_LATE_MIN,
            "attrib": ATTRIBUTION}


# ------------------------------------------------------------------ html


def html(events: pd.DataFrame, increments: pd.DataFrame, occupancy: pd.DataFrame, topo: Topology,
         track: Track, trip_dirs: dict[str, int], late_min: float, follow: str | None = None) -> str:
    data = json.dumps(payload(events, increments, occupancy, topo, track, trip_dirs, late_min, follow),
                      separators=(",", ":"))
    data = data.replace("</", r"<\/")  # a name containing "</script>" cannot end the script block
    tokens = {"BG": style.BG, "PANEL": style.PANEL, "RULE": style.RULE, "TEXT": style.TEXT,
              "MUTED": style.MUTED, "FAINT": style.FAINT, "ORANGE": style.ORANGE, "ON_TIME": style.ON_TIME,
              "MAJOR": style.MAJOR, "ORANGE_HOVER": style.ORANGE_HOVER, "HEIGHT": str(HEIGHT)}
    out = _TEMPLATE.replace("__DATA__", data)
    for k, v in tokens.items():
        out = out.replace(f"__{k}__", v)
    return out


# The page lives in its own file: it is mostly JavaScript, and editors highlight it there.
_TEMPLATE = Path(__file__).with_name("ride_view.html").read_text(encoding="utf-8")
