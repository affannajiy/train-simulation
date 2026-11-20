"""Visual tokens, the Plotly template and small HTML pieces for the control-centre look.

One source of truth for colour and type. `.streamlit/config.toml` repeats the same values
because Streamlit reads its theme from there; change both together.
"""

from __future__ import annotations

import html

import plotly.graph_objects as go
import plotly.io as pio

# ------------------------------------------------------------------ tokens

BG = "#0D0D0D"        # page canvas
PANEL = "#141414"     # inset panels (KPI board, hover labels), between canvas and card
PANEL_2 = "#1A1A1A"   # elevated surfaces: cards, sidebar widgets
RULE = "#27272A"      # borders and dividers
TEXT = "#FFFFFF"      # headings and key figures
BODY = "#D4D4D8"      # paragraphs; off-white avoids halation on black
MUTED = "#8E8E93"     # captions, labels, placeholders
FAINT = "#5C5C61"

ORANGE = "#FF6B1A"        # accent, primary button, and "minor late"
ORANGE_HOVER = "#FF8542"  # primary button hover, badge text
LINK = "#FF7A2F"          # inline links
ON_ORANGE = "#0D0D0D"     # text on an orange fill
BTN_2 = "#2A2A2A"         # secondary button fill
BTN_2_BORDER = "#3F3F46"  # secondary button border
ORANGE_GLOW = "rgba(255,107,26,0.2)"   # input focus ring
ORANGE_TINT = "rgba(255,107,26,0.15)"  # badge / tag fill
ON_TIME = "#F2F2F2"  # on time: white
MAJOR = "#DC2626"    # major late (15+ min): deep red so it never reads as orange
NORTH = ORANGE       # northbound (direction 0): orange
SOUTH = "#FFFFFF"    # southbound (direction 1): white
PLANNED = "#555555"
SOFT_ORANGE = "#FFB27A"  # secondary orange for a third series

SANS = "Inter Tight, Inter, system-ui, sans-serif"
MONO = "JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, monospace"

MAJOR_LATE_MIN = 15.0  # red from here; amber between the late threshold and this


def delay_color(delay_min: float, late_min: float) -> str:
    if delay_min < late_min:
        return ON_TIME
    return ORANGE if delay_min < MAJOR_LATE_MIN else MAJOR


# ------------------------------------------------------------------ Plotly template

def _template() -> go.layout.Template:
    axis = dict(gridcolor="rgba(255,255,255,0.07)", zerolinecolor="rgba(255,255,255,0.14)",
                linecolor=RULE, tickcolor=RULE, ticks="outside", ticklen=4,
                tickfont=dict(family=MONO, size=11, color=MUTED),
                title=dict(font=dict(family=SANS, size=12, color=MUTED), standoff=8))
    t = go.layout.Template()
    t.layout = go.Layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=SANS, size=12, color=BODY),
        colorway=[ORANGE, SOUTH, SOFT_ORANGE, MUTED, MAJOR, FAINT],
        xaxis=axis, yaxis=axis,
        margin=dict(l=8, r=8, t=8, b=8),
        hoverlabel=dict(bgcolor=PANEL, bordercolor=RULE, font=dict(family=MONO, size=12, color=TEXT)),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=MUTED, size=11), orientation="h",
                    yanchor="bottom", y=1.0, xanchor="left", x=0),
        bargap=0.35,
    )
    t.data.bar = [go.Bar(marker=dict(color=ORANGE, line=dict(width=0)))]
    t.data.histogram = [go.Histogram(marker=dict(color=ORANGE, line=dict(width=0)))]
    return t


pio.templates["ets"] = _template()
pio.templates.default = "ets"


# ------------------------------------------------------------------ CSS

