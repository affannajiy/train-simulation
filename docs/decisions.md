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
