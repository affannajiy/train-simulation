"""Streamlit front end for the KTM ETS delay propagation simulator.

Run:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import datetime as dt
import sys
from dataclasses import replace
from pathlib import Path

# Streamlit Community Cloud installs requirements.txt only, not this package, so make
# src/ importable. A local `pip install -e .` makes this a no-op.
_SRC = str(Path(__file__).resolve().parents[1] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pandas as pd  # noqa: E402
import plotly.graph_objects as go
import streamlit as st

from ets_sim import live_map, metrics, realtime, style, viz
from ets_sim.config import load_config, project_path
from ets_sim.experiments import (Scenario, buffer_sweep, frequency_stress, run_replications,
                                 speed_comparison, block_length_sensitivity)
from ets_sim.loader import load_or_build
from ets_sim.model import params_from_config, simulate
from ets_sim.topology import Topology
from ets_sim.train import apply_buffer, trips_from_frames

st.set_page_config(page_title="KTM ETS delay propagation", page_icon=":material/train:", layout="wide")
st.markdown(style.CSS, unsafe_allow_html=True)

ASSUMED = " :orange-badge[assumed]"


def section(title: str, note: str = "") -> None:
    st.markdown(style.section(title, note), unsafe_allow_html=True)


# ------------------------------------------------------------------ data


@st.cache_resource
def load_all():
    cfg = load_config()
    try:
        tt = load_or_build(cfg)
    except (FileNotFoundError, ValueError) as exc:
        return cfg, None, str(exc)
    return cfg, tt, ""


cfg, tt, load_error = load_all()
if tt is None:
    st.markdown(style.top_bar("KTM ETS · Delay Propagation", "Discrete-event simulator", []),
                unsafe_allow_html=True)
    st.error(f"Could not load the timetable. {load_error}")
    st.stop()

SERVICE_DATE = dt.date.fromisoformat(str(cfg["network"]["service_date"]))
BASE_TRIPS = trips_from_frames(tt.trips, tt.stop_times)
TRIP_DIRS = {t.trip_id: t.direction_id for t in BASE_TRIPS}


@st.cache_resource
def topology(block_km: float) -> Topology:
    return Topology(tt.stations, block_km)


# ------------------------------------------------------------------ sidebar

sb = st.sidebar
pdc = cfg["primary_delay"]
sb.markdown('<div class="ets-side-title">Scenario</div>', unsafe_allow_html=True)
sb.caption("Values tagged *assumed* are modelling assumptions, listed in the README.")

with sb.expander("Primary delays", icon=":material/bolt:"):
    p_origin = st.slider("P(delay at origin)" + ASSUMED, 0.0, 1.0, float(pdc["p_origin"]), 0.05)
    origin_median = st.slider("Origin delay median, min" + ASSUMED, 0.5, 20.0, float(pdc["origin_median_min"]), 0.5)
    origin_sigma = st.slider("Origin delay spread (sigma)" + ASSUMED, 0.1, 2.0, float(pdc["origin_sigma"]), 0.1)
    p_stop = st.slider("P(delay at each stop)" + ASSUMED, 0.0, 0.5, float(pdc["p_stop"]), 0.01)
    stop_median = st.slider("Stop delay median, min" + ASSUMED, 0.5, 10.0, float(pdc["stop_median_min"]), 0.5)
    stop_sigma = st.slider("Stop delay spread (sigma)" + ASSUMED, 0.1, 2.0, float(pdc["stop_sigma"]), 0.1)

with sb.expander("Operations", icon=":material/tune:", expanded=True):
    buffer_min = st.slider("Timetable buffer per journey, min", 0, 15, 0, 1)
    line_speed = st.segmented_control("Line speed, km/h", [140, 160],
                                      default=int(cfg["operations"]["line_speed_kmh"]))
    line_speed = line_speed or int(cfg["operations"]["line_speed_kmh"])
    late_min = st.slider("Late threshold, min", 1, 15, int(cfg["metrics"]["late_threshold_min"]))
    block_km = st.select_slider("Max block length, km" + ASSUMED, [2.5, 5.0, 10.0, 20.0],
                                value=float(cfg["network"]["max_block_km"]))

with sb.expander("Run", icon=":material/play_arrow:", expanded=True):
    seed = int(st.number_input("Random seed", 0, 10_000_000, int(cfg["experiments"]["base_seed"]), 1))
    reps = st.slider("Replications", 1, 100, 20, help="Used by the KPI strip, Bottlenecks and Experiments.")

PARAMS = params_from_config(
    cfg, p_origin=p_origin, origin_median_s=origin_median * 60, origin_sigma=origin_sigma, p_stop=p_stop,
    stop_median_s=stop_median * 60, stop_sigma=stop_sigma, line_speed_kmh=float(line_speed))
TRIPS = [apply_buffer(t, buffer_min * 60) for t in BASE_TRIPS]
SCENARIO = Scenario(topology(block_km), TRIPS, PARAMS, late_min * 60)


@st.cache_data(show_spinner="Simulating one day...")
def single_run(params_key: tuple, buffer: int, block: float, seed_: int):
    res = simulate(topology(block), [apply_buffer(t, buffer * 60) for t in BASE_TRIPS], PARAMS, seed=seed_)
    return res.events, res.increments


@st.cache_data(show_spinner="Running replications...")
def many_runs(params_key: tuple, buffer: int, block: float, seed_: int, n: int, threshold_s: float):
    rep = run_replications(replace(SCENARIO, threshold_s=threshold_s), n, seed_)
    return rep.summary, rep.events, rep.increments


PKEY = (p_origin, origin_median, origin_sigma, p_stop, stop_median, stop_sigma, line_speed)

# ------------------------------------------------------------------ top bar

st.markdown(style.top_bar(
    "KTM ETS · Delay Propagation",
    f"Discrete-event simulation · {len(tt.trips)} trips · {len(tt.stations)} stations · service day {SERVICE_DATE}",
    [("SEED", str(seed)), ("REPS", str(reps)), ("SPEED", f"{line_speed} km/h"), ("BUFFER", f"{buffer_min} min"),
     ("BLOCK", f"{block_km:g} km"), ("LATE ≥", f"{late_min} min")]), unsafe_allow_html=True)

events, increments = single_run(PKEY, buffer_min, block_km, seed)
summ, evs, incs = many_runs(PKEY, buffer_min, block_km, seed, reps, late_min * 60)

tabs = st.tabs(["Control room", "Time–distance", "Bottlenecks", "Experiments", "Live vs sim", "Data quality"])

# ------------------------------------------------------------------ Control room

with tabs[0]:
    kpis = []
    for key, label, unit, fmt in [
        ("on_time_all_pct", "On time · all stops", "%", "{:.1f}"),
        ("on_time_dest_pct", "On time · destination", "%", "{:.1f}"),
        ("avg_dest_delay_min", "Avg destination delay", "min", "{:.1f}"),
        ("avg_trains_affected_per_primary", "Trains hit per primary", "", "{:.2f}"),
    ]:
        m, lo, hi = metrics.mean_ci(summ[key])
        kpis.append((label, fmt.format(m), unit, f"95% CI {fmt.format(lo)}–{fmt.format(hi)}"))
    section("Headline", f"mean of {reps} replications")
    st.markdown(style.kpi_board(kpis), unsafe_allow_html=True)

    section("Live line", f"one replication, seed {seed}")
    st.iframe(live_map.html(events, SCENARIO.topo, TRIP_DIRS, late_min), height=live_map.HEIGHT)

    section("Where the minutes come from", "delay minutes per simulated day, by cause")
    cause = summ[["primary_min", "knock_on_min", "timetable_conflict_min", "recovered_min"]].mean()
    names = ["Primary", "Knock-on", "Timetable conflict", "Recovered"]
    colors = [style.ORANGE, style.MAJOR, style.SOFT_ORANGE, style.ON_TIME]
    fig = go.Figure(go.Bar(x=cause.values, y=names, orientation="h", marker_color=colors,
                           text=[f"{v:,.0f}" for v in cause.values], textposition="outside",
                           textfont=dict(family=style.MONO, color=style.TEXT), cliponaxis=False,
                           hovertemplate="%{y}: %{x:,.1f} min<extra></extra>"))
    fig.update_traces(marker_opacity=0.85)
    fig.update_layout(height=210, bargap=0.5, xaxis_title="Minutes per day", margin=dict(l=8, r=48, t=8, b=8))
    fig.update_yaxes(autorange="reversed", ticks="", tickfont=dict(family=style.SANS, size=12, color=style.TEXT))
    st.plotly_chart(fig, width="stretch")

# ------------------------------------------------------------------ Time-distance

with tabs[1]:
    c1, c2 = st.columns([1, 2])
    dirs = c1.pills("Direction", ["Northbound", "Southbound"], default=["Northbound", "Southbound"],
                    selection_mode="multi")
    hours = c2.slider("Time window (hours from service-day start)", 0, 34, (6, 12))
    dir_ids = tuple(i for i, n in enumerate(["Northbound", "Southbound"]) if n in (dirs or []))
    section("Planned vs simulated paths", f"one replication, seed {seed}")
    if not dir_ids:
        st.info("Pick at least one direction to draw the paths.")
    else:
        st.plotly_chart(viz.marey_figure(events, SCENARIO.topo, SERVICE_DATE, TRIP_DIRS, dir_ids,
                                         (hours[0] * 3600, hours[1] * 3600)), width="stretch")
    st.caption("Dashed: planned timetable. Solid: simulated. A solid line drifting right of its dashed twin is a "
               "late train; lines bunching together show knock-on delay. Butterworth is drawn at the "
               "Bukit Mertajam km (branch line).")

# ------------------------------------------------------------------ Bottlenecks

with tabs[2]:
    c1, c2 = st.columns(2)
    with c1:
        section("Stations", "average arrival delay, top 20")
        sd = metrics.station_delay(evs).head(20)
        fig = go.Figure(go.Bar(x=sd["avg_delay_min"], y=sd["station"].str.title(), orientation="h",
                               marker_color=style.ORANGE, hovertemplate="%{y}: %{x:.2f} min<extra></extra>"))
        fig.update_layout(height=520, xaxis_title="Minutes")
        fig.update_yaxes(autorange="reversed", ticks="", tickfont=dict(family=style.SANS, size=11, color=style.TEXT))
        st.plotly_chart(fig, width="stretch")
    with c2:
        section("Propagation reach", "other trains each primary delay reached")
        imp = metrics.primary_impact(incs)
        if len(imp):
            fig = go.Figure(go.Histogram(x=imp["trains_affected"], marker_color=style.NORTH,
                                         hovertemplate="%{x} trains: %{y} delays<extra></extra>"))
            fig.update_layout(height=520, xaxis_title="Other trains affected", yaxis_title="Primary delays")
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No primary delays in these runs, so nothing propagated. Raise the delay probabilities.")

    c1, c2 = st.columns(2)
    with c1:
        section("Bottleneck sections", "secondary delay generated per day")
        st.dataframe(metrics.bottlenecks(incs, reps).head(20).round(2), hide_index=True, width="stretch")
    with c2:
        section("Trains that hold up others", "knock-on caused per day")
        st.dataframe(metrics.train_impact(incs, reps).head(20).round(2), hide_index=True, width="stretch")

# ------------------------------------------------------------------ Experiments

with tabs[3]:
    ex = cfg["experiments"]
    results_dir = project_path(cfg["data"]["results_dir"])
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    exp = c1.selectbox("Experiment", ["Buffer sweep", "Line speed 140 vs 160", "Frequency stress",
                                      "Block length sensitivity"])
    file = {"Buffer sweep": "buffer_sweep", "Line speed 140 vs 160": "speed_comparison",
            "Frequency stress": "frequency_stress", "Block length sensitivity": "block_length"}[exp]
    saved = results_dir / f"{file}.csv"
    run_now = c2.button("Run with current scenario", type="primary", icon=":material/play_arrow:",
                        width="stretch")
    st.caption(f"{reps} replications with common random numbers (seed {seed}). Saved full runs from "
               "`python -m ets_sim.experiments` are shown until you run one here.")
    df = None
    if run_now:
        with st.spinner(f"Running {exp.lower()}..."):
            if exp == "Buffer sweep":
                df = buffer_sweep(SCENARIO, ex["buffer_minutes"], reps, seed)
            elif exp == "Line speed 140 vs 160":
                df = speed_comparison(SCENARIO, ex["line_speeds_kmh"], reps, seed)
            elif exp == "Frequency stress":
                df = frequency_stress(SCENARIO, ex["frequency_extra_trips"], float(ex["frequency_offset_min"]),
                                      float(ex["on_time_target_pct"]), reps, seed)
            else:
                df = block_length_sensitivity(SCENARIO, tt.stations, ex["block_km_values"], reps, seed)
        source = "run just now with the current scenario"
    elif saved.exists():
        df = pd.read_csv(saved)
        source = f"saved results from {saved.name}"
    if df is not None:
        x, x_title = {"buffer_sweep": ("buffer_min", "Buffer per journey (min)"),
                      "speed_comparison": ("line_speed_kmh", "Line speed (km/h)"),
                      "frequency_stress": ("extra_trips", "Extra daily trips"),
                      "block_length": ("max_block_km", "Max block length (km)")}[file]
        section(f"{exp}: on-time % at all stops", f"95% CI · {source}")
        st.plotly_chart(viz.ci_figure(df, x, "on_time_all_pct", exp, x_title, "On time %"), width="stretch")
        st.dataframe(df.round(2), hide_index=True, width="stretch")
    else:
        st.info(f"No saved results for {exp.lower()} yet. Press **Run with current scenario** to make them.")

# ------------------------------------------------------------------ Live vs simulated


@st.cache_data(ttl=600, show_spinner="Looking for realtime logs...")
def realtime_sources() -> tuple[dict, str]:
    """Local data/realtime/ first; otherwise the realtime-data branch on GitHub."""
    days = realtime.local_days(cfg)
    if days:
        return days, "data/realtime/"
    return realtime.remote_days(cfg), "realtime-data branch on GitHub"


@st.cache_data(ttl=600, show_spinner="Reading realtime log...")
def realtime_frame(day: str, source) -> pd.DataFrame:
    return realtime.read_day(source)


with tabs[4]:
    rt_days, rt_where = realtime_sources()
    rt = None
    if not rt_days:
        section("Logged positions vs simulation")
        if realtime.remote_base(cfg) is None:
            st.info("No realtime logs in `data/realtime/` yet. The logger commits them to the `realtime-data` "
                    "branch. To view them here, run:\n\n`git fetch origin realtime-data`\n\n"
                    "`git restore --source origin/realtime-data --worktree -- data/realtime`\n\n"
                    "Or set `data.realtime_repo` in config.yaml to read them from GitHub.")
        else:
            st.info(f"No realtime logs on the `{cfg['data'].get('realtime_branch', 'realtime-data')}` branch "
                    f"for the last {cfg['data'].get('realtime_remote_days', 7)} days. Check that the "
                    "realtime-logger workflow is running in the repo's Actions tab.")
    else:
        c1, c2 = st.columns([1, 3])
        day = c1.selectbox("Day (UTC)", list(rt_days), index=len(rt_days) - 1, help=f"Source: {rt_where}")
        try:
            rt = realtime_frame(day, rt_days[day])
        except Exception as exc:  # network error or malformed file: report it, keep the other tabs alive
            st.error(f"Could not read the log for {day}: {exc}")
    if rt is not None and not rt.empty:
        rt["observed"] = pd.to_datetime(rt["observed_at_utc"]).dt.tz_convert("Asia/Kuala_Lumpur")
        bad = int(rt["bad_position"].sum())
        stamps = sorted(rt["observed"].unique())
        pick = c2.select_slider("Observation time (MYT)", options=stamps, value=stamps[-1],
                                format_func=lambda t: pd.Timestamp(t).strftime("%H:%M"))
        section("Logged positions vs simulation",
                f"{len(rt)} rows · {rt['vehicle_label'].nunique()} trainsets · {bad} bad positions hidden")
        snap = rt[(rt["observed"] == pick) & (~rt["bad_position"])]
        local = pd.Timestamp(pick)
        t_s = local.hour * 3600 + local.minute * 60 + local.second
        # The timetable repeats daily and runs past 24:00 (GTFS hours up to 33), so a clock
        # time also matches service-day second t_s + 86400 (overnight trains).
        sim_pos = pd.concat([viz.positions_at(events, SCENARIO.topo, t_s),
                             viz.positions_at(events, SCENARIO.topo, t_s + 86400)], ignore_index=True)
        fig = go.Figure([viz.station_trace(SCENARIO.topo),
                         go.Scattermap(lat=snap["lat"], lon=snap["lon"], mode="markers+text",
                                       text=snap["vehicle_label"].fillna("?") + " (" + snap["trip_id"].fillna("?") + ")",
                                       textfont=dict(color=style.TEXT), textposition="top right",
                                       marker=dict(size=13, color=style.TEXT), name="Real (logged)"),
                         go.Scattermap(lat=sim_pos["lat"], lon=sim_pos["lon"], mode="markers", text=sim_pos["trip_id"],
                                       marker=dict(size=9, color=style.ORANGE), name="Simulated")])
        fig.update_layout(map=dict(style=viz.MAP_STYLE, center=dict(lat=3.6, lon=101.6), zoom=5.4),
                          height=700, margin=dict(l=0, r=0, t=0, b=0),
                          legend=dict(x=0.01, y=0.99, bgcolor=style.PANEL, bordercolor=style.RULE, borderwidth=1))
        st.plotly_chart(fig, width="stretch")
        st.caption("White: logged position, with the trainset and the trip_id the feed claims. Orange: simulated "
                   "trains at the same time of day, current scenario and seed. trip_id in this feed is not "
                   "reliable (docs/decisions.md item 8).")

# ------------------------------------------------------------------ Data quality

with tabs[5]:
    section("Loader report", "every trip dropped, cut short or flagged, with the reason")
    st.dataframe(tt.quality, hide_index=True, width="stretch")
    section("Stations", f"{len(tt.stations)} stations · {len(tt.trips)} trips · service date {SERVICE_DATE}")
    st.dataframe(tt.stations, hide_index=True, width="stretch")