CSS = f"""
<style>
/* Tabular numerals everywhere numbers appear. */
[data-testid="stMetricValue"], [data-testid="stDataFrame"], .ets-mono {{
  font-family: {MONO}; font-variant-numeric: tabular-nums;
}}
.block-container {{ padding-top: 1.2rem; max-width: 1500px; }}
header[data-testid="stHeader"] {{ background: transparent; }}

/* Top bar */
.ets-top {{ display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap;
  padding: 0 0 14px; margin-bottom: 4px; border-bottom: 1px solid {RULE}; }}
.ets-brand {{ display:flex; align-items:center; gap:12px; }}
.ets-mark {{ width:10px; height:28px; background:{ORANGE}; border-radius:1px; }}
.ets-title {{ font-weight:600; font-size:18px; letter-spacing:-0.01em; color:{TEXT}; line-height:1.1; }}
.ets-sub {{ font-size:12px; color:{MUTED}; }}
.ets-chips {{ display:flex; gap:6px; flex-wrap:wrap; }}
.ets-chip {{ font-family:{MONO}; font-size:11px; color:{MUTED}; border:1px solid {RULE};
  padding:3px 8px; border-radius:3px; white-space:nowrap; }}
.ets-chip b {{ color:{TEXT}; font-weight:500; }}

/* Section header: label + rule */
.ets-sec {{ display:flex; align-items:baseline; gap:10px; margin: 18px 0 8px; }}
.ets-sec h3 {{ margin:0; padding:0; font-size:13px; font-weight:600; text-transform:uppercase;
  letter-spacing:0.08em; color:{TEXT}; }}
.ets-sec > span:not(.ets-help) {{ font-size:12px; color:{MUTED}; }}
.ets-sec::after {{ content:""; flex:1; border-bottom:1px solid {RULE}; transform: translateY(-4px); }}

/* "How to read" tooltip next to a section title. Opens on hover and on keyboard focus. */
.ets-help {{ position:relative; align-self:center; display:inline-flex; align-items:center; justify-content:center;
  width:16px; height:16px; border:1px solid {BTN_2_BORDER}; border-radius:50%; font-family:{MONO}; font-size:10px;
  font-weight:600; color:{MUTED}; cursor:help; flex:none; }}
.ets-help:hover, .ets-help:focus-visible {{ color:{ORANGE}; border-color:{ORANGE}; outline:none; }}
.ets-tip {{ display:none; position:absolute; top:22px; left:-8px; z-index:1000; width:min(340px, 80vw);
  padding:10px 12px; background:{PANEL}; border:1px solid {RULE}; border-radius:4px;
  box-shadow:0 8px 24px rgba(0,0,0,.5); font-family:{SANS}; font-size:12px; font-weight:400; line-height:1.5;
  color:{BODY}; text-transform:none; letter-spacing:0; white-space:normal; }}
.ets-tip b {{ display:block; color:{TEXT}; font-size:11px; text-transform:uppercase; letter-spacing:.08em;
  margin-bottom:4px; }}
.ets-tip p {{ margin:0 0 6px; }}
.ets-tip p:last-child {{ margin:0; }}
.ets-help:hover .ets-tip, .ets-help:focus .ets-tip {{ display:block; }}
/* Let the tooltip spill out of the markdown block instead of being clipped. */
[data-testid="stMarkdownContainer"]:has(.ets-help), [data-testid="stElementContainer"]:has(.ets-help) {{
  overflow:visible; z-index:5; }}
/* The open one goes above later section headers, which share z-index 5. */
[data-testid="stElementContainer"]:has(.ets-help:hover), [data-testid="stElementContainer"]:has(.ets-help:focus),
[data-testid="stColumn"]:has(.ets-help:hover), [data-testid="stColumn"]:has(.ets-help:focus),
[data-testid="stHorizontalBlock"]:has(.ets-help:hover), [data-testid="stHorizontalBlock"]:has(.ets-help:focus) {{
  z-index:1000; position:relative; }}

/* Expand dialog: use nearly the whole screen for the live line. */
[data-testid="stDialog"]:has(.st-key-live_full) div:has(> [role="dialog"]),
[data-testid="stDialog"]:has(.st-key-live_full) [role="dialog"] {{ width:min(96vw, 1800px); max-width:96vw; }}

/* Departure-board KPI strip */
.ets-board {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  border:1px solid {RULE}; border-radius:4px; background:{PANEL}; overflow:hidden; }}
.ets-kpi {{ padding:12px 16px; border-right:1px solid {RULE}; }}
.ets-kpi:last-child {{ border-right:0; }}
.ets-kpi .l {{ font-size:11px; text-transform:uppercase; letter-spacing:0.08em; color:{MUTED}; }}
.ets-kpi .v {{ font-family:{MONO}; font-variant-numeric:tabular-nums; font-size:28px; font-weight:500;
  color:{ORANGE}; line-height:1.25; margin-top:2px; }}
.ets-kpi .v small {{ font-size:14px; color:{MUTED}; margin-left:3px; }}
.ets-kpi .ci {{ font-family:{MONO}; font-size:11px; color:{FAINT}; }}

/* Tabs: underline style, uppercase labels */
.stTabs [data-baseweb="tab-list"] {{ gap: 22px; border-bottom: 1px solid {RULE}; }}
.stTabs [data-baseweb="tab"] {{ padding: 8px 0; }}
.stTabs [data-baseweb="tab"] p {{ font-size:12px; font-weight:600; text-transform:uppercase;
  letter-spacing:0.08em; }}
.stTabs [aria-selected="false"] p {{ color:{MUTED}; }}

/* Sidebar */
section[data-testid="stSidebar"] .ets-side-title {{ font-size:11px; text-transform:uppercase;
  letter-spacing:0.1em; color:{MUTED}; margin: 2px 0 6px; }}
.ets-tag {{ font-family:{MONO}; font-size:10px; color:{ORANGE_HOVER}; background:{ORANGE_TINT};
  padding:0 4px; border-radius:2px; margin-left:4px; vertical-align:1px; }}
.ets-note {{ font-size:12px; color:{MUTED}; line-height:1.5; }}
.ets-note b {{ color:{TEXT}; font-weight:500; }}

/* About tab: bound the line length for reading. */
.st-key-about {{ max-width: 860px; }}
.st-key-about li, .st-key-about p {{ line-height: 1.6; }}

/* Headings white, body silver. */
h1, h2, h3, h4, h5, h6 {{ color:{TEXT}; }}

/* Buttons: black text on bright orange; dark ghost for secondary. */
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"],
.stDownloadButton button[kind="primary"] {{
  background:{ORANGE}; border-color:{ORANGE}; color:{ON_ORANGE}; font-weight:600; }}
.stButton button[kind="primary"] p, .stFormSubmitButton button[kind="primary"] p,
.stDownloadButton button[kind="primary"] p {{ color:{ON_ORANGE}; }}
.stButton button[kind="primary"]:hover, .stFormSubmitButton button[kind="primary"]:hover,
.stDownloadButton button[kind="primary"]:hover {{
  background:{ORANGE_HOVER}; border-color:{ORANGE_HOVER}; color:{ON_ORANGE}; }}
.stButton button[kind="secondary"], .stFormSubmitButton button[kind="secondary"],
.stDownloadButton button[kind="secondary"] {{
  background:{BTN_2}; border-color:{BTN_2_BORDER}; color:{TEXT}; }}
.stButton button[kind="secondary"]:hover, .stDownloadButton button[kind="secondary"]:hover {{
  border-color:{ORANGE}; color:{TEXT}; }}

/* Inputs: orange border plus soft glow on focus. */
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within,
[data-baseweb="textarea"]:focus-within {{
  border-color:{ORANGE} !important; box-shadow:0 0 0 3px {ORANGE_GLOW}; }}

a, a:visited {{ color:{LINK}; }}
</style>
"""


