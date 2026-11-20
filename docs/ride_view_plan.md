# Ride view plan (3D follow camera)

Agreed 2026-11-20 in a design review. Status: steps 1 to 6 built. Step 7 (viva rehearsal, backup video) is for the user.

## Goal

A "ride along" 3D view for the viva demo. The viewer rides one ETS trip, sees it stop at a red
signal behind a late train, and reads why from a cause caption. It shows RQ1 (delay
propagation) live. It is a demo, not an analysis tool. It must stay convincing for 30 to 60 s.

## Decisions

1. **Track geometry: OpenStreetMap, fetched once offline.** A one-off script pulls the
   `railway=rail` ways along the ETS corridor from Overpass, keeps one clean polyline per
   station-to-station section, and writes `data/processed/track.geojson` (committed).
   Position between two stations = fraction along that section's polyline. Reason: GTFS has no
   `shapes.txt`; splines or straight lines look wrong at cab height. Cost: ODbL attribution in
   the README and on the view.
2. **Rendering: MapLibre GL JS for the ground, three.js custom layer for the train.** Esri
   imagery tiles, no API key, scripts from jsdelivr or cdnjs, one self-contained iframe like
   `live_map.py`. Reason: real surroundings for free, no key in a public app. CesiumJS needs a
   token; pure three.js has an empty world.
3. **Train model: low-poly, built in code.** Six cars of about 23 m, sloped nose on both end
   cars, window band, bogies, pantograph, behind one `makeTrain()` function so a `.glb` can
   replace it later. Livery is a neutral placeholder until reference photos arrive.
4. **Placement: "Ride along" dialog in Control Room** with a trip picker. Default trip = the
   trip with the most knock-on delay in the shown replication. Other trains are drawn too.
   Reason: WebGL loads only when opened; the default trip gives a demo story.
5. **Motion: block-level, from occupancy.** The ride view re-runs the shown replication with
   `record_occupancy=True` and moves each train by sub-block entry times, so a held train
   visibly stops. Signal posts at block boundaries show red or green from occupancy. A caption
   from `increments` names each hold, its cause and the blocking train.
6. **Easing is visual only.** Trains ease in and out of stops; times are exact at block
   boundaries. The view says so, because the model has no traction physics.
7. **Cameras:** chase (default), side, cab, orbit, keys 1 to 4. Heading from the smoothed track
   tangent.
8. **Playback:** 1x, 10x, 60x (default), 300x. "Next hold" jumps to 20 s before the trip's next
   wait and drops to 1x. Scrubber and clock styled like the live map.
9. **Viva reliability:** run locally, rehearse so tiles are cached, record a 60 to 90 s backup
   video. If tiles fail, draw track, stations, signals and trains on a plain dark ground with a
   note.

## Build steps (stop after each for testing)

1. **Pitch spike.** Throwaway HTML: MapLibre at cab height over Esri imagery near Kajang.
   Decide if the MapLibre camera is enough or three.js must drive it. Nothing enters the app.
2. **Track geometry.** `scripts/fetch_track.py` to `data/processed/track.geojson`. Tests: every
   station within 200 m of the track; sections in line_km order; section length within about
   15% of the GTFS km difference. README attribution and an assumption entry.
3. **Ride payload (Python).** `ride_view.payload()`: block trajectories, signal states, hold
   captions, default trip. Tests: times monotonic; every wait in `increments` appears as a stop
   of the same length; default trip has the largest knock-on.
4. **3D scene.** Ground, train, track ribbon, signals, other trains, plain-ground fallback.
5. **Cameras and playback.** Four cameras, speeds, "Next hold", easing with its label.
6. **App wiring.** Dialog in Control Room; entry in `docs/decisions.md`.
7. **Viva prep (user).** Local rehearsal, backup video.

## Step 1 result (2026-11-20)

Spike: MapLibre GL JS 5.6.0 and three.js 0.170.0 from jsdelivr, Esri World Imagery, AWS
Terrarium DEM, Kajang looking toward Serdang, 1280x720.

- **Verdict: the MapLibre camera is enough.** three.js only draws objects.
- 5.6.0 has no free-camera API (`setFreeCameraOptions` is missing). Use
  `map.calculateCameraOptionsFromTo(fromLngLat, fromAlt, toLngLat, toAlt)` then `jumpTo`.
- `maxPitch: 89` is accepted. Cab view asks for 90 and gets 89; the horizon and the style
  `sky` render correctly.
- Chase (25 m up, 170 m back, pitch 84) and side (4 m up, 40 m out) read well. A 6-car
  box train at 23.3 m spacing looks right in scale.
- Cab view: satellite imagery is smeared at 3.5 m eye height. Step 4 needs a near-field
  track ribbon (ballast and two rails) in three.js so the cab view has detail.
- Terrain works and adds real hills on the horizon, but the train sank under it (it was at
  altitude 0). Every three.js object must be lifted by `map.queryTerrainElevation`.
- No console errors.

## Changes from the plan during the build

- Track file lives in `data/snapshots/ets_track_osm.geojson`, not `data/processed/` (that folder
  is generated and git-ignored; the hosted app needs the file committed).
- Ground: Esri dark-grey base tiles instead of satellite imagery, and no terrain (user choice;
  terrain would also lift trains over tunnels).
- Trip picker is inside the 3D view, so changing train does not rerun Streamlit.
- Delay shown is the running sum of the trip's increments plus time already spent in a wait, so it
  climbs while the train stands at a red signal.
- Signals are drawn 12 m past the block boundary so a held train's cab view has them in sight.
- Lines are extended 300 m past each terminus so a train standing at its origin has track.

## Open items

- Class 93 livery reference photos (needed before step 4 is final).
