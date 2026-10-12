"""Shared styling and HTML building blocks for the AutoDiag-RAG Streamlit app.

Design concept: an engineering blueprint. Drafting-grid paper, white line work, a title block on
every sheet, registration marks on key panels, and inspection stamps for warranty verdicts.
Safety yellow is the single accent (actions and the one thing to look at); status colours are
reserved for verdicts and always ship with an icon and a word.
"""
import base64
import html as _html
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Saira+Condensed:wght@500;600;700;800&family=Saira:wght@400;500;600;700&display=swap');

:root {
  --bp: #0a2342;          /* blueprint paper */
  --bp-deep: #071a33;     /* sidebar, wells */
  --panel: rgba(9, 33, 63, .82);
  --line: #2c5583;        /* drafting line */
  --line-hi: #6f9cc9;     /* emphasised line */
  --grid: rgba(143, 179, 217, .07);
  --grid-major: rgba(143, 179, 217, .12);
  --text: #eaf2fb;        /* drafting white */
  --muted: #a7c0dc;
  --faint: #7896b8;
  --accent: #ffd23f;      /* safety yellow */
  --accent-ink: #0a2342;
  --good: #46d38a;
  --bad: #ff6b6b;
  --warn: #ffb454;
  --dtc: #7cc4ff;
  --nhtsa: #9ee6c8;
  --warranty: #ffcf8a;
  --cond: 'Saira Condensed', 'Arial Narrow', sans-serif;
  --body: 'Saira', 'Segoe UI', system-ui, sans-serif;
}

html, body, [class*="css"], .stApp, .stMarkdown, button, input, textarea, select { font-family: var(--body); }
.stApp {
  background-color: var(--bp);
  background-image:
    linear-gradient(var(--grid-major) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid-major) 1px, transparent 1px),
    linear-gradient(var(--grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid) 1px, transparent 1px);
  background-size: 100px 100px, 100px 100px, 20px 20px, 20px 20px;
}
[data-testid="stHeader"] { background: rgba(7, 26, 51, .97); border-bottom: 1px solid var(--line); }
[data-testid="stSidebar"] { background: var(--bp-deep); border-right: 1px solid var(--line); }
[data-testid="stSidebar"] h3 { font-family: var(--cond); font-size: 1rem; font-weight: 600; color: var(--muted);
  margin-top: .6rem; border-bottom: 1px dashed var(--line); padding-bottom: .25rem; }
.block-container { padding-top: 3.2rem; max-width: 1200px; }
h1, h2, h3, h4, h5, h6 { font-family: var(--cond) !important; letter-spacing: .01em; }
.stMarkdown h4, .stMarkdown h5 { font-weight: 700; }

/* ---------- registration marks: L-shaped corner ticks on key panels ---------- */
.reg {
  --m: var(--line-hi);
  background:
    linear-gradient(var(--m), var(--m)) top left / 12px 2px no-repeat,
    linear-gradient(var(--m), var(--m)) top left / 2px 12px no-repeat,
    linear-gradient(var(--m), var(--m)) top right / 12px 2px no-repeat,
    linear-gradient(var(--m), var(--m)) top right / 2px 12px no-repeat,
    linear-gradient(var(--m), var(--m)) bottom left / 12px 2px no-repeat,
    linear-gradient(var(--m), var(--m)) bottom left / 2px 12px no-repeat,
    linear-gradient(var(--m), var(--m)) bottom right / 12px 2px no-repeat,
    linear-gradient(var(--m), var(--m)) bottom right / 2px 12px no-repeat,
    var(--panel);
}

/* ---------- sheet header: title with a dimension line + title block ---------- */
.ad-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 1.5rem; }
.ad-title { font-family: var(--cond); font-size: 2.9rem; font-weight: 800; color: var(--text); margin: 0;
  line-height: 1.02; letter-spacing: .005em; display: inline-block; }
.ad-dim { position: relative; height: 12px; margin: .35rem 0 .55rem; border-left: 1.5px solid var(--accent);
  border-right: 1.5px solid var(--accent); }
