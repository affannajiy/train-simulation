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
        hover = [f"{tid} {style.station_name(s)}<br>planned {_hhmm(p)} | sim {_hhmm(a)} | delay {d / 60:.1f} min"
                 for s, p, a, d in zip(g["station"], g["sched_s"], g["actual_s"], g["delay_s"])]
        fig.add_trace(go.Scatter(x=to_clock(g["sched_s"], service_date), y=g["km"], mode="lines",
                                 line=dict(color=PLANNED_COLOR, dash="dash", width=1), name=f"{tid} planned",
                                 legendgroup=tid, showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=to_clock(g["actual_s"], service_date), y=g["km"], mode="lines",
                                 line=dict(color=color, width=1.4), name=tid, legendgroup=tid,
                                 showlegend=False, text=hover, hovertemplate="%{text}<extra></extra>"))
    main = sorted((s for s in topo.stations.values() if not s.branch_junction), key=lambda s: s.line_km)
    # Name only stations far enough apart not to overlap; every station keeps a faint gridline,
    # and hovering a train line still names the station.
    span = (main[-1].line_km - main[0].line_km) if len(main) > 1 else 1.0
    named = spaced_labels(main, min_gap_km=span * LABEL_PX / MAREY_PLOT_PX)
    fig.update_yaxes(autorange="reversed", tickmode="array", tickvals=[s.line_km for s in named],
                     ticktext=[style.station_name(s.name) for s in named], title=None,
                     tickfont=dict(family=style.SANS, size=10, color=style.MUTED), showgrid=True,
                     minor=dict(tickmode="array", tickvals=[s.line_km for s in main], showgrid=True,
                                gridcolor="rgba(255,255,255,0.035)", ticks=""))
    fig.update_xaxes(title=None, tickformat="%H:%M", side="top")
    if window_s:
        fig.update_xaxes(range=list(to_clock(np.array(window_s), service_date)))
    for name, color, dash in [("Planned", PLANNED_COLOR, "dash"), ("Northbound (sim)", NORTH_COLOR, "solid"),
                              ("Southbound (sim)", SOUTH_COLOR, "solid")]:
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines", name=name,
                                 line=dict(color=color, dash=dash, width=2)))
    # 620 px fits a laptop screen; the fullscreen button gives the full height for detail.
    fig.update_layout(height=620, margin=dict(l=8, r=8, t=44, b=8), showlegend=True,
                      legend=dict(orientation="h", y=-0.02, yanchor="top", x=0))
    return fig


MAREY_PLOT_PX = 520  # approximate plot height inside the 620 px figure, after margins and legend
LABEL_PX = 14        # vertical room one 10 px station label needs


def spaced_labels(stations, min_gap_km: float):
    """Pick which stations to name on a km axis so no two labels sit closer than min_gap_km.

    Landmark stations (the big ones in _LANDMARKS) are placed first, then the rest fill the gaps
    in line order. Returns the chosen stations sorted by km.
    """
    ranked = sorted(stations, key=lambda s: (s.name not in _LANDMARKS, s.line_km))
    kept: list = []
    for s in ranked:
        if all(abs(s.line_km - k.line_km) >= min_gap_km for k in kept):
            kept.append(s)
    return sorted(kept, key=lambda s: s.line_km)


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
                         marker=dict(size=6, color=style.MUTED), text=[style.station_name(x.name) for x in s],
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


# ------------------------------------------------------------------ charts added for the dashboard

# Sequential ramp for "more delay": one hue (orange), from near-canvas to bright. Dark theme only.
HEAT_SCALE = [[0.0, "#1A1A1A"], [0.25, "#4A2412"], [0.55, "#A8460F"], [0.8, style.ORANGE], [1.0, style.SOFT_ORANGE]]
DIR_NAMES = {0: "Northbound", 1: "Southbound"}
DIR_COLORS = {0: NORTH_COLOR, 1: SOUTH_COLOR}

