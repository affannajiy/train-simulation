"""Shared physical railway: station graph and fixed sub-blocks.

The topology is independent of any train's stopping pattern. Every train that runs between
two stations uses the same sub-blocks, whether it stops at the stations in between or not.
That is what lets trains with different stopping patterns delay each other.

Double track, one track per direction: the sub-blocks of section A->B and B->A are separate
resources, so opposing trains never conflict.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from functools import lru_cache

import pandas as pd


@dataclass(frozen=True)
class Station:
    name: str
    lat: float
    lon: float
    line_km: float            # position on the main line; branch stations use the junction km
    branch_junction: str = ""  # empty for main-line stations
    branch_km: float = 0.0     # distance from the junction along the branch


@dataclass(frozen=True)
class SubBlock:
    """One fixed block: a directed piece of a station-to-station section."""

    section: tuple[str, str]  # (from_station, to_station), direction of travel
    index: int                 # 0 is the block leaving from_station
    count: int                 # number of sub-blocks in this section
    length_km: float

    @property
    def key(self) -> tuple[str, str, int]:
        return (*self.section, self.index)


class Topology:
    def __init__(self, stations: pd.DataFrame, max_block_km: float):
        if max_block_km <= 0:
            raise ValueError("max_block_km must be positive")
        self.max_block_km = float(max_block_km)
        self.stations: dict[str, Station] = {
            r.station: Station(r.station, float(r.lat), float(r.lon), float(r.line_km),
                               r.branch_junction or "", float(r.branch_km))
            for r in stations.itertuples()
        }
        self._adj: dict[str, dict[str, float]] = {s: {} for s in self.stations}

        main = sorted((s for s in self.stations.values() if not s.branch_junction),
                      key=lambda s: s.line_km)
        for a, b in zip(main, main[1:]):
            self._connect(a.name, b.name, b.line_km - a.line_km)
        for s in self.stations.values():
            if s.branch_junction:
                if s.branch_junction not in self.stations:
                    raise ValueError(f"{s.name}: junction {s.branch_junction} is not a station")
                self._connect(s.branch_junction, s.name, s.branch_km)

    def _connect(self, a: str, b: str, km: float) -> None:
        if km <= 0:
            raise ValueError(f"Section {a}-{b} has non-positive length {km}")
        self._adj[a][b] = km
        self._adj[b][a] = km

    # ------------------------------------------------------------ queries

    def neighbours(self, station: str) -> dict[str, float]:
        return dict(self._adj[station])

    def section_km(self, a: str, b: str) -> float:
        return self._adj[a][b]

    @lru_cache(maxsize=None)
    def path(self, origin: str, dest: str) -> tuple[str, ...]:
        """Stations from origin to dest inclusive. The graph is a tree, so the path is unique."""
        if origin not in self._adj or dest not in self._adj:
            raise KeyError(f"Unknown station in path {origin} -> {dest}")
        prev: dict[str, str | None] = {origin: None}
        queue = deque([origin])
        while queue:
            cur = queue.popleft()
            if cur == dest:
                break
            for nxt in self._adj[cur]:
                if nxt not in prev:
                    prev[nxt] = cur
                    queue.append(nxt)
        if dest not in prev:
            raise ValueError(f"No path {origin} -> {dest}")
        out = [dest]
        while prev[out[-1]] is not None:
            out.append(prev[out[-1]])
        return tuple(reversed(out))

    @lru_cache(maxsize=None)
    def sub_blocks(self, a: str, b: str) -> tuple[SubBlock, ...]:
        """Equal sub-blocks of the directed section a->b, each at most max_block_km long."""
        km = self.section_km(a, b)
        n = max(1, math.ceil(km / self.max_block_km - 1e-9))
        return tuple(SubBlock((a, b), i, n, km / n) for i in range(n))

    def chart_km(self, station: str) -> float:
        """Y position for time-distance charts. Branch stations sit at their junction km."""
        return self.stations[station].line_km