.ad-dim::before { content: ''; position: absolute; left: 0; right: 0; top: 50%; height: 1.5px; background: var(--accent); }
.ad-dim::after { content: ''; position: absolute; left: 50%; top: 50%; width: 7px; height: 7px; transform: translate(-50%, -50%);
  background: var(--bp); border: 1.5px solid var(--accent); border-radius: 50%; }
.ad-titlewrap { display: inline-block; }
.ad-sub { color: var(--muted); font-size: 1rem; max-width: 640px; line-height: 1.55; }
.ad-tb { border: 1px solid var(--line-hi); font-family: var(--cond); font-size: .82rem; min-width: 210px;
  background: rgba(7, 26, 51, .85); }
.ad-tb div { display: grid; grid-template-columns: 70px 1fr; border-bottom: 1px solid var(--line); }
.ad-tb div:last-child { border-bottom: none; }
.ad-tb span { padding: .22rem .5rem; color: var(--text); }
.ad-tb span:first-child { color: var(--faint); border-right: 1px solid var(--line); }
@media (max-width: 900px) { .ad-tb { display: none; } .ad-title { font-size: 2.2rem; } }

/* ---------- brand / title block in the sidebar ---------- */
.ad-brand { display: flex; align-items: center; gap: .7rem; padding: .2rem 0 .8rem; }
.ad-brand img { width: 44px; height: 44px; }
.ad-brand-name { font-family: var(--cond); font-weight: 800; font-size: 1.45rem; color: var(--text); line-height: 1; }
.ad-brand-tag { font-size: .76rem; color: var(--muted); }
.ad-status { display: inline-flex; align-items: center; gap: .45rem; font-family: var(--cond); font-size: .88rem;
  color: var(--text); padding: .2rem .6rem; border: 1px solid var(--line); }
.ad-dot { width: 8px; height: 8px; border-radius: 50%; }

/* ---------- cards ---------- */
.ad-card { border: 1px solid var(--line); padding: 1.1rem 1.2rem; height: 100%; }
.ad-card h4 { margin: .55rem 0 .3rem; font-size: 1.2rem; color: var(--text); font-family: var(--cond); }
.ad-card p { margin: 0; color: var(--muted); font-size: .9rem; line-height: 1.55; }
.ad-icon img { width: 30px; height: 30px; }

/* ---------- badges & chips ---------- */
.ad-meta-line { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; margin-bottom: .7rem; }
.ad-badge { display: inline-flex; align-items: center; gap: .4rem; padding: .12rem .6rem; font-family: var(--cond);
  font-size: .95rem; font-weight: 700; border: 1.5px solid; }
.ad-badge.diagnosis { color: var(--dtc); border-color: var(--dtc); }
.ad-badge.warranty  { color: var(--warranty); border-color: var(--warranty); }
.ad-conf { display: inline-flex; align-items: center; gap: .35rem; padding: .12rem .6rem; font-family: var(--cond);
  font-size: .95rem; font-weight: 600; border: 1px solid; }
.ad-conf.high { color: var(--good); border-color: rgba(70, 211, 138, .6); }
.ad-conf.medium { color: var(--warn); border-color: rgba(255, 180, 84, .6); }
.ad-conf.low { color: var(--bad); border-color: rgba(255, 107, 107, .6); }
.ad-conf.unknown { color: var(--muted); border-color: var(--line); }
.ad-latency { font-family: var(--cond); font-size: .92rem; color: var(--faint); font-variant-numeric: tabular-nums; }
.ad-chip { display: inline-block; font-family: var(--cond); font-size: .84rem; color: var(--muted);
  padding: .02rem .45rem; border: 1px solid var(--line); margin-right: .3rem; font-variant-numeric: tabular-nums; }
.ad-chip.hit { color: var(--text); border-color: var(--line-hi); }
.ad-chip.both { color: var(--accent-ink); background: var(--accent); border-color: var(--accent); font-weight: 700; }
.ad-defer { border: 1.5px dashed var(--warn); padding: .7rem .95rem; margin-bottom: .7rem; font-size: .9rem; color: var(--warn); }
.ad-defer b { color: var(--text); }

