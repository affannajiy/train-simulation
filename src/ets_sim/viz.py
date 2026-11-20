"""Plotly figure builders used by the Streamlit app. Kept here so they can be tested."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ets_sim import style
from ets_sim.topology import Topology

PLANNED_COLOR = style.PLANNED
NORTH_COLOR = style.NORTH
SOUTH_COLOR = style.SOUTH
MAP_STYLE = "carto-darkmatter"


def to_clock(seconds: pd.Series | np.ndarray, service_date: dt.date) -> pd.Series:
    """Seconds from service-day start -> timestamps, so times past 24:00 fall on the next day."""
    return pd.Timestamp(service_date) + pd.to_timedelta(np.asarray(seconds, dtype=float), unit="s")


def marey_figure(events: pd.DataFrame, topo: Topology, service_date: dt.date, trip_dirs: dict[str, int],
                 directions: tuple[int, ...] = (0, 1),
                 window_s: tuple[float, float] | None = None) -> go.Figure:
    """Time-distance diagram: planned dashed grey, simulated solid (blue north, violet south)."""
    ev = events.copy()
    ev["km"] = ev["station"].map(topo.chart_km)
    ev["direction_id"] = ev["trip_id"].map(trip_dirs)
    ev = ev[ev["direction_id"].isin(directions)]
    order = {"arr": 0, "pass": 1, "dep": 2}
    ev = ev.assign(_o=ev["kind"].map(order)).sort_values(["trip_id", "sched_s", "_o"])
    fig = go.Figure()
    for tid, g in ev.groupby("trip_id", sort=False):
        color = NORTH_COLOR if g["direction_id"].iloc[0] == 0 else SOUTH_COLOR
        hover = [f"{tid} {s}<br>planned {_hhmm(p)} | sim {_hhmm(a)} | delay {d / 60:.1f} min"
                 for s, p, a, d in zip(g["station"], g["sched_s"], g["actual_s"], g["delay_s"])]
        fig.add_trace(go.Scatter(x=to_clock(g["sched_s"], service_date), y=g["km"], mode="lines",
                                 line=dict(color=PLANNED_COLOR, dash="dash", width=1), name=f"{tid} planned",
                                 legendgroup=tid, showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=to_clock(g["actual_s"], service_date), y=g["km"], mode="lines",
                                 line=dict(color=color, width=1.4), name=tid, legendgroup=tid,
                                 showlegend=False, text=hover, hovertemplate="%{text}<extra></extra>"))
    main = sorted((s for s in topo.stations.values() if not s.branch_junction), key=lambda s: s.line_km)
    fig.update_yaxes(autorange="reversed", tickmode="array", tickvals=[s.line_km for s in main],
                     ticktext=[s.name.title() for s in main], title=None,
                     tickfont=dict(family=style.SANS, size=10, color=style.MUTED), showgrid=True)
    fig.update_xaxes(title=None, tickformat="%H:%M", side="top")
    if window_s:
        fig.update_xaxes(range=list(to_clock(np.array(window_s), service_date)))
    for name, color, dash in [("Planned", PLANNED_COLOR, "dash"), ("Northbound (sim)", NORTH_COLOR, "solid"),
                              ("Southbound (sim)", SOUTH_COLOR, "solid")]:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines", name=name,
                                 line=dict(color=color, dash=dash, width=2)))
    fig.update_layout(height=900, margin=dict(l=8, r=8, t=44, b=8), showlegend=True,
                      legend=dict(orientation="h", y=-0.02, yanchor="top", x=0))
    return fig


def _hhmm(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}"


def positions_at(events: pd.DataFrame, topo: Topology, t: float, time_col: str = "actual_s") -> pd.DataFrame:
    """Each running train's position at time t, interpolated in a straight line between stations."""
    rows = []
    for tid, g in events.sort_values(time_col).groupby("trip_id"):
        times = g[time_col].to_numpy()
        if t < times[0] or t > times[-1]:
            continue
        k = int(np.searchsorted(times, t, side="right")) - 1
        k = min(k, len(times) - 2) if len(times) > 1 else 0
        a, b = g.iloc[k], g.iloc[min(k + 1, len(g) - 1)]
        span = b[time_col] - a[time_col]
        f = 0.0 if span <= 0 else (t - a[time_col]) / span
        sa, sb = topo.stations[a["station"]], topo.stations[b["station"]]
        rows.append({
            "trip_id": tid,
            "lat": sa.lat + f * (sb.lat - sa.lat),
            "lon": sa.lon + f * (sb.lon - sa.lon),
            "delay_min": (a["delay_s"] + f * (b["delay_s"] - a["delay_s"])) / 60,
            "near": a["station"] if f < 0.5 else b["station"],
        })
    return pd.DataFrame(rows, columns=["trip_id", "lat", "lon", "delay_min", "near"])


def station_trace(topo: Topology) -> go.Scattermap:
    s = list(topo.stations.values())
    return go.Scattermap(lat=[x.lat for x in s], lon=[x.lon for x in s], mode="markers",
                         marker=dict(size=6, color=style.MUTED), text=[x.name.title() for x in s],
                         hoverinfo="text", name="Stations")


def ci_figure(df: pd.DataFrame, x: str, y: str, title: str, x_title: str, y_title: str) -> go.Figure:
    """Line with 95% CI error bars, for experiment sweeps."""
    fig = go.Figure(go.Scatter(
        x=df[x], y=df[y], mode="lines+markers", name=title,
        line=dict(color=style.ORANGE, width=2), marker=dict(size=8, color=style.ORANGE),
        error_y=dict(type="data", symmetric=False, array=df[f"{y}_hi"] - df[y], arrayminus=df[y] - df[f"{y}_lo"],
                     color=style.MUTED, thickness=1.2, width=5),
    ))
    fig.update_layout(xaxis_title=x_title, yaxis_title=y_title, height=380, showlegend=False)
    return fig
