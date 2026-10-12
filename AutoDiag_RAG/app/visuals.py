"""Blueprint-styled visuals for the AutoDiag UI: car drawing with a parts list, warranty gauges,
DTC decoder, coverage timeline and evaluation bars. Pure HTML/SVG — no external images or packages."""
import json
import math
import re
from pathlib import Path

import streamlit as st
from ui import esc, html, pretty, svg_img, STATUS

EVAL_DIR = Path(__file__).resolve().parents[1] / "data" / "eval"
DTC_PATTERN = re.compile(r"\b([PBCU])([0-3])([0-9A-F])([0-9A-F]{2})\b", re.IGNORECASE)

GOOD, WARN, BAD = "#46d38a", "#ffb454", "#ff6b6b"
YELLOW, WHITE, LINE, LINE_HI, MUTED = "#ffd23f", "#eaf2fb", "#2c5583", "#6f9cc9", "#a7c0dc"
COND = "'Saira Condensed', 'Arial Narrow', 'Roboto Condensed', sans-serif"

CSS = """
<style>
/* ---------- car drawing ---------- */
.vx-hero { border: 1px solid var(--line); padding: .6rem .8rem .3rem; }
.vx-hero img { width: 100%; display: block; }

/* ---------- gauges ---------- */
.vx-gauges { display: grid; grid-template-columns: 1fr 1fr; gap: .8rem; margin: .2rem 0 .9rem; }
.vx-gauge { border: 1px solid var(--line); padding: .55rem .5rem .25rem; text-align: center; }
.vx-gauge img { width: 100%; max-width: 270px; }
.vx-gauge-t { font-family: var(--cond); font-size: 1.05rem; font-weight: 700; color: var(--text); }

/* ---------- DTC decoder ---------- */
.vx-dtc { border: 1.5px solid var(--accent); padding: .7rem .9rem .75rem; margin-bottom: .8rem; background: rgba(7, 26, 51, .9); }
.vx-dtc-head { display: flex; justify-content: space-between; font-family: var(--cond); font-size: .95rem;
  color: var(--muted); margin-bottom: .5rem; }
.vx-dtc-head b { color: var(--accent); }
.vx-dtc-cells { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0; border: 1px solid var(--line); }
.vx-dtc-cell { padding: .45rem .65rem; border-right: 1px dashed var(--line); }
.vx-dtc-cell:last-child { border-right: none; }
.vx-dtc-cell .ch { font-family: var(--cond); font-size: 2.1rem; font-weight: 800; color: var(--accent); line-height: 1; }
.vx-dtc-cell .lb { font-size: .8rem; color: var(--text); margin-top: .25rem; line-height: 1.3; }
.vx-dtc-cell .pos { font-family: var(--cond); font-size: .76rem; color: var(--faint); }

/* ---------- coverage timeline ---------- */
.vx-tl { border: 1px solid var(--line); padding: .9rem 1rem .6rem; }
.vx-tl-row { display: grid; grid-template-columns: 160px 1fr 140px; align-items: center; gap: .8rem; height: 38px;
  border-bottom: 1px dashed rgba(44, 85, 131, .6); }
.vx-tl-name { font-family: var(--cond); font-size: 1.02rem; font-weight: 600; color: var(--text); }
.vx-tl-term { font-family: var(--cond); font-size: .9rem; color: var(--muted); text-align: right; font-variant-numeric: tabular-nums; }
.vx-tl-track { position: relative; height: 37px; }
.vx-tl-bar { position: absolute; top: 11px; height: 15px; left: 0; }
.vx-tl-mark { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--accent); }
.vx-tl-axis { display: grid; grid-template-columns: 160px 1fr 140px; gap: .8rem; margin-top: .25rem; }
.vx-tl-ticks { position: relative; height: 18px; font-family: var(--cond); font-size: .82rem; color: var(--faint); }
.vx-tl-ticks span { position: absolute; transform: translateX(-50%); }
.vx-tl-you { position: relative; height: 24px; }
.vx-tl-you span { position: absolute; transform: translateX(-50%); font-family: var(--cond); font-size: .95rem; font-weight: 700;
  color: var(--accent); white-space: nowrap; }
.vx-legend { display: flex; gap: 1.2rem; font-size: .8rem; color: var(--muted); margin-top: .4rem; }
.vx-legend i { display: inline-block; width: 12px; height: 10px; margin-right: .35rem; vertical-align: -1px; }

/* ---------- evaluation bars ---------- */
.vx-bars { border: 1px solid var(--line); padding: .8rem 1rem; }
.vx-bar-row { display: grid; grid-template-columns: 150px 1fr 54px; align-items: center; gap: .7rem; margin: .55rem 0; }
.vx-bar-row .lbl { font-family: var(--cond); font-size: 1rem; color: var(--muted); }
.vx-bar-row.best .lbl { color: var(--accent); font-weight: 700; }
.vx-bar-track { height: 16px; border: 1px solid var(--line); background: var(--bp-deep); }
.vx-bar-fill { height: 100%; background: repeating-linear-gradient(135deg, #6f9cc9 0 6px, #5a87b5 6px 12px); }
.vx-bar-row.best .vx-bar-fill { background: var(--accent); }
.vx-bar-row .val { font-family: var(--cond); font-size: 1.05rem; color: var(--text); text-align: right; font-variant-numeric: tabular-nums; }
.vx-bar-row.best .val { color: var(--accent); font-weight: 700; }

@media (max-width: 760px) {
  .vx-tl-row, .vx-tl-axis { grid-template-columns: 90px 1fr 80px; }
  .vx-dtc-cells { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


# ================================================================ car drawing + parts list
PARTS = [
    (1, "Engine", "misfires, P0301"),
    (2, "Exhaust", "catalyst, P0420"),
    (3, "Brakes", "pedal, ABS"),
    (4, "Steering", "stiff, vibration"),
    (5, "Airbags", "warning light"),
]


def car_hero():
    """Side elevation of a car drawn like an engineering sheet: numbered balloons, a dimension line
    and a parts list naming the systems the assistant can diagnose. One scan sweep on load."""
    balloons = [  # (number, point on car, balloon centre)
        (1, (586, 128), (612, 52)),
        (2, (318, 184), (330, 236)),
        (3, (244, 178), (176, 236)),
        (4, (546, 178), (600, 236)),
        (5, (470, 98), (452, 34)),
    ]
    marks = []
    for n, (px, py), (bx, by) in balloons:
        marks.append(f'<line x1="{px}" y1="{py}" x2="{bx}" y2="{by}" stroke="{LINE_HI}" stroke-width="1"/>'
                     f'<circle cx="{px}" cy="{py}" r="3.5" fill="{YELLOW}"/>'
                     f'<circle cx="{bx}" cy="{by}" r="13" fill="#0a2342" stroke="{YELLOW}" stroke-width="1.6"/>'
                     f'<text x="{bx}" y="{by + 5.5}" text-anchor="middle" class="b">{n}</text>')
    rows = []
    for i, (n, part, what) in enumerate(PARTS):
        y = 74 + i * 34
        rows.append(f'<line x1="700" y1="{y + 12}" x2="950" y2="{y + 12}" stroke="{LINE}" stroke-width="1"/>'
                    f'<text x="712" y="{y + 4}" class="pn">{n}</text>'
                    f'<text x="736" y="{y + 4}" class="pt">{part}</text>'
                    f'<text x="830" y="{y + 4}" class="pd">{what}</text>')
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 262">
<style>
  .b {{ font-family: {COND}; font-weight: 700; font-size: 15px; fill: {YELLOW}; }}
  .pn {{ font-family: {COND}; font-weight: 700; font-size: 16px; fill: {YELLOW}; }}
  .pt {{ font-family: {COND}; font-weight: 700; font-size: 16px; fill: {WHITE}; }}
  .pd {{ font-family: {COND}; font-size: 13.5px; fill: {MUTED}; }}
  .h {{ font-family: {COND}; font-weight: 700; font-size: 15px; fill: {MUTED}; }}
  .dim {{ font-family: {COND}; font-size: 13px; fill: {MUTED}; }}
  .scan {{ animation: sweep 2.8s ease-in-out .4s 1 both; }}
  @keyframes sweep {{ 0% {{ transform: translateX(90px); opacity: 0; }} 12% {{ opacity: 1; }}
                      88% {{ opacity: 1; }} 100% {{ transform: translateX(600px); opacity: 0; }} }}
  @media (prefers-reduced-motion: reduce) {{ .scan {{ animation: none; opacity: 0; }} }}
</style>
<defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="{YELLOW}" stop-opacity="0"/>
  <stop offset=".5" stop-color="{YELLOW}" stop-opacity=".45"/><stop offset="1" stop-color="{YELLOW}" stop-opacity="0"/></linearGradient></defs>
<line x1="70" y1="208" x2="680" y2="208" stroke="{LINE_HI}" stroke-width="1" stroke-dasharray="10 4 2 4"/>
<g fill="none" stroke="{WHITE}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round">
  <path d="M118 176 L114 148 Q116 132 140 126 L222 116 Q262 78 300 66 Q330 58 392 58 L452 60 Q486 64 524 100
           L552 114 Q612 120 636 134 Q648 142 648 158 L646 176 L586 176 A40 40 0 0 0 506 176 L284 176
           A40 40 0 0 0 204 176 Z"/>
  <path d="M248 116 Q280 84 318 74 Q340 70 382 70 L384 116 Z"/>
  <path d="M398 70 L448 71 Q478 76 508 112 L398 116 Z"/>
  <line x1="390" y1="118" x2="388" y2="172"/>
  <circle cx="244" cy="178" r="30"/><circle cx="546" cy="178" r="30"/>
</g>
<g fill="none" stroke="{LINE_HI}" stroke-width="1">
  <circle cx="244" cy="178" r="13"/><circle cx="546" cy="178" r="13"/>
  <path d="M244 160v36M226 178h36M546 160v36M528 178h36" stroke-dasharray="3 3"/>
</g>
<g stroke="{MUTED}" stroke-width="1">
  <line x1="244" y1="214" x2="244" y2="252"/><line x1="546" y1="214" x2="546" y2="252"/>
  <line x1="250" y1="246" x2="540" y2="246"/>
  <path d="M250 246l8-4v8zM540 246l-8-4v8z" fill="{MUTED}"/>
</g>
<rect x="356" y="238" width="78" height="16" fill="#0a2342"/>
<text x="395" y="250" text-anchor="middle" class="dim">wheelbase</text>
<rect class="scan" x="0" y="44" width="70" height="160" fill="url(#g)"/>
{''.join(marks)}
<text x="700" y="46" class="h">Systems the assistant covers</text>
<line x1="700" y1="54" x2="950" y2="54" stroke="{LINE_HI}" stroke-width="1.2"/>
{''.join(rows)}
</svg>"""
    html(f'<div class="vx-hero reg">{svg_img(svg, "Car drawing showing the systems AutoDiag can diagnose")}</div>')


