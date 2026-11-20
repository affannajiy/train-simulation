# Design decisions

Agreed 2026-11-20 during the design review. Each entry: decision, then the reason in one line.
Values marked ASSUMPTION go into `config.yaml` with the same label and into the README
"Assumptions" section.

## Scope

1. **Purpose: planned FYP.** Research questions drive the design: RQ1 delay propagation,
   RQ2 bottlenecks, RQ3 timetable resilience. Reason: retrofitting attribution and
   seeded replications later is the expensive path.
2. **Engine and level of detail are fixed by the brief:** Python + SimPy, macroscopic,
   double track, one track per direction, no train physics, ETS only in v1, Streamlit + Plotly.
3. **Komuter, Intercity (ERT, SH) and Shuttle Selatan share parts of the ETS corridor but are
   out of scope for v1.** Reason: brief decision. Consequence: v1 understates conflicts on
   shared track; stated as a limitation. The loader filters by a route list in config so
   other services can be added later.

## Data findings (feed downloaded 2026-11-20)

4. Static GTFS has one ETS route (`route_id=ETS`), 94 daily trips, 51 stops, service `ets`
   daily. No Platinum/Gold/Express label exists in the feed, so the model does not use tiers.
5. No `shapes.txt`. `shape_dist_traveled` is present on every row, measured from each trip's
   own origin. Line km per station is derived by offsetting each trip against a reference trip.
6. `direction_id` 0 = northbound, 1 = southbound.
7. GTFS times exceed 24:00 (latest 33:50:00). All times are stored as integer seconds from
   the start of the service day.
8. Realtime vehicle-position feed contains ETS vehicles (7 entities at 18:56, all ETS).
   `vehicle.label` is the trainset (for example `ETS303`). `trip_id` matches static trip IDs
   but was inconsistent with scheduled position for 6 of 7 vehicles; one vehicle reported
   (0, 0); speed was 90.0 for all and current_status was not set. A second poll 14 minutes
   later returned identical positions. Treated as unreliable until proven.

## Realtime logger

9. **Log raw, validate later.** Keep every field as delivered (trip_id, vehicle id, label,
   feed timestamp, vehicle timestamp, observed-at timestamp, lat, lon, speed, status, stop_id)
   plus a `bad_position` flag. Matching trainsets to trips is a later notebook. Validation
   against real data is a stretch goal, not an FYP promise.
10. **Public repo. Hourly workflow, polling every 60 s for about 55 min, one commit per run to
    an orphan `realtime-data` branch**, one CSV per day. Reason: `main` stays owned by the user;
    60 s polling catches far more station events than the 5 min cron. GitHub disables scheduled
    workflows after 60 days of repo inactivity; documented in the README.

## Topology

11. **Blocks are sub-blocks of at most `max_block_km` (ASSUMPTION, default 5 km).** Each
    station-to-station section is split into equal sub-blocks, each a `simpy.Resource(1)`.
    Scheduled running time is spread over sub-blocks in proportion to length. Reason: one block
    per section (up to 69 km) would invent knock-on delay. Block length is also a sensitivity
    parameter.
12. **The network is a small graph, not a line.** Main line Padang Besar to JB Sentral plus the
    Bukit Mertajam to Butterworth branch. A plain adjacency dict, no networkx.
13. **Hat Yai trips (1004/1005) are truncated at Padang Besar** and flagged `international`.
    They are excluded from dwell-recovery analysis because of the border dwell.
14. **Platforms:** `simpy.Resource` per station per direction, default 2 (ASSUMPTION), with
    per-station overrides in config. A train that cannot get a platform keeps holding its
    approach sub-block. Trains passing without stopping do not request a platform.

## Timetable quality

15. Exact duplicate trips (for example 9584/9624) are dropped, keeping the lower trip_id, and
    listed in `data/processed/data_quality.csv`. Nothing is dropped silently.
16. Same-minute departures with different timings (for example 9510/9524, 9514/9532) are kept.
    Delay they cause is labelled `timetable_conflict`, separate from `primary` and `knock_on`.

## Delay model

17. **Primary delays at origin and at every intermediate departure.** Two Bernoulli + truncated
    lognormal draws, all ASSUMPTION placeholders: `p_origin 0.30`, median 3.0 min, sigma 0.8;
    `p_stop 0.05`, median 1.5 min, sigma 0.8; cap 60 min. To be refitted from logged data.
18. **Recovery.** Running slack per sub-block = scheduled time minus minimum time at line speed
    (140 km/h default, 160 km/h option). Where scheduled time is below minimum time, slack is
    clamped to 0 and the count is reported. Dwell can shrink to `min_dwell` (ASSUMPTION, 1 min
    at intermediate stops). A train never departs before its scheduled time.
19. **Attribution.** Every event records `delay_increment`, `cause`, `blocking_train_id` and
    `primary_delay_id`. Each train carries a delay ledger keyed by root cause id. A knock-on
    wait inherits the root ids of the blocking train in proportion to that train's ledger.
    Recovery reduces the ledger proportionally. Reason: no double counting, and every minute
    traces back to a root disturbance.
20. **No rolling-stock linking in v1.** Each trip is independent; a late arrival does not delay
    the trainset's next departure. Reason: GTFS has no `block_id`. Possible v2: infer trainset
    rosters from realtime labels. Stated as a limitation.
21. **One simulated service day** from the first departure to the last arrival. Overnight
    trains from the previous day are not carried over. Stated as a limitation.

## Metrics and experiments

22. Late = more than `late_threshold_min` (default 5) behind schedule. On-time % is reported
    at all stops and separately at the destination.