# ------------------------------------------------------------------ names

_UPPER_WORDS = {"KL", "JB"}  # abbreviations that stay in capitals: KL Sentral, JB Sentral


def station_name(name: str) -> str:
    """Display form of a GTFS station name: "KL SENTRAL" -> "KL Sentral", "PULAU SEBANG/TAMPIN" ->
    "Pulau Sebang/Tampin". Plain str.title() would give "Kl Sentral"."""
    return " ".join(w if w.upper() in _UPPER_WORDS else w.title() for w in str(name).split())


# ------------------------------------------------------------------ HTML pieces

def top_bar(title: str, subtitle: str, chips: list[tuple[str, str]]) -> str:
    c = "".join(f'<span class="ets-chip">{html.escape(k)} <b>{html.escape(v)}</b></span>' for k, v in chips)
    return (f'<div class="ets-top"><div class="ets-brand"><div class="ets-mark"></div><div>'
            f'<div class="ets-title">{html.escape(title)}</div>'
            f'<div class="ets-sub">{html.escape(subtitle)}</div></div></div>'
            f'<div class="ets-chips">{c}</div></div>')


def section(title: str, note: str = "", guide: str = "") -> str:
    """Section header. guide, if given, adds an (i) "how to read" tooltip on hover or keyboard focus.
    guide is plain text; a blank line starts a new paragraph."""
    n = f"<span>{html.escape(note)}</span>" if note else ""
    g = ""
    if guide:
        paras = "".join(f"<p>{html.escape(p.strip())}</p>" for p in guide.split("\n\n") if p.strip())
        g = (f'<span class="ets-help" tabindex="0" role="button" aria-label="How to read: {html.escape(title)}">'
             f'i<span class="ets-tip" role="tooltip"><b>How to read</b>{paras}</span></span>')
    return f'<div class="ets-sec"><h3>{html.escape(title)}</h3>{g}{n}</div>'


def kpi_board(items: list[tuple[str, str, str, str]]) -> str:
    """items: (label, value, unit, sub-line such as the CI)."""
    cells = "".join(
        f'<div class="ets-kpi"><div class="l">{html.escape(l)}</div>'
        f'<div class="v">{html.escape(v)}<small>{html.escape(u)}</small></div>'
        f'<div class="ci">{html.escape(s)}</div></div>'
        for l, v, u, s in items)
    return f'<div class="ets-board">{cells}</div>'