# ================================================================ warranty gauges
def _pt(cx, cy, r, f):
    a = math.radians(-120 + 240 * f)
    return cx + r * math.sin(a), cy - r * math.cos(a)


def _arc(cx, cy, r, f0, f1):
    x0, y0 = _pt(cx, cy, r, f0)
    x1, y1 = _pt(cx, cy, r, f1)
    large = 1 if (f1 - f0) * 240 > 180 else 0
    return f"M{x0:.1f},{y0:.1f} A{r},{r} 0 {large} 1 {x1:.1f},{y1:.1f}"


def _gauge_svg(used, limit, unit, fmt):
    cx, cy, r = 120, 108, 88
    if limit:
        scale = limit * 1.25          # dial runs to 125 % of the limit; the last fifth is the red zone
        f = max(0.0, min(used / scale, 1.0))
        pct = used / limit
        colour = GOOD if pct < 0.8 else (WARN if pct <= 1.0 else BAD)
        sub = f"of {fmt(limit)} {unit}"
    else:
        f, colour, sub = 0.12, GOOD, f"{unit}, no limit"
    parts = [f'<path d="{_arc(cx, cy, r, 0, 1)}" stroke="#12325a" stroke-width="12" fill="none"/>']
    if limit:
        parts.append(f'<path d="{_arc(cx, cy, r, 0.8, 1)}" stroke="{BAD}" stroke-opacity=".5" stroke-width="12" fill="none"/>')
    if f > 0.005:
        parts.append(f'<path d="{_arc(cx, cy, r, 0, f)}" stroke="{colour}" stroke-width="12" fill="none"/>')
    parts.append(f'<path d="{_arc(cx, cy, r + 9, 0, 1)}" stroke="{LINE_HI}" stroke-width="1" fill="none"/>')
    for k in range(26):                            # minor + major ticks, like a drafted instrument scale
        t = k / 25
        major = k % 5 == 0
        x0, y0 = _pt(cx, cy, r + 9, t)
        x1, y1 = _pt(cx, cy, r + (17 if major else 13), t)
        parts.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{LINE_HI}" '
                     f'stroke-width="{1.6 if major else 1}"/>')
    if limit:
        lx, ly = _pt(cx, cy, r - 24, 0.8)
        parts.append(f'<text x="{lx:.1f}" y="{ly + 4:.1f}" text-anchor="middle" class="s">limit</text>')
    nx, ny = _pt(cx, cy, r - 6, f)
    parts.append(f'<line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{YELLOW}" stroke-width="3" stroke-linecap="round"/>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="8" fill="#0a2342" stroke="{YELLOW}" stroke-width="2.5"/>')
    parts.append(f'<text x="{cx}" y="{cy + 36}" text-anchor="middle" class="v">{esc(fmt(used))}</text>')
    parts.append(f'<text x="{cx}" y="{cy + 54}" text-anchor="middle" class="s">{esc(sub)}</text>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 178">
<style>.v {{ font-family: {COND}; font-size: 30px; font-weight: 800; fill: {WHITE}; }}
.s {{ font-family: {COND}; font-size: 13px; fill: {MUTED}; }}</style>
{''.join(parts)}</svg>"""


def warranty_gauges(verdict, age, miles):
    """Two instrument dials: how much of the time and mileage limit has been used. Red zone = past the limit."""
    rule = (verdict or {}).get("rule_used") or {}
    if not rule:
        return
    time_svg = _gauge_svg(age, rule.get("years"), "years", lambda v: f"{v:g}")
    miles_svg = _gauge_svg(miles, rule.get("miles"), "miles", lambda v: f"{int(v):,}")
    html(f'<div class="vx-gauges"><div class="vx-gauge reg"><div class="vx-gauge-t">Time used</div>'
         f'{svg_img(time_svg, f"Time used: {age:g} years")}</div>'
         f'<div class="vx-gauge reg"><div class="vx-gauge-t">Mileage used</div>'
         f'{svg_img(miles_svg, f"Mileage used: {int(miles):,} miles")}</div></div>')


# ================================================================ DTC decoder
SYSTEMS = {"P": "Powertrain", "B": "Body", "C": "Chassis", "U": "Network"}
P_SUBSYSTEMS = {
    "0": "Fuel, air & emissions", "1": "Fuel & air metering", "2": "Fuel & air metering (injectors)",
    "3": "Ignition system / misfire", "4": "Auxiliary emission controls", "5": "Speed, idle & aux inputs",
    "6": "Computer & output circuits", "7": "Transmission", "8": "Transmission", "9": "Transmission",
    "A": "Hybrid propulsion", "B": "Hybrid propulsion", "C": "Hybrid propulsion",
}


def find_dtc(text: str):
    m = DTC_PATTERN.search(text or "")
    return m.group(0).upper() if m else None


def dtc_decoder(code: str):
    """Breakdown of an OBD-II code using the SAE J2012 structure."""
    code = code.upper()
    system, kind, sub, fault = code[0], code[1], code[2], code[3:]
    kind_label = {"0": "Generic (SAE)", "1": "Manufacturer-specific",
                  "2": "Generic (SAE)" if system == "P" else "Manufacturer-specific",
                  "3": "Generic / manufacturer"}.get(kind, "—")
    sub_label = P_SUBSYSTEMS.get(sub, "Subsystem") if system == "P" else "Subsystem group"
    if system == "P" and kind == "0" and sub == "3" and fault[0] == "0":
        fault_label = "Random / multiple cylinders" if fault[1] == "0" else f"Cylinder {fault[1]}"
    else:
        fault_label = "Specific fault"
    cells = [("System", system, SYSTEMS.get(system, "—")), ("Type", kind, kind_label),
             ("Subsystem", sub, sub_label), ("Fault", fault, fault_label)]
    body = "".join(f'<div class="vx-dtc-cell"><div class="pos">{pos}</div><div class="ch">{esc(c)}</div>'
                   f'<div class="lb">{esc(lbl)}</div></div>' for pos, c, lbl in cells)
    html(f'<div class="vx-dtc"><div class="vx-dtc-head"><span>Fault code decoded from your question</span>'
         f'<b>{esc(code)}</b></div><div class="vx-dtc-cells">{body}</div></div>')


# ================================================================ coverage timeline
def coverage_timeline(matrix, age, miles):
    """Each covered component as a bar from purchase to its time limit, with the car's age marked."""
    if not matrix:
        return
    span = max([((m.get("rule") or {}).get("years") or 0) for m in matrix] + [age + 1])
    span = min(max(span, 4), 16)
    pos = lambda v: f"{min(v, span) / span * 100:.2f}%"
    fills = {"covered": "rgba(70,211,138,.6)", "not_covered": "rgba(255,107,107,.55)", "needs_review": "rgba(255,180,84,.6)"}
    rows = []
    for m in sorted(matrix, key=lambda m: -((m.get("rule") or {}).get("years") or 0)):
        rule = m.get("rule") or {}
        years = rule.get("years") or 0
        s = STATUS.get(m["status"], STATUS["needs_review"])
        term = f"{years:g} yrs, " + (f"{rule['miles']:,} mi" if rule.get("miles") else "no mile limit")
        rows.append(
            f'<div class="vx-tl-row" title="{esc(pretty(m["component"]))}: {esc(term)}, {s["label"]}">'
            f'<div class="vx-tl-name">{s["icon"]} {esc(pretty(m["component"]))}</div>'
            f'<div class="vx-tl-track"><div class="vx-tl-bar" style="width:{pos(years)};background:{fills.get(m["status"])}"></div>'
            f'<div class="vx-tl-mark" style="left:{pos(age)}"></div></div>'
            f'<div class="vx-tl-term">{esc(term)}</div></div>')
    step = 2 if span <= 10 else 4
    ticks = "".join(f'<span style="left:{pos(t)}">{t}</span>' for t in range(0, int(span) + 1, step))
    html(f"""<div class="vx-tl reg">
    <div class="vx-tl-axis"><div></div><div class="vx-tl-you"><span style="left:{pos(age)}">Your car: {age:g} yrs, {int(miles):,} mi</span></div><div></div></div>
    {''.join(rows)}
    <div class="vx-tl-axis"><div></div><div class="vx-tl-ticks">{ticks}</div><div class="vx-tl-term">years from purchase</div></div>
    <div class="vx-legend"><span><i style="background:{fills['covered']}"></i>Covered now</span>
    <span><i style="background:{fills['not_covered']}"></i>Expired on time or mileage</span></div>
    </div>""")


# ================================================================ evaluation results
def load_eval():
    """Reads the saved evaluation outputs from data/eval (empty dict for any file that is missing)."""
    out = {}
    for key, name in (("retrieval", "retrieval_summary.json"), ("pipeline", "pipeline_summary.json"),
                      ("ragas", "ragas_summary.json")):
        path = EVAL_DIR / name
        try:
            out[key] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError):
            out[key] = {}
    return out


def metric_bars(rows, best_label=None):
    """rows: [(label, value 0-1)]. Single series; the configuration the assistant uses is highlighted."""
    top = max((v for _, v in rows), default=1) or 1
    body = "".join(
        f'<div class="vx-bar-row{" best" if lbl == best_label else ""}" title="{esc(lbl)}: {v:.3f}">'
        f'<div class="lbl">{esc(lbl)}</div><div class="vx-bar-track">'
        f'<div class="vx-bar-fill" style="width:{max(v / top * 100, 2):.1f}%"></div></div>'
        f'<div class="val">{v:.2f}</div></div>' for lbl, v in rows)
    html(f'<div class="vx-bars reg">{body}</div>')