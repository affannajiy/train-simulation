"""Live line: a self-contained HTML panel that animates one simulated day on a geographic map
(Leaflet, Esri dark-grey tiles) and a track schematic below it.

The whole day is sent to the browser once, so play, pause, speed and scrubbing run without a
Streamlit rerun. Positions are interpolated linearly between timing events, the same rule as
`viz.positions_at`.
"""

from __future__ import annotations

import json

import pandas as pd

from ets_sim import style
from ets_sim.topology import Topology

_KIND_ORDER = {"arr": 0, "pass": 1, "dep": 2}

MAP_PX = 440   # full-size map height
BOARD_PX = 173  # "most delayed now" list: header plus five rows, and its top border
HEIGHT = 1040  # iframe height in px for the full layout (map 440 + schematic 236 + board)
COMPACT_MAP_PX = 280  # inline view, sized to fit a laptop screen; the Expand dialog shows the full one


def height(map_px: int = MAP_PX, board: bool = True) -> int:
    """Iframe height that fits the panel exactly for this map height and board setting."""
    return HEIGHT - (MAP_PX - int(map_px)) - (0 if board else BOARD_PX)


def payload(events: pd.DataFrame, topo: Topology, trip_dirs: dict[str, int], late_min: float,
            start_s: float) -> dict:
    stations = list(topo.stations.values())
    idx = {s.name: i for i, s in enumerate(stations)}
    stops = events[events["kind"].isin(["arr", "dep"])].groupby("station")["trip_id"].nunique()
    st_rows = []
    for s in stations:
        if s.branch_junction:
            j = topo.stations[s.branch_junction]
            x, jx = j.line_km - s.branch_km, idx[j.name]
        else:
            x, jx = s.line_km, -1
        st_rows.append({"n": style.station_name(s.name), "x": round(x, 2), "b": int(bool(s.branch_junction)), "j": jx,
                        "p": int(stops.get(s.name, 0)), "lat": round(s.lat, 5), "lon": round(s.lon, 5)})

    ev = events.assign(_o=events["kind"].map(_KIND_ORDER)).sort_values(["trip_id", "actual_s", "_o"])
    trips = []
    for tid, g in ev.groupby("trip_id", sort=True):
        trips.append({"id": str(tid), "dir": int(trip_dirs.get(tid, 0)),
                      "t": [int(round(v)) for v in g["actual_s"]],
                      "s": [idx[v] for v in g["station"]],
                      "d": [int(round(v)) for v in g["delay_s"]]})
    t_all = events["actual_s"]
    return {"stations": st_rows, "trips": trips, "late": float(late_min), "major": style.MAJOR_LATE_MIN,
            "t0": int(t_all.min()), "t1": int(t_all.max()), "start": int(start_s)}


def html(events: pd.DataFrame, topo: Topology, trip_dirs: dict[str, int], late_min: float,
         start_s: float = 7 * 3600, map_px: int = MAP_PX, board: bool = True) -> str:
    """map_px sets the map height. board=False hides the "most delayed now" list (compact view).
    Size the iframe with height(map_px, board)."""
    data = json.dumps(payload(events, topo, trip_dirs, late_min, start_s), separators=(",", ":"))
    data = data.replace("</", r"<\/")  # a name containing "</script>" cannot end the script block
    tokens = {"BG": style.BG, "PANEL": style.PANEL, "RULE": style.RULE, "TEXT": style.TEXT,
              "MUTED": style.MUTED, "FAINT": style.FAINT, "ORANGE": style.ORANGE, "ON_TIME": style.ON_TIME,
              "MAJOR": style.MAJOR, "ORANGE_HOVER": style.ORANGE_HOVER}
    out = (_TEMPLATE.replace("__DATA__", data).replace("__MAPH__", str(int(map_px)))
           .replace("__BOARD__", "grid" if board else "none"))
    for k, v in tokens.items():
        out = out.replace(f"__{k}__", v)
    return out


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
:root{--bg:__BG__;--panel:__PANEL__;--rule:__RULE__;--text:__TEXT__;--muted:__MUTED__;--faint:__FAINT__;
--amber:__ORANGE__;--green:__ON_TIME__;--red:__MAJOR__;
--mono:"JetBrains Mono",ui-monospace,Menlo,monospace;--sans:"Inter Tight",system-ui,sans-serif}
*{box-sizing:border-box}
html,body{margin:0;background:transparent;color:var(--text);font-family:var(--sans);font-size:13px}
.wrap{border:1px solid var(--rule);border-radius:4px;background:var(--panel);overflow:hidden}
.bar{display:flex;align-items:center;gap:18px;padding:12px 16px;border-bottom:1px solid var(--rule);flex-wrap:wrap}
.clock{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:34px;font-weight:500;color:var(--amber);
 letter-spacing:.02em;line-height:1}
