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

from ets_sim import live_map, metrics, realtime, ride_view, style, viz
from ets_sim.config import load_config, project_path
from ets_sim.experiments import (Scenario, buffer_sweep, frequency_stress, run_replications,
                                 speed_comparison, block_length_sensitivity)
from ets_sim.loader import load_or_build
from ets_sim.model import params_from_config, simulate
from ets_sim.topology import Topology
from ets_sim.track import Track
from ets_sim.train import apply_buffer, trips_from_frames

st.set_page_config(page_title="KTM ETS delay propagation", page_icon=":material/train:", layout="wide")
st.markdown(style.CSS, unsafe_allow_html=True)

ASSUMED = " :orange-badge[assumed]"


def section(title: str, note: str = "", guide: str = "") -> None:
    st.markdown(style.section(title, note, guide), unsafe_allow_html=True)


# Sidebar tooltips. Kept in one place so the wording stays consistent; Markdown is allowed.
HELP = {
    "p_origin": "Chance that a train **starts late** at its first station. 0.3 means about 3 trains in 10. "
                "*Assumed*: not yet fitted from KTMB data.",
    "origin_median": "Typical size of a late start, in minutes. Half of late starts are shorter than this, half "
                     "longer (lognormal). *Assumed.*",
    "origin_sigma": "How much late-start sizes vary. Higher means rare but very long delays become more likely "
                    "(a longer tail). *Assumed.*",
    "p_stop": "Chance that a train **loses time at each stop** (boarding, a door fault). Applied at every "
              "intermediate stop, so small values add up over a long trip. *Assumed.*",
    "stop_median": "Typical size of a delay at a stop, in minutes (lognormal median). *Assumed.*",
    "stop_sigma": "How much stop-delay sizes vary (lognormal sigma). *Assumed.*",
    "buffer": "Extra minutes added to **every** journey's scheduled running time, spread over its legs in "
              "proportion to running time. More buffer absorbs delay, but trains take longer on paper.",
    "speed": "Top speed a train can use to **win time back** when late. 140 km/h is the ETS service speed; "
             "160 km/h is the design speed, shown as an idealised what-if, not a prediction.",
    "late": "A train counts as **late** at a stop when it arrives more than this many minutes behind "
            "schedule. Changes every on-time figure and the map colours.",
    "block": "Longest stretch of track that only **one train** may occupy at a time. Shorter blocks let trains "
             "run closer together. *Assumed*: real signal spacing is not published.",
    "seed": "Starting point for the random delays. Same seed and settings give exactly the same results, so "
            "a run can be repeated.",
    "reps": "How many simulated days to average. More days give a narrower 95% confidence interval but run "
            "slower. Used by the KPI strip, Bottlenecks and Experiments; the map and time–distance chart "
            "show one day.",
}


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
sb.caption("Every value here changes the scenario for **all tabs**. Hover the :material/help: next to a "
           "control to see what it does. Values tagged *assumed* are modelling assumptions, listed in the README.")

with sb.expander("Primary delays", icon=":material/bolt:"):
    st.caption("The random delays that start everything: late starts and time lost at stops.")
    p_origin = st.slider("P(delay at origin)" + ASSUMED, 0.0, 1.0, float(pdc["p_origin"]), 0.05,
                         help=HELP["p_origin"])
    origin_median = st.slider("Origin delay median, min" + ASSUMED, 0.5, 20.0, float(pdc["origin_median_min"]), 0.5,
                              help=HELP["origin_median"])
    origin_sigma = st.slider("Origin delay spread (sigma)" + ASSUMED, 0.1, 2.0, float(pdc["origin_sigma"]), 0.1,
                             help=HELP["origin_sigma"])
    p_stop = st.slider("P(delay at each stop)" + ASSUMED, 0.0, 0.5, float(pdc["p_stop"]), 0.01,
                       help=HELP["p_stop"])
    stop_median = st.slider("Stop delay median, min" + ASSUMED, 0.5, 10.0, float(pdc["stop_median_min"]), 0.5,
                            help=HELP["stop_median"])
    stop_sigma = st.slider("Stop delay spread (sigma)" + ASSUMED, 0.1, 2.0, float(pdc["stop_sigma"]), 0.1,
                           help=HELP["stop_sigma"])