# Stations named on km axes. The rest show on hover; 50 labels on one axis is noise.
_LANDMARKS = {"PADANG BESAR", "ALOR SETAR", "SUNGAI PETANI", "BUKIT MERTAJAM", "TAIPING", "IPOH",
              "TANJONG MALIM", "KL SENTRAL", "SEREMBAN", "GEMAS", "SEGAMAT", "KLUANG", "JB SENTRAL"}


def _main_stations(topo: Topology):
    return sorted((s for s in topo.stations.values() if not s.branch_junction), key=lambda s: s.line_km)


def _landmark_axis(fig: go.Figure, topo: Topology) -> None:
    main = _main_stations(topo)
    big = [s for s in main if s.name in _LANDMARKS] or main[::6]
    fig.update_xaxes(tickmode="array", tickvals=[s.line_km for s in big], ticktext=[style.station_name(s.name) for s in big],
                     tickangle=-35, title=None, range=[main[0].line_km - 10, main[-1].line_km + 10],
                     tickfont=dict(family=style.SANS, size=10, color=style.MUTED))


def _arrivals(events: pd.DataFrame) -> pd.DataFrame:
    return events[events["kind"] == "arr"]


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def station_hour_heatmap(events: pd.DataFrame, topo: Topology, min_arrivals: int = 3) -> go.Figure:
    """Average arrival delay by station (rows, in line order) and scheduled hour (columns).

    Cells with fewer than min_arrivals arrivals stay blank, so one odd train cannot paint a cell.
    Hours run past 24 because the GTFS service day does.
    """
    arr = _arrivals(events).copy()
    arr["hour"] = (arr["sched_s"] // 3600).astype(int)
    g = arr.groupby(["station", "hour"])["delay_s"].agg(["mean", "count"]).reset_index()
    g.loc[g["count"] < min_arrivals, "mean"] = np.nan
    order = sorted(g["station"].unique(), key=topo.chart_km)
    hours = list(range(int(g["hour"].min()), int(g["hour"].max()) + 1)) if len(g) else []
    z = g.pivot(index="station", columns="hour", values="mean").reindex(index=order, columns=hours) / 60
    n = g.pivot(index="station", columns="hour", values="count").reindex(index=order, columns=hours)
    zz = z.to_numpy(dtype=float)
    # Cap the colour scale at the 97th percentile so a few extreme cells do not darken the rest.
    # Hover still shows the true value; capped cells just show the brightest colour.
    finite = zz[np.isfinite(zz)]
    zmax = max(float(np.percentile(finite, 97)), 1.0) if finite.size else 1.0
    fig = go.Figure(go.Heatmap(
        z=zz, x=[f"{h % 24:02d}:00" + (" +1" if h >= 24 else "") for h in hours],
        y=[style.station_name(s) for s in order], customdata=n.fillna(0).to_numpy(), colorscale=HEAT_SCALE, zmin=0,
        zmax=zmax, xgap=1, ygap=1,
        colorbar=dict(title=dict(text="min", side="top"), thickness=10, outlinewidth=0,
                      tickfont=dict(family=style.MONO, size=10, color=style.MUTED)),
        hovertemplate="%{y} · %{x}<br>avg delay %{z:.1f} min<br>%{customdata:.0f} arrivals<extra></extra>"))
    fig.update_yaxes(autorange="reversed", ticks="", showgrid=False, dtick=1,
                     tickfont=dict(family=style.SANS, size=9, color=style.MUTED))
    fig.update_xaxes(side="top", ticks="", showgrid=False, tickangle=0, nticks=12)
    # Top margin leaves room for the chart toolbar above the hour labels.
    fig.update_layout(height=660, margin=dict(l=8, r=8, t=56, b=8))
    return fig


def delay_buildup(events: pd.DataFrame, topo: Topology, trip_dirs: dict[str, int]) -> go.Figure:
    """Mean arrival delay at each station along the line, one line per direction, with a 95% CI
    band across replications. Read northbound right to left, southbound left to right.
    Main-line stations only."""
    from ets_sim import metrics  # local import: metrics must not depend on viz

    arr = _arrivals(events).copy()
    # Branch stations share their junction's km and would draw a vertical jump; leave them out.
    arr = arr[~arr["station"].map(lambda s: bool(topo.stations[s].branch_junction))]
    arr["direction_id"] = arr["trip_id"].map(trip_dirs)
    if "rep" not in arr:
        arr["rep"] = 0
    per_rep = arr.groupby(["direction_id", "station", "rep"])["delay_s"].mean().div(60).reset_index()
    rows = []
    for (d, s), grp in per_rep.groupby(["direction_id", "station"]):
        m, lo, hi = metrics.mean_ci(grp["delay_s"])
        rows.append({"direction_id": int(d), "station": s, "km": topo.chart_km(s), "mean": m, "lo": lo, "hi": hi})
    df = pd.DataFrame(rows, columns=["direction_id", "station", "km", "mean", "lo", "hi"]).sort_values("km")
    fig = go.Figure()
    for d, grp in df.groupby("direction_id"):
        color, name = DIR_COLORS.get(d, style.MUTED), DIR_NAMES.get(d, str(d))
        fig.add_trace(go.Scatter(x=list(grp["km"]) + list(grp["km"])[::-1],
                                 y=list(grp["hi"]) + list(grp["lo"])[::-1], fill="toself", mode="none",
                                 fillcolor=_rgba(color, 0.14), hoverinfo="skip", showlegend=False,
                                 legendgroup=name))
        fig.add_trace(go.Scatter(
            x=grp["km"], y=grp["mean"], mode="lines+markers", name=name, legendgroup=name,
            line=dict(color=color, width=2), marker=dict(size=8, color=color, line=dict(width=2, color=style.BG)),
            customdata=np.c_[grp["station"].map(style.station_name), grp["lo"], grp["hi"]],
            hovertemplate=(f"{name} · %{{customdata[0]}}<br>avg delay %{{y:.2f}} min"
                           "<br>95% CI %{customdata[1]:.2f}–%{customdata[2]:.2f}<extra></extra>")))
    _landmark_axis(fig, topo)
    fig.update_yaxes(title="Avg arrival delay (min)", rangemode="tozero")
    fig.update_layout(height=380, legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0))
    return fig


