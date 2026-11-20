"""Track geometry for the 3D ride view: OpenStreetMap lines with station chainages.

The geometry is display-only. The simulation keeps using GTFS line km. A position in the model
(a fraction along the directed section A->B, by GTFS km) maps to the same fraction along the
OSM line between A and B, so the two never disagree about which station a train is at.

Built once by scripts/fetch_track.py. Map data (c) OpenStreetMap contributors, ODbL 1.0.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ATTRIBUTION = "Track geometry &copy; OpenStreetMap contributors (ODbL)"


@dataclass(frozen=True)
class Line:
    name: str
    lonlat: np.ndarray    # (n, 2)
    chainage: np.ndarray  # (n,) metres from the first point


@dataclass(frozen=True)
class StationPos:
    station: str
    line: str
    chainage_m: float
    snap_m: float


class Track:
    def __init__(self, lines: dict[str, Line], stations: list[StationPos]):
        self.lines = lines
        self._at: dict[str, dict[str, StationPos]] = {}
        for s in stations:
            self._at.setdefault(s.station, {})[s.line] = s

    @classmethod
    def load(cls, path: str | Path) -> Track:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        lines, stations = {}, []
        for f in data["features"]:
            p = f["properties"]
            if p["kind"] == "line":
                ll = np.asarray(f["geometry"]["coordinates"], dtype=float)
                lines[p["line"]] = Line(p["line"], ll, _chainage(ll))
            elif p["kind"] == "station":
                stations.append(StationPos(p["station"], p["line"], float(p["chainage_m"]), float(p["snap_m"])))
        return cls(lines, stations)

    def has(self, station: str) -> bool:
        return station in self._at

    def positions(self, station: str) -> dict[str, StationPos]:
        return dict(self._at[station])

    def section(self, a: str, b: str) -> tuple[str, float, float]:
        """(line, chainage at a, chainage at b) for the section a->b. Both stations must sit on
        one line; a branch junction sits on the main line and on its branch."""
        shared = set(self._at[a]) & set(self._at[b])
        if not shared:
            raise KeyError(f"No track line holds both {a} and {b}")
        # Prefer a branch: the junction is on the main line too, but a->terminus runs on the branch.
        line = sorted(shared, key=lambda n: n == "main")[0]
        return line, self._at[a][line].chainage_m, self._at[b][line].chainage_m


def _chainage(lonlat: np.ndarray) -> np.ndarray:
    lat = np.radians((lonlat[1:, 1] + lonlat[:-1, 1]) / 2)
    dx = np.radians(np.diff(lonlat[:, 0])) * np.cos(lat) * 6371008.8
    dy = np.radians(np.diff(lonlat[:, 1])) * 6371008.8
    return np.concatenate([[0.0], np.cumsum(np.hypot(dx, dy))])