with sb.expander("Operations", icon=":material/tune:", expanded=True):
    st.caption("How the timetable and the track handle those delays.")
    buffer_min = st.slider("Timetable buffer per journey, min", 0, 15, 0, 1, help=HELP["buffer"])
    line_speed = st.segmented_control("Line speed, km/h", [140, 160],
                                      default=int(cfg["operations"]["line_speed_kmh"]), help=HELP["speed"])
    line_speed = line_speed or int(cfg["operations"]["line_speed_kmh"])
    late_min = st.slider("Late threshold, min", 1, 15, int(cfg["metrics"]["late_threshold_min"]), help=HELP["late"])
    block_km = st.select_slider("Max block length, km" + ASSUMED, [2.5, 5.0, 10.0, 20.0],
                                value=float(cfg["network"]["max_block_km"]), help=HELP["block"])

with sb.expander("Run", icon=":material/play_arrow:", expanded=True):
    st.caption("How many simulated days, and which random draw.")
    seed = int(st.number_input("Random seed", 0, 10_000_000, int(cfg["experiments"]["base_seed"]), 1,
                               help=HELP["seed"]))
    reps = st.slider("Replications", 1, 100, 20, help=HELP["reps"])

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

@st.dialog("Live line", width="large", icon=":material/train:")
def live_dialog():
    """Full-size live line, with the most-delayed list. Close with Esc or the X."""
    with st.container(key="live_full"):
        st.caption(f"One replication, seed {seed}. Close with Esc or the X in the corner.")
        st.iframe(live_map.html(events, SCENARIO.topo, TRIP_DIRS, late_min), height=live_map.height())


@st.cache_resource
def track() -> Track | None:
    """OSM track geometry for the ride view. None when the file is missing: the rest of the app still runs."""
    path = project_path(cfg["data"]["track_geojson"])
    return Track.load(path) if path.exists() else None


@st.cache_data(show_spinner="Simulating the day with signal-by-signal detail...")
def ride_run(params_key: tuple, buffer: int, block: float, seed_: int):
    """Same run as single_run (same seed, same results) plus the block occupancy the 3D view needs."""
    res = simulate(topology(block), [apply_buffer(t, buffer * 60) for t in BASE_TRIPS], PARAMS, seed=seed_,
                   record_occupancy=True)
    return res.events, res.increments, res.occupancy


@st.dialog("Ride along", width="large", icon=":material/videocam:")
def ride_dialog():
    """3D follow camera for one train. Close with Esc or the X."""
    trk = track()
    if trk is None:
        st.error("Track geometry is missing (data/snapshots/ets_track_osm.geojson). Run scripts/fetch_track.py.")
        return
    ev, inc, occ = ride_run(PKEY, buffer_min, block_km, seed)
    st.caption(f"One replication, seed {seed}. Starts on the train with the most knock-on delay; pick another "
               "in the list. **Next hold** jumps to the next time it stops at a red signal. Keys: 1 to 4 "
               "cameras, Space play or pause, N next hold. Needs internet for the map.")
    st.iframe(ride_view.html(ev, inc, occ, SCENARIO.topo, trk, TRIP_DIRS, late_min), height=ride_view.HEIGHT)