def punctuality_curve(events: pd.DataFrame, late_min: float, max_min: float = 30.0) -> go.Figure:
    """% of arrivals at most t minutes late, for every t: how the on-time figure depends on where
    the line is drawn. The dotted line marks the current late threshold."""
    arr = _arrivals(events)
    t = np.arange(0, max_min + 0.25, 0.25)
    fig = go.Figure()
    for name, sub, color in [("All stops", arr, style.ORANGE), ("Destination", arr[arr["is_destination"]], style.SOUTH)]:
        d = np.sort(sub["delay_s"].to_numpy() / 60)
        pct = 100.0 * np.searchsorted(d, t, side="right") / len(d) if len(d) else np.full_like(t, np.nan)
        fig.add_trace(go.Scatter(x=t, y=pct, mode="lines", name=name, line=dict(color=color, width=2),
                                 hovertemplate=f"{name}: %{{y:.1f}}%<extra></extra>"))
    fig.add_vline(x=late_min, line=dict(color=style.MUTED, width=1, dash="dot"))
    fig.add_annotation(x=late_min, y=0, yref="paper", yanchor="bottom", xanchor="left", showarrow=False,
                       text=f" late threshold {late_min:g} min", font=dict(size=10, color=style.MUTED))
    fig.update_xaxes(title="Within this many minutes late", range=[0, max_min], hoverformat=".2f")
    fig.update_yaxes(title="Arrivals on time", ticksuffix="%")
    fig.update_layout(height=320, hovermode="x unified", legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0))
    return fig