.clock small{font-size:12px;color:var(--muted);margin-left:6px;letter-spacing:.06em}
.lbl{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);margin-bottom:4px}
.ctl{display:flex;gap:6px;align-items:center}
button{font-family:var(--mono);font-size:11px;color:var(--text);background:transparent;border:1px solid var(--rule);
 border-radius:3px;height:30px;min-width:30px;padding:0 10px;cursor:pointer;letter-spacing:.06em}
button:hover{border-color:var(--muted)}
button[aria-pressed="true"]{border-color:var(--amber);color:var(--amber)}
button:focus-visible,input:focus-visible{outline:2px solid var(--amber);outline-offset:2px}
#play{min-width:76px;background:var(--amber);color:var(--bg);border-color:var(--amber);font-weight:600}
#play:hover{background:__ORANGE_HOVER__;border-color:__ORANGE_HOVER__}
.stats{display:flex;gap:22px;margin-left:auto}
.stat .v{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:18px;font-weight:500}
.scrub{padding:8px 16px 0;display:flex;align-items:center;gap:10px}
.scrub span{font-family:var(--mono);font-size:10px;color:var(--faint)}
input[type=range]{flex:1;accent-color:var(--amber);height:24px;margin:0}
#svg{display:block;width:100%}
.trk{stroke:#3A3A3A;stroke-width:2}
.stn{fill:#444}
.stn.maj{fill:#8A8A8A}
.sl{font-family:var(--sans);font-size:10px;fill:var(--muted)}
.sl.maj{fill:var(--text);font-weight:500}
.dl{font-family:var(--mono);font-size:10px;fill:var(--faint);letter-spacing:.08em}
.tr{cursor:pointer}
.tr text{font-family:var(--mono);font-size:10px;font-weight:600}
.tr.hi path{stroke:var(--text);stroke-width:1.5}
.legend{display:flex;gap:16px;padding:0 16px 10px;font-size:11px;color:var(--muted);flex-wrap:wrap}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.board{border-top:1px solid var(--rule);display:__BOARD__;grid-template-columns:1fr 1fr;align-content:start;min-height:172px}
.board h4{grid-column:1/-1;margin:0;padding:10px 16px 6px;font-size:10px;text-transform:uppercase;
 letter-spacing:.12em;color:var(--muted);font-weight:600}
.row{display:grid;grid-template-columns:70px 34px 1fr 74px;gap:8px;padding:5px 16px;font-family:var(--mono);
 font-size:12px;font-variant-numeric:tabular-nums;border-top:1px solid rgba(39,39,42,.7);cursor:default}
.row:hover{background:rgba(255,107,26,.08)}
.row .id{color:var(--amber)}
.row .dir{color:var(--muted)}
.row .nx{color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:var(--sans)}
.row .dl2{text-align:right}
.empty{grid-column:1/-1;padding:10px 16px 14px;color:var(--muted);font-size:12px}
#tip{position:fixed;pointer-events:none;background:var(--bg);border:1px solid var(--rule);border-radius:3px;
 padding:6px 8px;font-family:var(--mono);font-size:11px;line-height:1.5;display:none;z-index:5;white-space:nowrap}
#map{height:__MAPH__px;background:#000;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}
.leaflet-container{font-family:var(--sans);background:#000}
.leaflet-tile-pane{filter:brightness(.75) contrast(1.1)}
.leaflet-control-attribution{background:rgba(0,0,0,.6)!important;color:var(--faint)!important;font-size:9px}
.leaflet-control-attribution a{color:var(--muted)!important}
.leaflet-bar a{background:var(--panel)!important;color:var(--text)!important;border-color:var(--rule)!important}
.leaflet-tooltip{background:var(--bg);color:var(--text);border:1px solid var(--rule);font-family:var(--sans);box-shadow:none}
.leaflet-tooltip-top:before{border-top-color:var(--rule)}
.mlab{font-family:var(--sans);font-size:10px;color:var(--text);font-weight:500;white-space:nowrap;
 text-shadow:0 0 3px #000,0 0 3px #000,0 0 3px #000}
.vlab{padding:10px 16px 6px;font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}
@media (max-width:640px){.board{grid-template-columns:1fr}.stats{margin-left:0}}
</style></head><body>
<div class="wrap">
 <div class="bar">
  <div><div class="lbl">Sim clock</div><div class="clock" id="clock" aria-live="off">--:--:--</div></div>
  <div><div class="lbl">Playback</div><div class="ctl">
   <button id="play" aria-label="Play or pause">PLAY</button>
   <span class="ctl" role="group" aria-label="Speed" id="speeds"></span>
  </div></div>
  <div class="stats">
   <div class="stat"><div class="lbl">Running</div><div class="v" id="nRun">0</div></div>
   <div class="stat"><div class="lbl">Late</div><div class="v" id="nLate" style="color:var(--amber)">0</div></div>
   <div class="stat"><div class="lbl">Worst</div><div class="v" id="worst">-</div></div>
  </div>
 </div>
 <div class="scrub"><span id="lo"></span>
  <input type="range" id="scrub" aria-label="Simulation time" step="30"><span id="hi"></span></div>
 <div class="vlab">Map</div>
 <div id="map" role="img" aria-label="Map of the ETS line with simulated trains"></div>
 <div class="vlab">Schematic</div>
 <svg id="svg" role="img" aria-label="Schematic of the ETS line with simulated trains"></svg>
 <div class="legend">
  <span><i style="background:var(--green)"></i>On time (under <span id="lt"></span> min)</span>
  <span><i style="background:var(--amber)"></i>Late</span>
  <span><i style="background:var(--red)"></i>15+ min late</span>
  <span style="margin-left:auto">Map positions run straight between stations. Hover a train for details.</span>
 </div>
 <div class="board" id="board"></div>
</div>
<div id="tip"></div>
<script>
const D = __DATA__;
const NS = "http://www.w3.org/2000/svg";
const svg = document.getElementById("svg");
const ST = D.stations, TR = D.trips;
const yB = 34, yN = 84, yS = 130, H = 236, PL = 34, PR = 64;
let W = 1000;
const kmMin = Math.min(...ST.map(s => s.x)), kmMax = Math.max(...ST.map(s => s.x));
const X = km => PL + (km - kmMin) / (kmMax - kmMin) * (W - PL - PR);
const Y = (i, dir) => ST[i].b ? yB : (dir === 0 ? yN : yS);
const colorOf = m => m < D.late ? "var(--green)" : (m < D.major ? "var(--amber)" : "var(--red)");
const fmtClock = s => { const d = Math.floor(s / 86400), r = ((s % 86400) + 86400) % 86400;
  const h = Math.floor(r / 3600), m = Math.floor(r % 3600 / 60), x = Math.floor(r % 60);
  return [h, m, x].map(v => String(v).padStart(2, "0")).join(":") + (d ? `<small>+${d} DAY</small>` : ""); };
const hhmm = s => fmtClock(s).slice(0, 5) + (s >= 86400 ? " +1" : "");
const fmtDelay = sec => { const a = Math.abs(sec), m = Math.floor(a / 60), x = Math.round(a % 60);
  return (sec < 0 ? "-" : "+") + m + ":" + String(x).padStart(2, "0"); };
const el = (n, a, p) => { const e = document.createElementNS(NS, n);
  for (const k in a) e.setAttribute(k, a[k]); if (p) p.appendChild(e); return e; };

let now = Math.min(Math.max(D.start, D.t0), D.t1), playing = false, speed = 300, last = null, hiId = null;
const scrub = document.getElementById("scrub");
scrub.min = D.t0; scrub.max = D.t1; scrub.value = now;
document.getElementById("lo").textContent = hhmm(D.t0);
document.getElementById("hi").textContent = hhmm(D.t1);
document.getElementById("lt").textContent = D.late;

// ---------------------------------------------------------------- static layer
let gStatic, gTrains, glyphs = {};
function drawStatic() {
  W = Math.max(svg.clientWidth || 1000, 320);
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("height", H);
  svg.innerHTML = ""; glyphs = {};
  gStatic = el("g", {}, svg);
  el("line", {x1: X(kmMin), x2: X(kmMax), y1: yN, y2: yN, class: "trk"}, gStatic);
  el("line", {x1: X(kmMin), x2: X(kmMax), y1: yS, y2: yS, class: "trk"}, gStatic);
  el("text", {x: 2, y: yN + 3, class: "dl"}, gStatic).textContent = "NB";
  el("text", {x: 2, y: yS + 3, class: "dl"}, gStatic).textContent = "SB";
  el("text", {x: X(kmMin), y: yN - 30, class: "dl"}, gStatic).textContent = "◀ NORTH";
  const s2 = el("text", {x: X(kmMax), y: yN - 30, class: "dl", "text-anchor": "end"}, gStatic);
  s2.textContent = "SOUTH ▶";
  ST.forEach((s, i) => { if (s.b && s.j >= 0) {
    const jx = X(ST[s.j].x);
    el("line", {x1: jx, y1: yN, x2: X(s.x), y2: yB, class: "trk"}, gStatic);
    el("line", {x1: jx, y1: yS, x2: jx, y2: yN, class: "trk", "stroke-dasharray": "2 3"}, gStatic);
  }});
  // labels: greedy by busyness so the busiest stations always get one
  const minGap = 17, order = ST.map((s, i) => i).filter(i => !ST[i].b).sort((a, b) => ST[b].p - ST[a].p);
  const taken = [], maj = new Set(order.slice(0, 8));
  for (const i of order) { const x = X(ST[i].x);
    if (taken.every(t => Math.abs(t - x) >= minGap)) { taken.push(x); ST[i]._lab = true; } else ST[i]._lab = false; }
  ST.forEach((s, i) => {
    const x = X(s.x), y = s.b ? yB : null, m = maj.has(i) || s.b;
    if (s.b) {
      el("rect", {x: x - 2, y: yB - 6, width: 4, height: 12, class: "stn maj"}, gStatic);
      el("text", {x: x - 8, y: yB + 4, class: "sl maj", "text-anchor": "end"}, gStatic).textContent = s.n;
      return;
    }
    const cls = "stn" + (m ? " maj" : ""), th = m ? 14 : 8;
    el("rect", {x: x - 1, y: yN - th / 2, width: 2, height: th, class: cls}, gStatic);
    el("rect", {x: x - 1, y: yS - th / 2, width: 2, height: th, class: cls}, gStatic);
    if (m) el("line", {x1: x, x2: x, y1: yN + 7, y2: yS - 7, stroke: "#27272A", "stroke-width": 1}, gStatic);
    if (s._lab) { const t = el("text", {x: 0, y: 0, class: "sl" + (m ? " maj" : ""),
        transform: `translate(${x - 3},${yS + 16}) rotate(40)`}, gStatic); t.textContent = s.n;
      const ti = el("title", {}, t); ti.textContent = s.n; }
  });
  gTrains = el("g", {}, svg);
  render(true);
}

// ---------------------------------------------------------------- dynamic layer
function at(tr, t) {
  const T = tr.t; if (t < T[0] || t > T[T.length - 1]) return null;
  let lo = 0, hi = T.length - 1;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (T[m] <= t) lo = m; else hi = m - 1; }
  const k = Math.min(lo, T.length - 2), span = T[k + 1] - T[k];
  const f = span > 0 ? Math.min(Math.max((t - T[k]) / span, 0), 1) : 0;
  const a = tr.s[k], b = tr.s[k + 1];
  return { x: X(ST[a].x) + f * (X(ST[b].x) - X(ST[a].x)),
           y: Y(a, tr.dir) + f * (Y(b, tr.dir) - Y(a, tr.dir)),
           d: tr.d[k] + f * (tr.d[k + 1] - tr.d[k]), next: ST[b].n, here: a === b ? ST[a].n : null };
}
const BODY = {0: "M-9,0 L-4,-4.5 L8,-4.5 L8,4.5 L-4,4.5 Z", 1: "M9,0 L4,-4.5 L-8,-4.5 L-8,4.5 L4,4.5 Z"};
let lastBoard = 0, live = [];
function render(force) {
  document.getElementById("clock").innerHTML = fmtClock(now);
  scrub.value = now;
  live = [];
  const seen = new Set();
  for (const tr of TR) {
    const p = at(tr, now); if (!p) continue;
    seen.add(tr.id); live.push({tr, p});
    let g = glyphs[tr.id];
    if (!g) { g = el("g", {class: "tr", "data-id": tr.id}, gTrains);
      g._b = el("path", {d: BODY[tr.dir]}, g);
      g._t = el("text", {"text-anchor": "middle", y: tr.dir === 0 ? -9 : 17}, g);
      g.addEventListener("mousemove", e => tip(e, tr.id)); g.addEventListener("mouseleave", () => tip(null));
      glyphs[tr.id] = g; }
    const mins = p.d / 60, c = colorOf(mins);
    g.setAttribute("transform", `translate(${p.x.toFixed(1)},${p.y.toFixed(1)})`);
    g._b.setAttribute("fill", c); g._t.setAttribute("fill", c);
    g._t.textContent = mins >= D.late ? "+" + Math.round(mins) : "";
    g.classList.toggle("hi", tr.id === hiId);
  }
  for (const id in glyphs) if (!seen.has(id)) { glyphs[id].remove(); delete glyphs[id]; }
  const late = live.filter(l => l.p.d / 60 >= D.late);
  document.getElementById("nRun").textContent = live.length;
  document.getElementById("nLate").textContent = late.length;
  const w = live.reduce((m, l) => Math.max(m, l.p.d), -Infinity);
  const we = document.getElementById("worst");
  we.textContent = live.length ? fmtDelay(w) : "-"; we.style.color = live.length ? colorOf(w / 60) : "";
  renderMap();
  const nowMs = performance.now();
  if (force || nowMs - lastBoard > 250) { lastBoard = nowMs; board(); }
}
function board() {
  const rows = [...live].sort((a, b) => b.p.d - a.p.d).slice(0, 10);
  const b = document.getElementById("board");
  let h = `<h4>Most delayed now</h4>`;
  if (!rows.length) h += `<div class="empty">No trains running at ${hhmm(now)}. Scrub to the service day.</div>`;
  for (const {tr, p} of rows) h += `<div class="row" data-id="${tr.id}"><span class="id">${tr.id}</span>`
    + `<span class="dir">${tr.dir === 0 ? "NB" : "SB"}</span>`
    + `<span class="nx">${p.here ? "at " + p.here : "to " + p.next}</span>`
    + `<span class="dl2" style="color:${colorOf(p.d / 60)}">${fmtDelay(p.d)}</span></div>`;
  b.innerHTML = h;
  b.querySelectorAll(".row").forEach(r => {
    r.onmouseenter = () => { hiId = r.dataset.id; render(); };
    r.onmouseleave = () => { hiId = null; render(); }; });
}
const tipEl = document.getElementById("tip");
function tip(e, id) {
  if (!e) { tipEl.style.display = "none"; return; }
  const l = live.find(v => v.tr.id === id); if (!l) return;
  tipEl.innerHTML = `<b style="color:var(--amber)">${id}</b> ${l.tr.dir === 0 ? "northbound" : "southbound"}<br>`
    + `${l.p.here ? "at " + l.p.here : "next " + l.p.next}<br>delay <b style="color:${colorOf(l.p.d / 60)}">`
    + `${fmtDelay(l.p.d)}</b>`;
  tipEl.style.display = "block";
  tipEl.style.left = Math.min(e.clientX + 12, innerWidth - tipEl.offsetWidth - 4) + "px";
  tipEl.style.top = (e.clientY + 12) + "px";
}

// ---------------------------------------------------------------- geographic map
let map = null, mk = {};
const CSSV = n => getComputedStyle(document.documentElement).getPropertyValue("--" + n).trim();
const hexOf = c => c.replace(/var\(--(\w+)\)/, (_, v) => CSSV(v));
function initMap() {
  if (!window.L) { document.getElementById("map").innerHTML =
    '<div class="empty">Map tiles could not load (offline?). The schematic below still runs.</div>'; return; }
  map = L.map("map", {zoomControl: true, scrollWheelZoom: false, zoomSnap: 0.25});
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", {maxZoom: 16,
    attribution: 'Tiles &copy; Esri, HERE, Garmin, &copy; OpenStreetMap contributors'}).addTo(map);
  const acc = CSSV("amber");
  const main = ST.map((s, i) => i).filter(i => !ST[i].b).sort((a, b) => ST[a].x - ST[b].x);
  L.polyline(main.map(i => [ST[i].lat, ST[i].lon]), {color: acc, weight: 3, opacity: .45, interactive: false}).addTo(map);
  ST.forEach(s => { if (s.b && s.j >= 0) L.polyline([[ST[s.j].lat, ST[s.j].lon], [s.lat, s.lon]],
    {color: acc, weight: 3, opacity: .45, dashArray: "4 5", interactive: false}).addTo(map); });
  const busy = new Set(ST.map((s, i) => i).sort((a, b) => ST[b].p - ST[a].p).slice(0, 10));
  ST.forEach((s, i) => {
    const m = busy.has(i) || s.b;
    L.circleMarker([s.lat, s.lon], {radius: m ? 3.5 : 2.5, color: "#000", weight: 1,
      fillColor: m ? "#FFFFFF" : "#8A8A8A", fillOpacity: 1}).bindTooltip(s.n, {direction: "top"}).addTo(map);
    if (m) L.marker([s.lat, s.lon], {interactive: false, keyboard: false, icon: L.divIcon({className: "",
      iconSize: [0, 0], html: `<div class="mlab" style="transform:translate(8px,-7px)">${s.n}</div>`})}).addTo(map);
  });
  map.fitBounds(L.latLngBounds(ST.map(s => [s.lat, s.lon])), {padding: [20, 20]});
  new ResizeObserver(() => map.invalidateSize()).observe(document.getElementById("map"));
}
function geoAt(tr, t) {
  const T = tr.t; if (t < T[0] || t > T[T.length - 1]) return null;
  let lo = 0, hi = T.length - 1;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (T[m] <= t) lo = m; else hi = m - 1; }
  const k = Math.min(lo, T.length - 2), span = T[k + 1] - T[k];
  const f = span > 0 ? Math.min(Math.max((t - T[k]) / span, 0), 1) : 0;
  const a = ST[tr.s[k]], b = ST[tr.s[k + 1]];
  return [a.lat + f * (b.lat - a.lat), a.lon + f * (b.lon - a.lon)];
}
function renderMap() {
  if (!map) return;
  const seen = new Set();
  for (const {tr, p} of live) {
    const ll = geoAt(tr, now); if (!ll) continue;
    seen.add(tr.id);
    let m = mk[tr.id];
    if (!m) { m = L.circleMarker(ll, {radius: 6, color: "#000", weight: 1.5, fillOpacity: 1}).addTo(map);
      m.on("mousemove", e => tip(e.originalEvent, tr.id)); m.on("mouseout", () => tip(null));
      mk[tr.id] = m; }
    m.setLatLng(ll);
    const hi = tr.id === hiId;
    m.setStyle({fillColor: hexOf(colorOf(p.d / 60)), radius: hi ? 9 : 6, color: hi ? "#FFFFFF" : "#000",
      weight: hi ? 2 : 1.5});
    if (hi) m.bringToFront();
  }
  for (const id in mk) if (!seen.has(id)) { mk[id].remove(); delete mk[id]; }
}