tabs = st.tabs(["Control Room", "Time–Distance", "Bottlenecks", "Experiments", "Live vs Sim", "Data Quality",
                "About"])

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
    section("Headline", f"mean of {reps} replications", guide=(
        "Each figure is the mean over all replications (simulated days). The small line under it is the 95% "
        "confidence interval: a narrow range means the result is stable; raise Replications to narrow it.\n\n"
        "Trains hit per primary: how many other trains one random delay went on to make late, on average."))
    st.markdown(style.kpi_board(kpis), unsafe_allow_html=True)

    c1, c2, c3 = st.columns([4, 1, 1], vertical_alignment="bottom")
    with c1:
        section("Live line", f"one replication, seed {seed}", guide=(
            "Press PLAY to run one simulated day; the speed buttons and the slider move through time. Top: the "
            "trains on a map. Bottom: the same trains on a straight track diagram, northbound on the upper line.\n\n"
            "Colour shows delay: white on time, orange late, red 15+ min late. Hover a train for its delay.\n\n"
            "Press Expand for a bigger view with the most-delayed list. Press Ride along to follow one train "
            "in 3D and watch it stop at red signals."))
    if c2.button("Ride along", icon=":material/videocam:", width="stretch",
                 help="Follow one train in 3D: chase, side, cab and orbit cameras. Starts on the train with "
                      "the most knock-on delay."):
        ride_dialog()
    if c3.button("Expand", icon=":material/open_in_full:", width="stretch",
                 help="Open the live line in a large window, with the most-delayed trains list."):
        live_dialog()
    st.iframe(live_map.html(events, SCENARIO.topo, TRIP_DIRS, late_min, map_px=live_map.COMPACT_MAP_PX, board=False),
              height=live_map.height(live_map.COMPACT_MAP_PX, board=False))

    cause_all = summ[["primary_min", "outage_min", "knock_on_min", "timetable_conflict_min", "recovered_min"]].mean()
    c1, c2 = st.columns(2)
    with c1:
        section("Where the minutes come from", "delay minutes per simulated day, by cause", guide=(
            "Primary: random delays a train causes itself. Knock-on: waiting behind a train that is already late. "
            "Timetable conflict: waiting behind an on-time train, so the timetable itself is too tight. "
            "Recovered: minutes won back by running faster or shortening stops.\n\n"
            "The About tab defines each cause."))
        cause = cause_all[["primary_min", "knock_on_min", "timetable_conflict_min", "recovered_min"]]
        names = ["Primary", "Knock-on", "Timetable conflict", "Recovered"]
        colors = [style.ORANGE, style.MAJOR, style.SOFT_ORANGE, style.ON_TIME]
        fig = go.Figure(go.Bar(x=cause.values, y=names, orientation="h", marker_color=colors,
                               text=[f"{v:,.0f}" for v in cause.values], textposition="outside",
                               textfont=dict(family=style.MONO, color=style.TEXT), cliponaxis=False,
                               hovertemplate="%{y}: %{x:,.1f} min<extra></extra>"))
        fig.update_traces(marker_opacity=0.85)
        fig.update_layout(height=300, bargap=0.5, xaxis_title="Minutes per day", margin=dict(l=8, r=48, t=8, b=8))
        fig.update_yaxes(autorange="reversed", ticks="", tickfont=dict(family=style.SANS, size=12, color=style.TEXT))
        st.plotly_chart(fig, width="stretch")
    with c2:
        section("How the minutes add up", "attributed minutes per day", guide=(
            "Left: every cause of delay. Middle: all delay added in a day. Right: how much was won back "
            "(Recovered) and how much was left (Net delay). Hover a band for its minutes.\n\n"
            "This is accounting, not a chain of events: when a train waits for a late train, the wait is "
            "shared out in proportion to that train's own causes."))
        st.plotly_chart(viz.cause_sankey(cause_all.to_dict()), width="stretch")

    section("How on-time depends on the threshold", f"all {reps} replications pooled", guide=(
        "Each line shows the share of arrivals no more than X minutes late, for every X. The dotted line is "
        "your Late threshold, so where it crosses a curve is the on-time figure above.\n\n"
        "Use it to compare with operators that count 'late' differently (for example 3 min in Switzerland "
        "and the Netherlands). A steep curve means most delays are small."))
    st.plotly_chart(viz.punctuality_curve(evs, late_min), width="stretch")