def cause_sankey(cause_min: dict[str, float]) -> go.Figure:
    """Attributed delay minutes per day: each cause flows into the delay added, which splits into
    minutes recovered and net delay left. Blame is proportional, so this is accounting, not a
    causal chain."""
    spec = [("Primary", "primary_min", style.ORANGE), ("Outage", "outage_min", style.FAINT),
            ("Knock-on", "knock_on_min", style.MAJOR),
            ("Timetable conflict", "timetable_conflict_min", style.SOFT_ORANGE)]
    srcs = [(n, max(float(cause_min.get(k, 0.0)), 0.0), c) for n, k, c in spec]
    srcs = [s for s in srcs if s[1] > 0]
    added = sum(v for _, v, _ in srcs)
    recovered = min(max(float(cause_min.get("recovered_min", 0.0)), 0.0), added)
    i_add = len(srcs)
    fig = go.Figure(go.Sankey(
        arrangement="fixed", valueformat=",.0f", valuesuffix=" min",
        node=dict(label=[n for n, _, _ in srcs] + ["Delay added", "Recovered", "Net delay"],
                  color=[c for _, _, c in srcs] + [style.MUTED, style.ON_TIME, style.ORANGE_HOVER],
                  pad=18, thickness=12, line=dict(width=0),
                  hovertemplate="%{label}: %{value:,.0f} min/day<extra></extra>"),
        link=dict(source=list(range(len(srcs))) + [i_add, i_add], target=[i_add] * len(srcs) + [i_add + 1, i_add + 2],
                  value=[v for _, v, _ in srcs] + [recovered, added - recovered],
                  color=[_rgba(c, 0.35) for _, _, c in srcs] + [_rgba(style.ON_TIME, 0.22),
                                                               _rgba(style.ORANGE_HOVER, 0.3)],
                  hovertemplate="%{source.label} → %{target.label}: %{value:,.0f} min/day<extra></extra>")))
    fig.update_layout(height=300, font=dict(family=style.SANS, size=12, color=style.TEXT))
    return fig


def corridor_bottlenecks(bottlenecks: pd.DataFrame, topo: Topology) -> go.Figure:
    """Secondary delay generated per day at its km along the line, stacked by cause. A section
    sits at its midpoint with both directions summed; a platform sits at its station."""
    b = bottlenecks.copy()

    def km(loc: str) -> float:
        if "->" in loc:
            a, c = loc.split("->", 1)
            return (topo.chart_km(a) + topo.chart_km(c)) / 2
        return topo.chart_km(loc)

    def label(loc: str, ltype: str) -> str:
        if ltype != "block":
            return f"{style.station_name(loc)} platforms"
        return " ↔ ".join(sorted(style.station_name(p) for p in loc.split("->", 1)))

    if b.empty:
        b = pd.DataFrame(columns=["location", "location_type", "knock_on_min", "timetable_conflict_min"])
    b["km"] = [km(x) for x in b["location"]]
    b["label"] = [label(x, t) for x, t in zip(b["location"], b["location_type"])]
    g = b.groupby(["km", "label"], as_index=False)[["knock_on_min", "timetable_conflict_min"]].sum()
    fig = go.Figure()
    for col, name, color in [("timetable_conflict_min", "Timetable conflict", style.SOFT_ORANGE),
                             ("knock_on_min", "Knock-on", style.MAJOR)]:
        fig.add_trace(go.Bar(x=g["km"], y=g[col], name=name, marker_color=color, width=5, customdata=g["label"],
                             hovertemplate=f"%{{customdata}}<br>{name}: %{{y:.1f}} min/day<extra></extra>"))
    _landmark_axis(fig, topo)
    fig.update_yaxes(title="Min per day")
    fig.update_layout(barmode="stack", height=340, legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0))
    return fig