/* ---------- pipeline trace: a schematic, boxes joined by lines ---------- */
.ad-trace { display: flex; flex-wrap: wrap; align-items: stretch; gap: 16px; margin: .9rem 0 .3rem; }
.ad-step { position: relative; flex: 1 1 130px; border: 1px solid var(--line-hi); padding: .45rem .7rem; background: var(--bp-deep); }
.ad-step:not(:last-child)::after { content: ''; position: absolute; right: -17px; top: 50%; width: 16px; height: 1.5px; background: var(--line-hi); }
.ad-step.skipped { opacity: .45; border-style: dashed; }
.ad-step .n { font-family: var(--cond); font-size: .8rem; color: var(--accent); }
.ad-step .t { font-family: var(--cond); font-size: 1.02rem; font-weight: 700; color: var(--text); }
.ad-step .d { font-size: .76rem; color: var(--muted); }

/* ---------- source cards: reference tags ---------- */
.ad-src { border: 1px solid var(--line); border-left: 4px solid var(--faint); padding: .7rem .9rem; margin-bottom: .55rem;
  background: rgba(7, 26, 51, .7); }
.ad-src.dtc { border-left-color: var(--dtc); }
.ad-src.nhtsa { border-left-color: var(--nhtsa); }
.ad-src.warranty { border-left-color: var(--warranty); }
.ad-src-head { display: flex; justify-content: space-between; gap: .6rem; flex-wrap: wrap; margin-bottom: .35rem; }
.ad-src-label { font-family: var(--cond); font-size: 1rem; font-weight: 700; color: var(--text); }
.ad-src-label .num { color: var(--accent); margin-right: .4rem; }
.ad-src-meta { font-size: .8rem; color: var(--muted); }
.ad-src-text { font-size: .88rem; color: #cfe0f2; line-height: 1.55; }

/* ---------- verdict: an inspection stamp ---------- */
.ad-verdict { display: grid; grid-template-columns: auto 1fr; gap: 1.1rem; align-items: center; padding: 1rem 1.2rem;
  margin-bottom: .8rem; border: 1px solid var(--line); }
.ad-stamp { font-family: var(--cond); font-weight: 800; font-size: 1.55rem; line-height: 1; padding: .45rem .8rem;
  border: 3px solid currentColor; outline: 1.5px solid currentColor; outline-offset: 3px; transform: rotate(-5deg);
  white-space: nowrap; letter-spacing: .03em; }
.ad-stamp.covered { color: var(--good); }
.ad-stamp.not_covered { color: var(--bad); }
.ad-stamp.needs_review { color: var(--warn); }
.ad-verdict-sub { font-family: var(--cond); font-size: 1.05rem; color: var(--text); font-weight: 600; }
.ad-verdict-reason { font-size: .9rem; color: var(--muted); margin-top: .25rem; line-height: 1.5; }

/* ---------- meters (used inside chat answers) ---------- */
.ad-meter { margin-top: .6rem; }
.ad-meter-head { display: flex; justify-content: space-between; font-size: .84rem; color: var(--muted); margin-bottom: .25rem; }
.ad-meter-head b { color: var(--text); font-weight: 600; font-variant-numeric: tabular-nums; }
.ad-track { height: 8px; background: var(--bp-deep); border: 1px solid var(--line); }
.ad-fill { height: 100%; }

/* ---------- matrix rows ---------- */
.ad-row { display: flex; align-items: center; justify-content: space-between; gap: .8rem; padding: .55rem .2rem;
  border-bottom: 1px dashed var(--line); font-size: .9rem; }
.ad-row:last-child { border-bottom: none; }
.ad-row .name { color: var(--text); font-weight: 600; }
.ad-row .lim { font-family: var(--cond); font-size: .86rem; color: var(--muted); }
.ad-pill { font-family: var(--cond); font-size: .9rem; font-weight: 700; padding: .05rem .5rem; border: 1px solid currentColor; }
.ad-pill.covered { color: var(--good); }
.ad-pill.not_covered { color: var(--bad); }
.ad-pill.needs_review { color: var(--warn); }

/* ---------- stat tiles & bars ---------- */
.ad-tile { border: 1px solid var(--line); padding: .8rem 1rem; background: rgba(7, 26, 51, .7); }
.ad-tile .k { font-family: var(--cond); font-size: .95rem; color: var(--muted); }
.ad-tile .v { font-family: var(--cond); font-size: 2.3rem; font-weight: 800; color: var(--text); line-height: 1.05;
  font-variant-numeric: tabular-nums; }
.ad-tile .s { font-size: .78rem; color: var(--faint); }
.ad-bar-row { display: grid; grid-template-columns: 150px 1fr 70px; align-items: center; gap: .7rem; margin: .45rem 0; font-size: .88rem; }
.ad-bar-row .lbl { color: var(--muted); }
.ad-bar-row .val { font-family: var(--cond); color: var(--text); text-align: right; font-size: .95rem; font-variant-numeric: tabular-nums; }
.ad-bar-track { height: 14px; border: 1px solid var(--line); background: var(--bp-deep); }
.ad-bar-fill { height: 100%; background: repeating-linear-gradient(135deg, #6f9cc9 0 6px, #5a87b5 6px 12px); }

/* ---------- architecture flow ---------- */
.ad-flow { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
.ad-node { border: 1px solid var(--line-hi); padding: .45rem .75rem; font-family: var(--cond); font-size: 1rem; color: var(--text);
  background: var(--bp-deep); }
.ad-node small { display: block; font-family: var(--body); color: var(--muted); font-size: .72rem; }
.ad-arrow { color: var(--accent); font-family: var(--cond); font-size: 1.1rem; }

/* ---------- native widgets ---------- */
.stButton > button, .stDownloadButton > button { border-radius: 2px; border: 1px solid var(--line-hi);
  background: rgba(7, 26, 51, .85); font-family: var(--cond); font-size: 1rem; font-weight: 600; color: var(--text); }
.stButton > button:hover, .stDownloadButton > button:hover { border-color: var(--accent); color: var(--accent); }
.stButton > button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.stButton > button[kind="primary"] { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); font-weight: 700; }
.stButton > button[kind="primary"]:hover { background: #ffdd66; color: var(--accent-ink); }
[data-testid="stChatMessage"] { background: transparent; }
[data-testid="stExpander"] details { border-radius: 2px; border-color: var(--line); background: rgba(7, 26, 51, .7); }
[data-testid="stExpander"] summary { font-family: var(--cond); font-size: 1.02rem; }
[class*="st-key-answer-"] {
  --m: var(--accent);
  background:
    linear-gradient(var(--m), var(--m)) top left / 14px 2px no-repeat,
    linear-gradient(var(--m), var(--m)) top left / 2px 14px no-repeat,
    linear-gradient(var(--m), var(--m)) top right / 14px 2px no-repeat,
    linear-gradient(var(--m), var(--m)) top right / 2px 14px no-repeat,
    linear-gradient(var(--m), var(--m)) bottom left / 14px 2px no-repeat,
    linear-gradient(var(--m), var(--m)) bottom left / 2px 14px no-repeat,
    linear-gradient(var(--m), var(--m)) bottom right / 14px 2px no-repeat,
    linear-gradient(var(--m), var(--m)) bottom right / 2px 14px no-repeat,
    rgba(7, 26, 51, .88);
  border: 1px solid var(--line); padding: 1.1rem 1.25rem; line-height: 1.65;
}
[class*="st-key-example-"] button { text-align: left; justify-content: flex-start; min-height: 3.3rem; font-family: var(--body);
  font-size: .9rem; font-weight: 500; color: #cfe0f2; }
[data-testid="stChatInput"] { border-radius: 2px; }
[data-testid="stChatInput"] textarea { font-family: var(--body); }
[data-testid="stSegmentedControl"] button, [data-baseweb="button-group"] button { border-radius: 2px !important;
  font-family: var(--cond); font-size: .98rem; }
[data-baseweb="select"] > div, [data-baseweb="input"] > div, .stNumberInput input { border-radius: 2px; }
</style>
"""

STATUS = {
    "covered": {"label": "Covered", "stamp": "COVERED", "icon": "✓", "color": "#46d38a"},
    "not_covered": {"label": "Not covered", "stamp": "NOT COVERED", "icon": "✕", "color": "#ff6b6b"},
    "needs_review": {"label": "Needs review", "stamp": "REVIEW", "icon": "!", "color": "#ffb454"},
}

SHEETS = {"What's wrong with the vehicle?": 1, "Is this repair covered?": 2, "System insights": 3}

# 24×24 line icons, drawn in blueprint white (used instead of emoji so the style stays consistent)
_ICON_PATHS = {
    "search": '<circle cx="10" cy="10" r="6"/><path d="M14.5 14.5 20 20"/>',
    "shield": '<path d="M12 3 19 6v5c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6z"/><path d="m9 12 2 2 4-4"/>',
    "doc": '<path d="M6 3h9l3 3v15H6z"/><path d="M9 10h6M9 14h6M9 18h4"/>',
    "chip": '<rect x="7" y="7" width="10" height="10"/><path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4"/>',
    "target": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r=".8"/>',
    "pen": '<path d="M4 20l4-1L19 8l-3-3L5 16z"/><path d="M14 7l3 3"/>',
    "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 11a6 6 0 0 0 12 0M12 17v4"/>',
}
_EMOJI_ICON = {"🔎": "search", "🛡️": "shield", "📚": "doc", "🧠": "chip", "🎯": "target", "✍️": "pen", "🎙️": "mic"}


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def esc(text) -> str:
    return _html.escape(str(text)) if text is not None else ""


def html(markup: str):
    """Render HTML. Lines are stripped so Markdown never treats indentation as a code block."""
    st.markdown("\n".join(line.strip() for line in markup.splitlines()), unsafe_allow_html=True)


def svg_img(svg: str, alt: str = "", cls: str = "") -> str:
    data = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f'<img class="{cls}" alt="{esc(alt)}" src="data:image/svg+xml;base64,{data}"/>'


def icon(name: str, color: str = "#eaf2fb") -> str:
    path = _ICON_PATHS.get(_EMOJI_ICON.get(name, name), _ICON_PATHS["doc"])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{path}</svg>')
    return svg_img(svg, "")


def pretty(component: str) -> str:
    name = component.replace("_", " ").replace("8 80", "8/80").title()
    return name.replace("Ac ", "AC ")


# ---------------------------------------------------------------- headers
def page_header(eyebrow, title, subtitle):
    """Sheet title with a dimension line under it and an engineering title block on the right."""
    sheet = SHEETS.get(title, 1)
    html(f"""
    <div class="ad-head">
      <div>
        <div class="ad-titlewrap"><h1 class="ad-title">{esc(title)}</h1><div class="ad-dim"></div></div>
        <div class="ad-sub">{esc(subtitle)}</div>
      </div>
      <div class="ad-tb">
        <div><span>Sheet</span><span>{sheet} of 3</span></div>
        <div><span>Subject</span><span>{esc(eyebrow)}</span></div>
      </div>
    </div>
    """)


def brand(online: bool):
    dot = "#46d38a" if online else "#ff6b6b"
    state = "API online" if online else "API offline"
    mark = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 44" fill="none">'
            '<rect x="1" y="1" width="42" height="42" stroke="#ffd23f" stroke-width="2"/>'
            '<circle cx="22" cy="22" r="13" stroke="#6f9cc9" stroke-width="1.2"/>'
            '<path d="M22 4v8M22 32v8M4 22h8M32 22h8" stroke="#6f9cc9" stroke-width="1.2"/>'
            '<path d="M14 28 22 14l8 14M17.5 23h9" stroke="#ffd23f" stroke-width="2.4" stroke-linejoin="round"/></svg>')
    html(f"""
    <div class="ad-brand">{svg_img(mark, "AutoDiag")}
      <div><div class="ad-brand-name">AutoDiag</div><div class="ad-brand-tag">Diagnosis &amp; warranty intelligence</div></div>
    </div>
    <span class="ad-status"><span class="ad-dot" style="background:{dot}"></span>{state}</span>
    """)


def feature_card(icon_name, title, body):
    html(f"""<div class="ad-card reg"><div class="ad-icon">{icon(icon_name)}</div><h4>{esc(title)}</h4><p>{esc(body)}</p></div>""")


# ---------------------------------------------------------------- answer parts
CONFIDENCE = {
    "high": ("●", "High confidence"),
    "medium": ("◐", "Medium confidence"),
    "low": ("○", "Low confidence"),
    "unknown": ("–", "Confidence not measured"),
}


def confidence_chip(conf: dict) -> str:
    if not conf:
        return ""
    level = conf.get("level", "unknown")
    glyph, label = CONFIDENCE.get(level, CONFIDENCE["unknown"])
    score = conf.get("top_score")
    score_txt = f" {score:.2f}" if score is not None else ""
    tip = esc(conf.get("reason", ""))
    return f'<span class="ad-conf {esc(level)}" title="{tip}">{glyph} {label}{score_txt}</span>'


def route_badge(route: str, timings: dict = None, confidence: dict = None) -> str:
    label = "Warranty" if route == "warranty" else "Diagnosis"
    total = timings.get("total_ms") if timings else None
    lat = f'<span class="ad-latency">{total / 1000:.1f} s end to end</span>' if total else ""
    return (f'<div class="ad-meta-line"><span class="ad-badge {esc(route)}">{label}</span>'
            f'{confidence_chip(confidence)}{lat}</div>')


def defer_notice(conf: dict):
    """Banner shown when the confidence gate deferred the question."""
    score = conf.get("top_score")
    score_txt = f"{score:.2f}" if score is not None else "n/a"
    html(f'<div class="ad-defer"><b>Sent to human review.</b> The best evidence scored {score_txt}, below the '
         f'{conf.get("threshold", 0):.2f} threshold, so no AI answer was written. The question has been logged '
         f'for an expert.</div>')


def pipeline_trace(route, timings, has_verdict, sources, confidence=None):
    timings = timings or {}
    confidence = confidence or {}
    deferred = confidence.get("deferred", False)
    n = len(sources)
    both = sum(1 for s in sources if s.get("dense_rank") and s.get("bm25_rank"))

    def ms(key):
        v = timings.get(key)
        return f"{v:.0f} ms" if v is not None else "—"

    steps = [
        ("01", "Router", f"{route}, {ms('routing_ms')}", False),
        ("02", "Hybrid retrieval", f"BGE-M3 + BM25, RRF, re-rank, {ms('retrieval_ms')}", False),
        ("03", "Rules check", f"deterministic, {ms('warranty_check_ms')}" if has_verdict else "not needed", not has_verdict),
        ("04", "Confidence gate", f"{confidence.get('level', 'unknown')}, " + ("deferred" if deferred else "passed"), False),
        ("05", "Grounded answer", "skipped for human review" if deferred else f"Gemini, {ms('generation_ms')}", deferred),
    ]
    cells = "".join(
        f'<div class="ad-step{" skipped" if skip else ""}"><div class="n">{num}</div>'
        f'<div class="t">{esc(t)}</div><div class="d">{esc(d)}</div></div>'
        for num, t, d, skip in steps
    )
    html(f'<div class="ad-trace">{cells}</div>'
         f'<div class="ad-latency">{n} sources used, {both} found by both retrievers</div>')


def _source_kind(src):
    source = (src.get("source") or "").lower()
    if src.get("doc_type") == "warranty" or source.endswith(".pdf"):
        return "warranty", f"Warranty booklet, {src.get('manufacturer') or 'unknown maker'}"
    if source == "nhtsa":
        return "nhtsa", "NHTSA owner complaint"
    return "dtc", "DTC code library"


def _source_meta(kind, src):
    if kind == "warranty":
        return f"page {src['page']}" if src.get("page") else ""
    if kind == "nhtsa":
        vehicle = " ".join(str(x) for x in (src.get("year"), src.get("make"), src.get("model")) if x)
        comp = src.get("components") or ""
        return ", ".join(x for x in (vehicle.title(), comp.title()) if x)
    return src.get("dtc_code") or ""


def source_card(i, src):
    kind, label = _source_kind(src)
    meta = _source_meta(kind, src)
    d, b = src.get("dense_rank"), src.get("bm25_rank")
    chips = []
    if d and b:
        chips.append('<span class="ad-chip both">found by both</span>')
    chips.append(f'<span class="ad-chip{" hit" if d else ""}">Dense {"#" + str(d) if d else "—"}</span>')
    chips.append(f'<span class="ad-chip{" hit" if b else ""}">BM25 {"#" + str(b) if b else "—"}</span>')
    if src.get("rerank_score") is not None:
        chips.append(f'<span class="ad-chip hit">Rerank {src["rerank_score"]:.2f}</span>')
    if src.get("fused_score") is not None:
        chips.append(f'<span class="ad-chip">RRF {src["fused_score"]:.4f}</span>')
    html(f"""
    <div class="ad-src {kind}">
      <div class="ad-src-head">
        <div><span class="ad-src-label"><span class="num">Ref {i}</span>{esc(label)}</span>
        <span class="ad-src-meta">{("  " + esc(meta)) if meta else ""}</span></div>
        <div>{"".join(chips)}</div>
      </div>
      <div class="ad-src-text">{esc(src.get("text", ""))}</div>
    </div>
    """)


# ---------------------------------------------------------------- warranty visuals
def _meter(label, used, limit, unit, fmt):
    if limit is None:
        return (f'<div class="ad-meter"><div class="ad-meter-head"><span>{esc(label)}</span>'
                f'<b>{fmt(used)} {unit}, no limit</b></div>'
                f'<div class="ad-track"><div class="ad-fill" style="width:100%;background:#2f7a55"></div></div></div>')
    pct = used / limit * 100 if limit else 0
    colour = "#46d38a" if pct < 80 else ("#ffb454" if pct <= 100 else "#ff6b6b")
    left = limit - used
    tail = f"{fmt(left)} {unit} left" if left >= 0 else f"{fmt(-left)} {unit} over"
    return (f'<div class="ad-meter"><div class="ad-meter-head"><span>{esc(label)}, {tail}</span>'
            f'<b>{fmt(used)} / {fmt(limit)} {unit}</b></div>'
            f'<div class="ad-track"><div class="ad-fill" style="width:{min(pct, 100):.1f}%;background:{colour}"></div></div></div>')


def verdict_block(verdict, age=None, miles=None, title=None):
    """Inspection stamp + reason. Meters are added when age and mileage are given (chat answers)."""
    status = verdict.get("status", "needs_review")
    s = STATUS.get(status, STATUS["needs_review"])
    rule = verdict.get("rule_used") or {}
    meters = ""
    if rule and age is not None and miles is not None:
        meters = (_meter("Time", age, rule.get("years"), "yrs", lambda v: f"{v:g}")
                  + _meter("Mileage", miles, rule.get("miles"), "mi", lambda v: f"{int(v):,}"))
    sub = esc(title) if title else "Rules check, not an LLM guess"
    html(f"""
    <div class="ad-verdict reg">
      <div class="ad-stamp {status}">{s['icon']} {s['stamp']}</div>
      <div><div class="ad-verdict-sub">{sub}</div>
        <div class="ad-verdict-reason">{esc(verdict.get("reason", ""))}</div>{meters}</div>
    </div>
    """)


def coverage_rows(matrix):
    rows = []
    for item in matrix:
        s = STATUS.get(item["status"], STATUS["needs_review"])
        rule = item.get("rule") or {}
        miles = f"{rule['miles']:,} mi" if rule.get("miles") else "unlimited mi"
        rows.append(
            f'<div class="ad-row"><div><div class="name">{esc(pretty(item["component"]))}</div>'
            f'<div class="lim">{rule.get("years", "?"):g} yrs, {miles}</div></div>'
            f'<span class="ad-pill {item["status"]}">{s["icon"]} {s["label"]}</span></div>'
        )
    html(f'<div class="ad-card">{"".join(rows)}</div>')


# ---------------------------------------------------------------- dashboard
def stat_tile(label, value, sub=""):
    html(f'<div class="ad-tile"><div class="k">{esc(label)}</div><div class="v">{esc(value)}</div><div class="s">{esc(sub)}</div></div>')


def bar_list(rows):
    """Single-series horizontal bars with direct value labels. rows: [(label, value)]."""
    if not rows:
        return
    top = max(v for _, v in rows) or 1
    body = "".join(
        f'<div class="ad-bar-row" title="{esc(lbl)}: {v:,}"><div class="lbl">{esc(lbl)}</div>'
        f'<div class="ad-bar-track"><div class="ad-bar-fill" style="width:{max(v / top * 100, 1.5):.1f}%"></div></div>'
        f'<div class="val">{v:,}</div></div>'
        for lbl, v in rows
    )
    html(f'<div class="ad-card">{body}</div>')