# ------------------------------------------------------------------ Time-distance

with tabs[1]:
    c1, c2 = st.columns([1, 2])
    dirs = c1.pills("Direction", ["Northbound", "Southbound"], default=["Northbound", "Southbound"],
                    selection_mode="multi", help="Show one direction or both. One direction is easier to read.")
    hours = c2.slider("Time window (hours from service-day start)", 0, 34, (6, 12),
                      help="Which part of the day to draw. Hours past 24 are after midnight (overnight "
                           "trains of the same service day). A narrow window is easier to read.")
    dir_ids = tuple(i for i, n in enumerate(["Northbound", "Southbound"]) if n in (dirs or []))
    section("Planned vs simulated paths", f"one replication, seed {seed}", guide=(
        "Time runs left to right, the line runs top (Padang Besar) to bottom (JB Sentral). Each line is one "
        "train. Dashed: planned timetable. Solid: simulated.\n\n"
        "A solid line to the right of its dashed twin is a late train. Lines bunching together show knock-on "
        "delay. Drag to zoom, double-click to reset, or use the fullscreen button at the top right of the chart."))
    if not dir_ids:
        st.info("Pick at least one direction to draw the paths.")
    else:
        st.plotly_chart(viz.marey_figure(events, SCENARIO.topo, SERVICE_DATE, TRIP_DIRS, dir_ids,
                                         (hours[0] * 3600, hours[1] * 3600)), width="stretch")
    st.caption("Butterworth is drawn at the Bukit Mertajam km (branch line).")

    section("Delay build-up along the line", f"mean of {reps} replications, 95% CI band", guide=(
        "Average arrival delay at each station, one line per direction. Southbound trains travel left to "
        "right, northbound right to left, so read each line in its own direction.\n\n"
        "A line that climbs means delay builds up along the trip. A sudden step marks a place where trains "
        "lose time. The shaded band is the 95% confidence interval."))
    st.plotly_chart(viz.delay_buildup(evs, SCENARIO.topo, TRIP_DIRS), width="stretch")

# ------------------------------------------------------------------ Bottlenecks

with tabs[2]:
    bn = metrics.bottlenecks(incs, reps)
    section("Where knock-on delay is made", f"along the line · mean of {reps} replications", guide=(
        "Each bar is a section of track between two stations, or a station's platforms, placed at its km. "
        "Height: minutes of secondary delay (knock-on plus timetable conflict) generated there per day, "
        "both directions added together.\n\n"
        "Tall bars are the bottlenecks. Hover a bar for its name; the table below lists them in order."))
    st.plotly_chart(viz.corridor_bottlenecks(bn, SCENARIO.topo), width="stretch")

    section("When and where trains run late", f"average arrival delay · all {reps} replications pooled", guide=(
        "Rows are stations in line order (Padang Besar at the top). Columns are the scheduled hour of arrival. "
        "Brighter cells mean later trains. The top of the colour scale means that many minutes or more, so a "
        "few extreme cells do not hide the rest; hover a cell for its exact value.\n\n"
        "A bright column is a bad time of day across the line; a bright row is a bad station all day. "
        "Blank cells have fewer than 3 arrivals, too few to average."))
    st.plotly_chart(viz.station_hour_heatmap(evs, SCENARIO.topo), width="stretch")

    c1, c2 = st.columns(2)
    with c1:
        section("Stations", "average arrival delay, top 20", guide=(
            "The 20 stations where trains arrive latest on average, over all arrivals and replications."))
        sd = metrics.station_delay(evs).head(20)
        fig = go.Figure(go.Bar(x=sd["avg_delay_min"], y=sd["station"].map(style.station_name), orientation="h",
                               marker_color=style.ORANGE, hovertemplate="%{y}: %{x:.2f} min<extra></extra>"))
        fig.update_layout(height=460, xaxis_title="Minutes")
        fig.update_yaxes(autorange="reversed", ticks="", tickfont=dict(family=style.SANS, size=11, color=style.TEXT))
        st.plotly_chart(fig, width="stretch")
    with c2:
        section("Propagation reach", "other trains each primary delay reached", guide=(
            "Each primary (random) delay is counted once. The bar at 0 is delays that stayed with their own "
            "train; bars further right are delays that spread to more trains.\n\n"
            "A long tail to the right means a single incident can disrupt much of the day."))
        imp = metrics.primary_impact(incs)
        if len(imp):
            fig = go.Figure(go.Histogram(x=imp["trains_affected"], marker_color=style.NORTH,
                                         hovertemplate="%{x} trains: %{y} delays<extra></extra>"))
            fig.update_layout(height=460, xaxis_title="Other trains affected", yaxis_title="Primary delays")
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No primary delays in these runs, so nothing propagated. Raise the delay probabilities.")

    c1, c2 = st.columns(2)
    with c1:
        section("Bottleneck sections", "secondary delay generated per day", guide=(
            "One row per direction of a section (A->B) or per station's platforms. waits: how many times per "
            "day a train had to wait there. Click a column header to sort."))
        st.dataframe(bn.head(20).round(2), hide_index=True, width="stretch", height=420)
    with c2:
        section("Trains that hold up others", "knock-on caused per day", guide=(
            "Trains that most often make other trains wait. trains_held: how many different trains it held "
            "up; minutes_passed_on: the delay it handed on, per day."))
        st.dataframe(metrics.train_impact(incs, reps).head(20).round(2), hide_index=True, width="stretch",
                     height=420)