// ---------------------------------------------------------------- playback
const playBtn = document.getElementById("play");
function setPlaying(v) { playing = v; playBtn.textContent = v ? "PAUSE" : "PLAY";
  playBtn.setAttribute("aria-pressed", v); last = null; if (v) requestAnimationFrame(tick); }
function tick(ts) {
  if (!playing) return;
  if (last !== null) { now += (ts - last) / 1000 * speed;
    if (now >= D.t1) { now = D.t1; render(true); setPlaying(false); return; } }
  last = ts; render(); requestAnimationFrame(tick);
}
playBtn.onclick = () => { if (now >= D.t1) now = D.t0; setPlaying(!playing); };
const SPEEDS = [[60, "1"], [300, "5"], [900, "15"], [3600, "60"]];
const sp = document.getElementById("speeds");
for (const [v, l] of SPEEDS) { const b = document.createElement("button");
  b.textContent = l + "×"; b.title = `${l} sim-minute${l === "1" ? "" : "s"} per second`;
  b.setAttribute("aria-pressed", v === speed);
  b.onclick = () => { speed = v; sp.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x === b)); };
  sp.appendChild(b); }
scrub.addEventListener("input", () => { now = +scrub.value; render(true); });
document.addEventListener("keydown", e => { if (e.code === "Space" && e.target.tagName !== "BUTTON") {
  e.preventDefault(); playBtn.click(); } });
let lastW = 0;
initMap();
new ResizeObserver(() => { const w = svg.clientWidth; if (Math.abs(w - lastW) > 2) { lastW = w; drawStatic(); } }).observe(svg);
drawStatic();
if (!matchMedia("(prefers-reduced-motion: reduce)").matches) setPlaying(true);
</script></body></html>
"""
