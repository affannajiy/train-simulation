# KTM ETS delay propagation simulator

A discrete event simulation (Python + SimPy) of the KTM Electric Train Service from Padang
Besar to JB Sentral. It studies how one late train spreads delay to others, which sections
and stations generate the most knock-on delay, and how much timetable buffer the service needs.

Research questions (planned FYP):

- **RQ1 Delay propagation.** How do primary delays spread through the ETS corridor, and how
  many trains does one disruption reach?
- **RQ2 Bottlenecks.** Which sections and stations generate the most secondary delay?
- **RQ3 Timetable resilience.** How do buffer time, line speed and service frequency change
  reliability?

Design decisions and the reason for each are in [docs/decisions.md](docs/decisions.md).

## Quick start (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt     # runtime + pytest
pip install -e .
```

```powershell
python -m ets_sim.loader                 # build data/processed/ (the app also does this on first run)
python -m pytest                         # verification tests
python -m ets_sim.experiments            # all experiments, 100 replications each, CSVs in results/
streamlit run app/streamlit_app.py       # the app
```

Useful options:

```powershell
python -m ets_sim.loader --download                   # use today's feed instead of the snapshot
python -m ets_sim.experiments --reps 20 --only buffer speed
python logger/fetch_realtime.py --once                # one realtime poll into data/realtime/
```

## Repository layout

| Path | Purpose |
| --- | --- |
| `config.yaml` | Every parameter. Values marked ASSUMPTION are not confirmed by KTMB data. |
| `src/ets_sim/loader.py` | GTFS static feed to clean ETS stations, trips and stop times |
| `src/ets_sim/topology.py` | Shared railway graph (main line plus Butterworth branch) and fixed sub-blocks |
| `src/ets_sim/train.py` | Trip data, buffer and synthetic-trip transforms |
| `src/ets_sim/events.py` | Event log and causal delay attribution (delay ledger) |
| `src/ets_sim/model.py` | SimPy model |
| `src/ets_sim/metrics.py` | On-time %, delay by station and cause, bottleneck rankings, 95% CI |
| `src/ets_sim/experiments.py` | Seeded replications and the experiments |
| `src/ets_sim/viz.py` | Plotly figures used by the app |
| `src/ets_sim/style.py` | Colour and type tokens, Plotly template, app CSS (theme also in `.streamlit/config.toml`) |
| `src/ets_sim/track.py` | OSM track geometry for the 3D view, station chainages |
| `src/ets_sim/ride_view.py`, `ride_view.html` | "Ride along" 3D follow camera (MapLibre ground, three.js trains and signals) |
| `scripts/fetch_track.py` | One-off: builds the track geometry from OpenStreetMap |
| `src/ets_sim/realtime.py` | Finds logged realtime CSVs locally or on the `realtime-data` branch |
| `app/streamlit_app.py` | Streamlit front end |
| `logger/` | Realtime vehicle-position logger |
| `.github/workflows/realtime_logger.yml` | Hourly logger job |
| `requirements.txt` / `requirements-dev.txt` | Runtime pins (what the host installs) / plus pytest |
| `data/snapshots/` | Pinned GTFS feed used for all results, and the OSM track geometry (committed) |
| `data/raw/`, `data/processed/`, `results/` | Generated, not committed |
| `tests/` | Verification tests |
| `docs/decisions.md` | Design decision record |

## How the model works

**Topology.** The physical railway is built once, independent of any train's stops. Stations
come from the GTFS feed; each station's line km is derived from `shape_dist_traveled` (km 0 at
Padang Besar, about 902 km at JB Sentral). Butterworth is a 9.9 km branch from Bukit Mertajam.
Each station-to-station section is split into equal sub-blocks of at most `max_block_km`,
one `simpy.Resource` of capacity 1 per sub-block per direction (double track, one track per
direction). Each station has a platform resource per direction.

**A train.** Waits for its scheduled departure, may get a primary delay, then requests each
sub-block in turn. It keeps its current block until the next one is free, which is how a
stopped train blocks the one behind it. Trains passing a station do not use a platform. At a
stop the train requests a platform while still holding its approach block.

**Recovery.** On each sub-block, slack = scheduled running time minus the minimum time at line
speed. A late train runs faster, down to that minimum. At a stop a late train can cut its
dwell to `min_dwell_min`. A train never leaves a stop early.

**Attribution.** Every change in a train's delay is recorded with a cause: `primary`,
`knock_on`, `timetable_conflict` or `recovery`. Each train carries a ledger of its delay by
root cause. When train B waits behind train A, the wait (up to A's own delay) inherits A's root
causes in proportion; any remainder is a `timetable_conflict`, meaning the timetable itself
does not leave room. The ledger always equals the train's delay (tested), so totals never
double count a delay as it travels along the line.

**Statistics.** Replication r uses seed `base_seed + r`. Inside a run each train has its own
random stream keyed by (seed, trip_id), so different scenarios meet the same disturbances on
the same trains (common random numbers). Results are means with 95% confidence intervals.

## Experiments

| Name | What changes | Output |
| --- | --- | --- |
| Baseline | Nothing; also a run with primary delays off | `results/baseline.csv` |
| Buffer sweep | 0, 2, 4, 6 extra minutes per journey, spread by running time | `results/buffer_sweep.csv` |
| Bottleneck finder | Ranks sections, platforms, stations and trains by secondary delay | `results/bottleneck_*.csv` |
| Line speed | 140 vs 160 km/h (idealised sensitivity, not a prediction) | `results/speed_comparison.csv` |
| Frequency stress | Adds synthetic trips copied from existing patterns | `results/frequency_stress.csv` |
| Block length | `max_block_km` 2.5, 5, 10 (sensitivity to the block assumption) | `results/block_length.csv` |
| Benchmark | Recovery model: line speed (v1) vs UIC 451-1 and ProRail running time supplements; ETS timetable supplements per section | `results/recovery_benchmark.csv`, `results/timetable_supplements.csv` |
| Incident replay | A real incident from `replays` in `config.yaml` as a section outage; start and duration fitted to reported delays | `results/replay_<name>_*.csv` |

Run the replays with `python -m ets_sim.replay` (add `--reps 20` for a faster run).

**Section outages.** A `SectionOutage` closes the track between two stations (one or both
directions) for a set time, like an overhead line or signalling failure. At the start it takes
every sub-block of the section ahead of any queuing train. A train already inside the section
stops at the next sub-block. Waiting for a closed block is recorded as cause `outage` with root
id `O:<name>`, and trains held up behind it inherit that root as `knock_on`.

## Realtime logger

The workflow `.github/workflows/realtime_logger.yml` starts every hour, polls the KTMB
vehicle-position feed every 60 s for 55 min, and makes one commit to the orphan branch
`realtime-data` (one CSV per UTC day). It never writes to `main`. All fields are kept as
delivered, plus a `bad_position` flag.

- The repository must be public for the hourly job to stay inside free Actions minutes.
- Run it once by hand from the Actions tab (`workflow_dispatch`) to create the branch.
- GitHub disables scheduled workflows after 60 days without repository activity. Re-enable it
  from the Actions tab if that happens.

To view the logs locally (files are git-ignored on `main`):

```powershell
git fetch origin realtime-data
git restore --source origin/realtime-data --worktree -- data/realtime
```

When `data/realtime/` is empty, the app reads the last `realtime_remote_days` days straight from
the branch at `raw.githubusercontent.com/<realtime_repo>/realtime-data/data/realtime/`. Set
`data.realtime_repo` in `config.yaml` to the repo's `owner/name`. No token is needed for a
public repo.

## Deployment

The app runs on Streamlit Community Cloud (free); GitHub Actions runs the logger. GitHub Pages
is not used: it serves static files only and cannot run a Python server.

1. Push to a public GitHub repo and set `data.realtime_repo` in `config.yaml`.
2. Repo Settings, Actions, General, Workflow permissions: **Read and write**. Then run
   `realtime-logger` once from the Actions tab.
3. Repo Settings, Code security: turn on **Secret scanning** and **Push protection**.
4. share.streamlit.io, Create app, from this repo: branch `main`, main file
   `app/streamlit_app.py`, Advanced settings, Python 3.13. No secrets are needed.

The host installs `requirements.txt` only. The app adds `src/` to the import path itself, and
builds `data/processed/` from the committed snapshot on first load. A free app sleeps after a
few days without visitors and takes about 30 s to wake.

No API keys: both data.gov.my feeds are public, and the workflow uses the built-in
`GITHUB_TOKEN`. Never commit `.streamlit/secrets.toml` or `.env` (both are git-ignored).

## Findings so far

Data (feed of 2026-11-20):

- One ETS route, 94 trips per day; after cleaning 91 trips and 50 stations.
- Three exact duplicate trips (9621, 9624, 9625) were dropped. Four pairs leave the same
  station at the same minute (9510/9524, 9514/9532, 9515/9533, 9256/9278); they are kept.
- Trip 9628 has distances about 10.8 km inconsistent with the other trips (reported, kept).
- The realtime feed does contain ETS trainsets (label such as `ETS303`), but `trip_id`
  disagreed with the scheduled position for 6 of 7 vehicles, one vehicle reported (0, 0), every
  vehicle reported speed 90.0, and positions were unchanged after 14 minutes. Treat it as
  unreliable until weeks of logs show otherwise.

Model, 100 replications, placeholder delay parameters (full tables in `results/`):

| Scenario | On time, all stops | On time at destination | Avg destination delay |
| --- | --- | --- | --- |
| No primary delays | 93.1% | 85.7% | 4.9 min |
| Baseline | 93.3% (93.2 to 93.5) | 86.8% | 4.5 min |
| Buffer +6 min | 93.2% (93.1 to 93.4) | 86.7% | 4.5 min |
| 160 km/h | 94.3% (94.1 to 94.4) | 89.3% | 3.5 min |
| +40 synthetic trips | 89.5% (89.3 to 89.6) | 81.0% | 7.8 min |
| 2.5 km blocks | 94.2% | 88.9% | 3.1 min |
| 10 km blocks | 92.7% | 86.5% | 4.9 min |

- **The timetable itself dominates.** With every primary delay switched off, the published
  timetable still produces about 1,000 minutes of `timetable_conflict` delay per day under 5 km
  blocks. The worst sections are Kepong Sentral to Kuala Lumpur, Batang Kali to Rawang and
  Slim River to Tanjong Malim, plus the four same-minute pairs.
- **Random delays slightly improve on-time %** (93.3% vs 93.1%). A late departure often splits
  a same-minute pair or a tight follow-on, which removes a conflict. This shows how much the
  results depend on those pairs, which may be data errors (see decision 16).
- **The buffer sweep barely moves on-time performance.** At 140 km/h the timetable already
  holds about 7,600 train-minutes of theoretical slack, so late trains recover quickly, and the
  remaining lateness comes from conflicts, which extra running time does not remove. The slack
  definition (minimum time at full line speed on every section) is optimistic; real speed
  restrictions make the usable slack smaller.
- **Frequency stress** never crosses the 80% target up to +60 trips; on-time % at all stops falls
  from 93.3% to about 89.5%. The +60 case is not worse than +40 because synthetic trips copy
  patterns at fixed offsets, so where they land matters more than how many there are.
- **Block length** changes results by about 1.5 points between 2.5 km and 10 km blocks, so the
  5 km assumption matters but does not change the conclusions.
- **Trains that hold others up most** are the slow overnight Hat Yai trips (1004/1005) and the
  short Ipoh and Batu Gajah services that share the busy Rawang to KL section.

International benchmark (full write-up in [docs/benchmarking.md](docs/benchmarking.md)):

- Against a constant 140 km/h, the ETS timetable holds a median 37% running time supplement;
  UIC 451-1 and ProRail plan 3-7%. So the line-speed recovery model is too optimistic.
- With a UIC-style supplement instead (`operations.recovery_model: supplement`), on time at
  destination falls from 86.8% to about 80%, close to KTMB's reported 80-86% (CNY 2025, 2026)
  and ÖBB long-distance (81.6%).
- Under that model a +6 min buffer raises on time at destination from 79.7% to 80.5% (CIs do
  not overlap). The flat buffer result above is an artefact of the idealised slack.
- Every run now also reports on-time % at 1, 3, 5, 10 and 15 min (`benchmark_thresholds_min`).

Incident replay: Tiroi to Seremban overhead line outage, 14 Jun 2026 (source and reported
delays in `config.yaml`, background in [docs/literature_review.md](docs/literature_review.md)):

- **Best fit:** Labu to Seremban closed both ways from 10:20 for 235 min (to 14:15). Mean
  absolute error over the 8 reported trains is 15.6 min, bias +3.1 min. Errors range from
  +36 min (9442) to -17.5 min (9428). The start and duration are fitted, not reported, so
  this is a calibration, not an independent validation.
- **The model reaches all 8 reported trains and 4 more:** 9510 (same-minute pair with 9524,
  see decision 16), 9574, and the KL to Ipoh/Batu Gajah services 9052 and 1054 (small delays).
- **Knock-on is about the size of the outage itself.** With primary delays on (100 reps),
  the outage gives about 563 train-minutes of direct delay and about 619 (613 to 626) of
  knock-on: 1.10 minutes of knock-on per minute of direct outage delay, across 12 trains.
- Caveat: the model uses the 2026-11-20 timetable. The June timetable may have differed.

## Assumptions

Every value below is in `config.yaml` with an ASSUMPTION comment. None is confirmed by KTMB.

| Parameter | Value | Reason |
| --- | --- | --- |
| `network.max_block_km` | 5 km | Typical order for main-line fixed blocks. One block per station section (up to 69 km) would invent knock-on delay. Tested at 2.5 and 10 km. |
| `platforms.default_per_direction` | 2 | Real counts unknown. Overrides go in `platforms.overrides`. |
| `operations.min_dwell_min` | 1 min | Shortest realistic intermediate stop for a late train. |
| `primary_delay.*` | p_origin 0.30, median 3 min, sigma 0.8; p_stop 0.05, median 1.5 min, sigma 0.8; cap 60 min | Placeholders until fitted from realtime logs. |
| `experiments.frequency_offset_min` | 20 min | Synthetic trips copy an existing pattern shifted by this. |
| `experiments.on_time_target_pct` | 80% | Line where the stress test says the network stops coping. |
| Line speed | 140 km/h service, 160 km/h design | Class 93 figures; 160 km/h is an idealised scenario only. |
| Track | Double track, one direction per track | Brief decision. |
| `operations.running_supplement_pct`, `supplement_min_per_100km` | 3%, 1 min/100 km (used when `recovery_model: supplement`) | UIC 451-1 figure for multiple units up to 140 km/h, from secondary sources. Benchmarked at 4% and ProRail 7%. |
| `replays.*.both_directions` | true for the Tiroi-Seremban replay | An overhead line outage cuts power to both tracks. |
| Ride along track layout | Two tracks 4.5 m apart either side of the OSM line, left-hand running; signals at block boundaries, 2 aspects | Display only. OSM maps one line; real track spacing and signal positions are not published. |
| Replay comparison | Reported delay vs peak simulated delay | Reports give delay "as of" a time, not where on the journey. |

## Limitations

- ETS only. Komuter, Intercity and Shuttle Selatan share parts of the line, so v1 understates
  conflicts. The loader takes a route list, so they can be added later.
- Fixed-block model with uniform speed per stop-to-stop leg; no signalling sections, junction
  conflicts, speed restrictions or train physics.
- No rolling-stock linking: a late arrival does not delay that trainset's next trip (GTFS has
  no `block_id`).
- One service day; overnight trains from the previous day are not carried over.
- Trains start at their origin without occupying a platform; destinations free the platform on
  arrival.
- Hat Yai trips (1004/1005) are cut at Padang Besar.
- The Live line map draws straight lines between stations. The Ride along 3D view uses the real
  alignment from OpenStreetMap, but for display only: the model still uses GTFS line km, and the
  easing into and out of stops in that view is visual (the model has no acceleration).
- Delay distributions are assumed, not calibrated, so results describe the model's behaviour,
  not measured KTMB performance (verification, not validation).

## Ride along (3D view)

Control Room, **Ride along**: follow one train in 3D with chase, side, cab and orbit cameras
(keys 1 to 4). It starts on the train with the most knock-on delay. **Next hold** jumps to the
next time that train stops at a red signal, and a caption names the cause and the train ahead.
Trains move signal by signal from the model's block occupancy log, so a held train really
stands at the signal for the simulated time. The view needs internet for its map tiles and
libraries; for a demo, run locally and open it once beforehand so the tiles are cached.

Track geometry (c) OpenStreetMap contributors, available under the Open Database License (ODbL
1.0). Map tiles (c) Esri. To rebuild the geometry: `python scripts/fetch_track.py`.

## Contributing notes

- Plain hyphens only in docs and comments. No emoji.
- New assumptions go in `config.yaml` with an ASSUMPTION comment and in the table above.