# ------------------------------------------------------------------ Experiments

with tabs[3]:
    ex = cfg["experiments"]
    results_dir = project_path(cfg["data"]["results_dir"])
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    exp = c1.selectbox("Experiment", ["Buffer sweep", "Line speed 140 vs 160", "Frequency stress",
                                      "Block length sensitivity"], help=(
        "Each experiment changes one thing and keeps the rest of your scenario fixed.\n\n"
        "- **Buffer sweep:** more slack in the timetable.\n"
        "- **Line speed:** 140 vs 160 km/h top speed for recovery.\n"
        "- **Frequency stress:** extra trains added to the day.\n"
        "- **Block length:** shorter or longer signal blocks."))
    file = {"Buffer sweep": "buffer_sweep", "Line speed 140 vs 160": "speed_comparison",
            "Frequency stress": "frequency_stress", "Block length sensitivity": "block_length"}[exp]
    saved = results_dir / f"{file}.csv"
    run_now = c2.button("Run with current scenario", type="primary", icon=":material/play_arrow:",
                        width="stretch", help="Run this experiment now with your sidebar settings and "
                                              "Replications. Can take a minute with many replications.")
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
        section(f"{exp}: on-time % at all stops", f"95% CI · {source}", guide=(
            "Each point is one setting of the experiment; the bar through it is the 95% confidence interval. "
            "If two bars overlap a lot, the difference between those settings may be noise.\n\n"
            "Every setting sees the same random delays (common random numbers), so differences come from "
            "the setting, not from luck."))
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
        day = c1.selectbox("Day (UTC)", list(rt_days), index=len(rt_days) - 1,
                           help=f"Which logged day of KTMB realtime positions to show. Source: {rt_where}")
        try:
            rt = realtime_frame(day, rt_days[day])
        except Exception as exc:  # network error or malformed file: report it, keep the other tabs alive
            st.error(f"Could not read the log for {day}: {exc}")
    if rt is not None and not rt.empty:
        rt["observed"] = pd.to_datetime(rt["observed_at_utc"]).dt.tz_convert("Asia/Kuala_Lumpur")
        bad = int(rt["bad_position"].sum())
        stamps = sorted(rt["observed"].unique())
        pick = c2.select_slider("Observation time (MYT)", options=stamps, value=stamps[-1],
                                format_func=lambda t: pd.Timestamp(t).strftime("%H:%M"),
                                help="Pick one logged snapshot. The simulated trains are drawn at the same "
                                     "time of day.")
        section("Logged positions vs simulation",
                f"{len(rt)} rows · {rt['vehicle_label'].nunique()} trainsets · {bad} bad positions hidden", guide=(
                    "White dots: where KTMB's feed said each trainset was. Orange dots: simulated trains at the "
                    "same time of day. Scroll to zoom, drag to pan.\n\n"
                    "This is a sanity check, not a validation: the feed's trip ids are often wrong."))
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
                          height=560, margin=dict(l=0, r=0, t=0, b=0),
                          legend=dict(x=0.01, y=0.99, bgcolor=style.PANEL, bordercolor=style.RULE, borderwidth=1))
        st.plotly_chart(fig, width="stretch")
        st.caption("White: logged position, with the trainset and the trip_id the feed claims. Orange: simulated "
                   "trains at the same time of day, current scenario and seed. trip_id in this feed is not "
                   "reliable (docs/decisions.md item 8).")