23. **Replications:** 100 per scenario (configurable), 95% confidence intervals.
    **Common random numbers:** each train gets its own random stream from a `SeedSequence`
    keyed by (replication seed, trip_id), so the same train meets the same disturbances in
    every scenario.
24. Buffer sweep (0, 2, 4, 6 min) is journey-level, spread over sections in proportion to
    scheduled running time. Report on-time % and the scheduled journey-time increase together.
25. Speed experiment 140 vs 160 km/h is labelled an idealised sensitivity analysis, not a
    prediction. Report total recoverable slack and destination delay.
26. Frequency stress test inserts synthetic trips copied from existing patterns at a
    configurable offset. The on-time target is a config parameter, not a hard-coded collapse point.
27. Extra sensitivity check: `max_block_km`.

## Engineering

28. `pyproject.toml` with a `src/ets_sim` package installed editable, so the app, notebooks and
    tests import the same code. `requirements.txt` with pinned versions. Python 3.12+.
29. `pytest` verification tests, starting with: a zero-disruption run reproduces the timetable
    exactly except labelled `timetable_conflict`; one injected delay on an empty line is
    recovered by exactly the computed slack; two trains on one block are never inside it at once.
30. The GTFS feed changes daily. The loader saves a dated copy under `data/raw/` (git-ignored)
    and one pinned snapshot under `data/snapshots/` (committed, about 47 KB) that all FYP
    results use. Processed outputs record the feed date.
31. No commits or pushes by the assistant. The user commits.
32. Plain hyphens only in docs and comments, no em or en dashes, no emoji.

## Incidents and replays

Added 2026-11-20 after the literature review (`docs/literature_review.md`).

33. **Section outage as an incident type.** `SectionOutage` closes the track between two
    stations, one or both directions, for a set time. It is separate from the small random
    primary delays. Reason: 2026 KTMB incidents (overhead line, signalling, cable theft) close
    a section for hours, which the lognormal primary delays capped at 60 min cannot produce.
34. **Outage priority.** Block and platform resources are `simpy.PriorityResource`. The outage
    requests with priority -1 so it goes ahead of queuing trains; trains share priority 0, so
    the order between trains is unchanged. An outage never removes a train already in a block.
35. **New cause `outage`** with root id `O:<name>`. A train waiting for a closed block gets
    the whole wait as `outage`, including any part spent queuing behind another train before
    the outage began (simplification). Trains behind inherit the root as `knock_on`.
36. **Replays fit start and duration.** News reports give the trains and their delays but not
    when the outage began or how long it lasted. A grid search (5 min steps) with primary delays
    off picks the pair with the lowest mean absolute error against peak simulated delay.
    Reason: the only honest use of the data we have. It is calibration, not validation.
37. **First replay: Tiroi to Seremban, 14 Jun 2026.** Tiroi is not an ETS stop, so the outage
    closes the ETS section Labu to Seremban. Both directions (ASSUMPTION). Uses the 2026-11-20
    timetable; all 8 reported trains exist in it.

## International benchmarking

Added 2026-11-20 (`docs/benchmarking.md`).

38. **Benchmark set:** Japan, Switzerland, Austria, the Netherlands, South Korea. Hong Kong and
    Singapore rank high on rail quality but through urban metros, so they are not compared
    with a 900 km intercity corridor.
39. **Punctuality profile.** Besides the 5 min headline, every run reports on-time % at
    `benchmark_thresholds_min` (1, 3, 5, 10, 15). Reason: SBB and NS use 3 min, NS 10 min for
    large delay, KTMB publishes no threshold.
40. **Second recovery model, `supplement`.** Minimum running time = published running time with
    a UIC 451-1 style supplement removed (pct of minimum plus minutes per 100 km), never faster
    than line speed. Default stays `line_speed` until the user decides to switch, because the
    switch changes every reported number. Reason: against line speed the ETS timetable shows a
    median 37% supplement, where real railways plan 3-7%, so v1 overstates recovery.
41. **The supplement minimum is fixed from the published timetable** (`Trip.base_run_s`), so a
    buffer added in an experiment stays recoverable slack instead of raising the minimum too.

## Ride along (3D view)

Added 2026-11-20. Full plan and spike results: `docs/ride_view_plan.md`.

42. **A demo view for the viva, not an analysis tool.** It shows RQ1 live: one train held at a red
    signal behind a late train, with the cause named.
43. **Track geometry from OpenStreetMap, fetched once and committed**
    (`data/snapshots/ets_track_osm.geojson`). Shortest rail path between consecutive stations;
    sidings cost more; a station may use any track node near it, because the two tracks of the
    double line are often joined only far away. Reason: GTFS has no `shapes.txt`. Display only:
    a model position (fraction along a section by GTFS km) maps to the same fraction along the
    OSM line, so the model stays the single source of truth.
44. **MapLibre GL JS for the ground, three.js for objects, plain Esri dark-grey tiles** (no
    satellite imagery, user choice; no terrain, because OSM tunnels and bridges would not match a
    DEM). No API keys. The MapLibre camera, set with `calculateCameraOptionsFromTo`, reaches
    pitch 89, enough for a cab view.
45. **Block-level motion.** `SimResult.occupancy` gained `t_req` (when the train reached the
    signal), so the view knows how long a train stood at each signal. Recorded only with
    `record_occupancy=True`; results are unchanged.
46. **Easing into and out of stops is visual only**, and the view says so. Times at each block
    boundary are exact.
47. **Low-poly ETS built in code**, six cars, placeholder livery until reference photos are
    supplied. One `makeTrain()` function, so a `.glb` model can replace it.