# ------------------------------------------------------------------ Data quality

with tabs[5]:
    section("Loader report", "every trip dropped, cut short or flagged, with the reason", guide=(
        "When the GTFS timetable is loaded, trips that cannot be simulated are dropped or trimmed, and odd "
        "ones are flagged. Each row says which trip and why. Hover the table for search and download."))
    st.dataframe(tt.quality, hide_index=True, width="stretch", height=380)
    section("Stations", f"{len(tt.stations)} stations · {len(tt.trips)} trips · service date {SERVICE_DATE}")
    st.dataframe(tt.stations, hide_index=True, width="stretch", height=420)

# ------------------------------------------------------------------ About

REPO = cfg["data"].get("realtime_repo")
REPO_URL = f"https://github.com/{REPO}" if REPO else ""


def doc_link(path: str) -> str:
    return f"[{path}]({REPO_URL}/blob/main/{path})" if REPO_URL else f"`{path}`"


with tabs[6]:
    with st.container(key="about"):
        section("What this is", "a final-year project")
        st.markdown(
            f"A discrete-event simulation of the KTM **Electric Train Service (ETS)** from Padang Besar to "
            f"JB Sentral, about 902 km. It replays one full service day of the published timetable "
            f"({len(tt.trips)} trips, {len(tt.stations)} stations) and adds random delays, then follows how "
            f"one late train makes other trains late. The goal is to find where delay comes from and how "
            f"much slack the timetable needs, not to predict tomorrow's trains.")

        section("Research questions")
        st.markdown(
            "1. **Delay propagation.** How does one primary delay spread along the corridor, and how many "
            "trains does it reach?\n"
            "2. **Bottlenecks.** Which sections and stations generate the most knock-on delay?\n"
            "3. **Timetable resilience.** How do buffer time, line speed and service frequency change "
            "reliability?")

        section("How the model works", "in four steps")
        st.markdown(
            "- **The track.** Each section between two stations is cut into blocks of at most "
            f"{cfg['network']['max_block_km']:g} km{ASSUMED}. Only one train can be in a block at a time, "
            "one track per direction. Each station has a limited number of platforms.\n"
            "- **A train.** It leaves at its scheduled time, sometimes late (a *primary* delay), and asks "
            "for each block in turn. If the block ahead is taken, it waits and keeps holding its own "
            "block, so the train behind it waits too.\n"
            "- **Recovery.** A late train can run faster, up to line speed, and shorten its stops to a "
            "minimum dwell. It never leaves a station early.\n"
            "- **Blame.** Every minute of delay is tagged with its cause. When train B waits for late "
            "train A, B inherits A's causes. When B waits for a train that is on time, the timetable "
            "itself is too tight: a *timetable conflict*. Totals never count one minute twice.")
        st.markdown(
            "Each scenario runs many times with different random seeds. Every scenario sees the same "
            "random delays on the same trains (common random numbers), so differences come from the "
            "scenario, not from luck. Results show the mean and a 95% confidence interval.")

        section("Delay causes", "the words used in every chart")
        st.dataframe(pd.DataFrame({
            "Cause": ["Primary", "Knock-on", "Timetable conflict", "Outage", "Recovered"],
            "Meaning": [
                "A train starts late or loses time at a stop for its own reasons (random, assumed).",
                "A train waits for another train that is already late.",
                "A train waits for a train that is on time: the timetable leaves no room.",
                "A train waits for a closed section (incident replays only).",
                "Minutes won back by running faster or cutting a stop short.",
            ]}), hide_index=True, width="stretch")

        section("What each tab shows")
        st.dataframe(pd.DataFrame({
            "Tab": ["Control Room", "Time–Distance", "Bottlenecks", "Experiments", "Live vs Sim", "Data Quality"],
            "Shows": [
                "Headline on-time figures, an animated map of one day, delay minutes by cause, and how "
                "on-time depends on the late threshold.",
                "Planned (dashed) vs simulated (solid) train paths, and how delay builds up along the line.",
                "Bottlenecks along the line, a station-by-hour delay heatmap, the worst stations, sections "
                "and trains, and how far each primary delay spread.",
                "Buffer, line speed, frequency and block length sweeps, saved or run with your settings.",
                "Train positions from the KTMB realtime feed next to the simulated trains.",
                "Every trip the loader dropped or flagged, and the station list.",
            ]}), hide_index=True, width="stretch")
        st.caption("The sidebar changes the scenario for every tab. Change a value and the whole app reruns. "
                   "Hover the (i) next to a chart title for how to read it, and the fullscreen icon at the "
                   "top right of any chart or table to enlarge it.")

        section("What it has found so far", f"timetable of {SERVICE_DATE}, 100 replications")
        st.markdown(
            "- **The timetable itself causes most of the lateness.** With every random delay switched off, "
            "the published timetable still produces about 1,000 minutes of conflict delay per day, mostly "
            "between Rawang and Kuala Lumpur and around Tanjong Malim.\n"
            "- **Extra buffer helps less than expected** under the idealised recovery model, because late "
            "trains already recover fast. With a more realistic running-time supplement (UIC 451-1), "
            "on time at destination is about 80%, close to KTMB's reported 80 to 86%.\n"
            "- **More trains hurt quickly.** Adding 40 synthetic trips drops on time at all stops from "
            "about 93% to 89.5%.\n"
            "- **Incident replay.** A real overhead line outage near Seremban (14 Jun 2026) caused about as "
            "much knock-on delay again as the outage itself, across 12 trains.")

        section("What it cannot tell you")
        st.markdown(
            f"- **Delay sizes are assumed.** Values tagged{ASSUMED} are placeholders until they are fitted "
            "from realtime logs, so results describe the model, not measured KTMB performance.\n"
            "- **ETS only.** Komuter, Intercity and Shuttle Selatan share parts of the line and are not modelled, "
            "so real conflicts are understated.\n"
            "- **Simple track.** Fixed blocks and constant speed per leg: no signals, junctions, speed "
            "restrictions or train physics. A late trainset does not delay its next trip.\n"
            "- **The realtime feed is unreliable** today (wrong trip ids, frozen positions), so the "
            "Live vs Sim tab is a check, not a validation.")

        section("Data and code")
        st.markdown(
            "- **Timetable:** KTMB GTFS static feed from data.gov.my, pinned as a snapshot so every "
            "result can be reproduced.\n"
            "- **Positions:** KTMB GTFS realtime vehicle positions, logged hourly by a GitHub Actions job.\n"
            "- **Built with** Python, SimPy, pandas, Plotly and Streamlit.\n"
            f"- **Read more:** {doc_link('README.md')} (full method and assumptions), "
            f"{doc_link('docs/decisions.md')} (why each design choice), "
            f"{doc_link('docs/benchmarking.md')} (international comparison)."
            + (f"\n- **Source code:** [{REPO}]({REPO_URL})" if REPO_URL else ""))
