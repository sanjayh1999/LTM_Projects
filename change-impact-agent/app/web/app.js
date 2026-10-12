"use strict";

/* ================= Helpers ================= */
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");

const ICONS = {
  logo: '<path d="M12 2 3 7v10l9 5 9-5V7l-9-5z"/><path d="M12 22V12M21 7l-9 5-9-5"/>',
  bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  graph: '<circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8.3 10.9 15.7 7.1M8.3 13.1l7.4 3.8"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  check: '<path d="m5 12 5 5L20 7"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  octagon: '<path d="M7.9 2h8.2L22 7.9v8.2L16.1 22H7.9L2 16.1V7.9z"/><path d="M12 8v4M12 16h.01"/>',
  shield: '<path d="M12 3 4 6v6c0 5 3.4 8.4 8 9 4.6-.6 8-4 8-9V6l-8-3z"/>',
  shieldCheck: '<path d="M12 3 4 6v6c0 5 3.4 8.4 8 9 4.6-.6 8-4 8-9V6l-8-3z"/><path d="m9 12 2 2 4-4"/>',
  contrast: '<circle cx="12" cy="12" r="9"/><path d="M12 3v18a9 9 0 0 0 0-18z" fill="currentColor"/>',
  brain: '<path d="M9 4a3 3 0 0 0-3 3v.5A3 3 0 0 0 4 13a3 3 0 0 0 2 5 3 3 0 0 0 6 0V4.5A2.5 2.5 0 0 0 9 4zM15 4a3 3 0 0 1 3 3v.5a3 3 0 0 1 2 5.5 3 3 0 0 1-2 5 3 3 0 0 1-6 0"/>',
  memory: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
  tools: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.2L3 17.8V21h3.2l6.3-6.3a4 4 0 0 0 5.2-5.4l-2.6 2.6-2.4-.6-.6-2.4 2.6-2.6z"/>',
  scale: '<path d="M12 3v18M5 21h14M7 7h10M7 7l-3 7a3 3 0 0 0 6 0L7 7zm10 0-3 7a3 3 0 0 0 6 0l-3-7z"/>',
  doc: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
  save: '<path d="M5 3h11l5 5v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M7 3v5h8M7 21v-7h10v7"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  chev: '<path d="m9 6 6 6-6 6"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  play: '<path d="M7 4v16l13-8L7 4z"/>',
  dot: '<circle cx="12" cy="12" r="3"/>',
};
const icon = (name, cls = "") =>
  `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;

const RISK = {
  high: { label: "High risk", cls: "critical", icon: "octagon", level: 3, color: "var(--critical)" },
  medium: { label: "Medium risk", cls: "warning", icon: "alert", level: 2, color: "var(--warning)" },
  low: { label: "Low risk", cls: "good", icon: "shieldCheck", level: 1, color: "var(--good)" },
};

const SIGNAL_LABELS = {
  multiple_projects: "Shared by several projects",
  remove: "Destructive change",
  major_version_jump: "Major version jump",
  version_conflict: "Version conflict",
  python_incompatible: "Python incompatible",
  no_wheel: "No ready-made wheel",
  version_not_found: "Version not on PyPI",
};

const DRY = {
  ok: ["good", "check", "OK"],
  conflict: ["crit", "octagon", "Conflict"],
  would_break: ["crit", "octagon", "Would break"],
  not_found: ["warn", "alert", "Not found"],
  unsupported: ["warn", "alert", "Unsupported"],
  error: ["warn", "alert", "Error"],
  skipped: ["", "info", "Skipped"],
};

const EXAMPLES = [
  "Can I downgrade numpy to 1.24.3?",
  "Can I remove numpy from change-impact-agent?",
  "What if I upgrade numpy to 2.3.5?",
  "Is it safe to upgrade pandas to 3.0.0 in AutoDiag_RAG?",
];

const PIPELINE = [
  { id: "parse_change", title: "Understand", sub: "LLM parses the question", tag: "LLM", icon: "brain" },
  { id: "recall_memory", title: "Recall", sub: "Similar past changes", tag: "Memory", icon: "memory" },
  { id: "investigate", title: "Investigate", sub: "Venvs, deps, PyPI", tag: "Tools", icon: "tools" },
  { id: "assess_risk", title: "Assess", sub: "Rule-based scoring", tag: "Rules", icon: "scale" },
  { id: "report", title: "Report", sub: "Facts + explanation", tag: "Code + LLM", icon: "doc" },
  { id: "save_memory", title: "Remember", sub: "Stored for recall", tag: "Memory", icon: "save" },
];

const pill = (text, kind = "", ic = null) => `<span class="pill ${kind}">${ic ? icon(ic) : ""}${esc(text)}</span>`;

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} returned ${res.status}`);
  return res.json();
}

async function streamNDJSON(url, body, onEvent) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok || !res.body) {
    let detail = `Server returned ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch (_) { /* keep default */ }
    throw new Error(detail);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let i;
    while ((i = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, i).trim();
      buffer = buffer.slice(i + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer));
}

/* ================= Tooltip ================= */
const tooltip = $("#tooltip");
document.addEventListener("mousemove", (e) => {
  const target = e.target.closest ? e.target.closest("[data-tip]") : null;
  if (!target) { tooltip.classList.add("hidden"); return; }
  tooltip.innerHTML = target.getAttribute("data-tip");
  tooltip.classList.remove("hidden");
  const pad = 14;
  let x = e.clientX + pad, y = e.clientY + pad;
  const r = tooltip.getBoundingClientRect();
  if (x + r.width > window.innerWidth - 8) x = e.clientX - r.width - pad;
  if (y + r.height > window.innerHeight - 8) y = e.clientY - r.height - pad;
  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${y}px`;
});

/* ================= Theme, icons, routing, health ================= */
function hydrateIcons(root = document) {
  $$("[data-icon]", root).forEach((el) => { el.innerHTML = icon(el.dataset.icon); el.removeAttribute("data-icon"); });
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  try { localStorage.setItem("impact-theme", theme); } catch (_) { /* storage unavailable */ }
}
let savedTheme = "dark";
try { savedTheme = localStorage.getItem("impact-theme") || "dark"; } catch (_) { /* storage unavailable */ }
applyTheme(savedTheme);
$("#theme-toggle").addEventListener("click", () => {
  applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
});

const loaded = {};
function route() {
  const view = (location.hash || "#analyze").slice(1);
  const valid = ["analyze", "inventory", "explorer", "history"].includes(view) ? view : "analyze";
  $$(".view").forEach((v) => v.classList.toggle("hidden", v.id !== `view-${valid}`));
  $$(".nav-item").forEach((a) => a.classList.toggle("active", a.dataset.view === valid));
  if (valid === "inventory" && !loaded.inventory) loadInventory();
  if (valid === "history") loadHistory();
}
window.addEventListener("hashchange", route);

async function loadHealth() {
  try {
    const h = await getJSON("/api/health");
    for (const [key, id] of [["database", "#status-db"], ["llm", "#status-llm"]]) {
      const row = $(id);
      $(".dot", row).className = `dot ${h[key].ok ? "ok" : "bad"}`;
      row.setAttribute("data-tip", esc(h[key].message));
    }
  } catch (_) {
    $$(".status-row .dot").forEach((d) => (d.className = "dot bad"));
  }
}

/* ================= Analyze ================= */
let current = null;
let busy = false;

function renderExamples() {
  $("#examples").innerHTML = EXAMPLES.map((q) => `<button type="button" class="chip" data-q="${esc(q)}">${icon("arrow")}${esc(q)}</button>`).join("");
  $$("#examples .chip").forEach((b) => b.addEventListener("click", () => { $("#ask-input").value = b.dataset.q; runAnalysis(b.dataset.q); }));
}

function renderPipeline() {
  const el = $("#pipeline");
  el.classList.remove("hidden");
  el.innerHTML = PIPELINE.map((n) => `
    <div class="pnode" id="p-${n.id}">
      <div class="pcircle">${icon(n.icon)}</div>
      <div class="ptitle">${n.title}</div>
      <div class="psub">${n.sub}</div>
      <div class="ptag">${n.tag}</div>
      <div class="ptime"></div>
    </div>`).join("");
}

function setNode(id, stateName, seconds) {
  const node = $(`#p-${id}`);
  if (!node) return;
  node.classList.remove("running", "done", "failed");
  node.classList.add(stateName);
  if (stateName === "done") {
    $(".pcircle", node).innerHTML = icon("check");
    if (seconds !== undefined) $(".ptime", node).textContent = `${seconds.toFixed(1)}s`;
  }
}

async function runAnalysis(query) {
  query = (query || "").trim();
  if (!query || busy) return;
  busy = true;
  $("#ask-btn").disabled = true;
  $("#ask-btn").textContent = "Analyzing...";
  $("#result").innerHTML = '<div class="skeleton tall"></div>';
  renderPipeline();
  const order = PIPELINE.map((n) => n.id);
  setNode(order[0], "running");
  let gotResult = false;
  try {
    await streamNDJSON("/api/analyze", { query }, (ev) => {
      if (ev.type === "step") {
        const id = ev.node === "write_report" || ev.node === "noop_report" ? "report" : ev.node;
        if (ev.node === "noop_report") {
          const n = $("#p-report");
          $(".ptitle", n).textContent = "No-op";
          $(".psub", n).textContent = "Nothing changes, LLM skipped";
          $(".ptag", n).textContent = "Code";
        }
        setNode(id, "done", ev.seconds);
        const next = order[order.indexOf(id) + 1];
        if (next) setNode(next, "running");
      } else if (ev.type === "result") {
        gotResult = true;
        current = ev.data;
        renderResult(ev.data);
      } else if (ev.type === "error") {
        throw new Error(ev.message);
      }
    });
    if (!gotResult) throw new Error("The agent stopped before producing a result.");
  } catch (err) {
    $$(".pnode.running").forEach((n) => { n.classList.remove("running"); n.classList.add("failed"); });
    $("#result").innerHTML = `<div class="error-box">${icon("alert")}<div><b>The agent failed.</b> ${esc(err.message)}<br>
      <span class="card-sub">Check that Docker Desktop (PostgreSQL) and Ollama are running. The status dots in the sidebar show which one is down.</span></div></div>`;
  } finally {
    busy = false;
    $("#ask-btn").disabled = false;
    $("#ask-btn").textContent = "Analyze impact";
  }
}

function renderNarrative(text) {
  return (text || "").split(/\n\s*\n/).map((raw) => {
    let p = esc(raw.trim()).replace(/`([^`]+)`/g, "<code>$1</code>");
    if (!p) return "";
    if (p.startsWith("Recommended next step:")) {
      return `<div class="callout next">${icon("arrow")}<div><b>Recommended next step</b><br>${p.replace("Recommended next step:", "").trim()}</div></div>`;
    }
    if (p.startsWith("Memory:")) return `<div class="callout memory">${icon("memory")}<div>${p.replace("Memory:", "<b>From memory:</b>")}</div></div>`;
    if (p.startsWith("Analysis scoped") || p.startsWith("Project &#39;")) return `<div class="callout scope">${icon("info")}<div>${p}</div></div>`;
    if (p.startsWith("Risk:")) return `<p class="summary">${p.replace(/^Risk: \w+\.\s*/, "")}</p>`;
    return `<p>${p}</p>`;
  }).join("");
}

function changeTitle(cr) {
  const verb = cap(cr.action);
  return cr.target_version ? `${verb} ${cr.package_name} to ${cr.target_version}` : `${verb} ${cr.package_name}`;
}

function renderResult(d) {
  const r = RISK[d.risk_level] || RISK.low;
  const cr = d.change_request;
  const checks = d.project_checks || [];
  const directDependents = checks.reduce((n, c) => n + (c.required_by || []).length, 0);
  const conflicts = checks.reduce((n, c) => n + (c.conflicts || []).length, 0);
  const chips = (d.signals || []).map((s) => pill(SIGNAL_LABELS[s] || s, "", "dot")).join("")
    + (d.is_noop ? pill("No change needed", "good", "check") : "")
    + ((d.memories || []).length ? pill("Recalled from memory", "accent", "memory") : "");

  $("#result").innerHTML = `
  <div class="bento">
    <div class="card risk-card ${r.cls} span-1">
      <div class="risk-kicker">Verdict</div>
      <div class="risk-top"><div class="risk-icon">${icon(r.icon)}</div><div class="risk-label">${r.label}</div></div>
      <div class="risk-meter">${[1, 2, 3].map((i) => `<span class="${i <= r.level ? "on" : ""}"></span>`).join("")}</div>
      <div class="risk-scale"><span>Low</span><span>Medium</span><span>High</span></div>
      <div class="risk-change">${esc(changeTitle(cr))}</div>
      <div class="risk-q">&ldquo;${esc(d.query)}&rdquo;</div>
      <div class="chips" style="margin-top:2px">${chips}</div>
    </div>

    <div class="card span-2">
      <div class="card-head"><h3>Agent report</h3><button class="small-btn" id="dl-report" type="button">${icon("download")}Download</button></div>
      <div class="narrative">${renderNarrative(d.narrative)}</div>
    </div>

    <div class="stats span-3">
      <div class="stat"><div class="stat-value">${d.affected_projects.length}</div><div class="stat-label">Projects affected</div></div>
      <div class="stat"><div class="stat-value">${directDependents}</div><div class="stat-label">Installed packages that depend on it</div></div>
      <div class="stat"><div class="stat-value">${conflicts}</div><div class="stat-label">Version conflicts found</div></div>
      <div class="stat"><div class="stat-value">${d.duration}s</div><div class="stat-label">Analysis time, ${d.steps.length} agent steps</div></div>
    </div>

    <div class="card span-2">
      <div class="card-head"><div><h3>Blast radius</h3><div class="card-sub">Hover any node for details</div></div>${graphLegend(r.color, cr.action)}</div>
      <div class="graph" id="blast"></div>
    </div>

    <div class="card span-1">
      <div class="card-head"><h3>Why this risk level</h3></div>
      <ul class="reasons">${(d.risk_reasons || []).map((x) => `<li>${icon("chev")}<span>${esc(x)}</span></li>`).join("")}</ul>
    </div>

    <div class="card span-3">
      <div class="card-head"><div><h3>Compatibility by project</h3><div class="card-sub">Read live from each project's own virtual environment</div></div></div>
      ${compatTable(checks, cr)}
    </div>

    <div class="card span-3" id="verify-card"></div>

    <div class="card span-3">
      <div class="card-head"><h3>Evidence trail</h3><span class="card-sub">${(d.findings || []).length} findings</span></div>
      ${evidenceList(d.findings || [])}
    </div>
  </div>`;

  renderBlast($("#blast"), {
    package: cr.package_name,
    locations: d.locations || [],
    checks,
    affected: new Set(d.affected_projects || []),
    color: r.color,
    action: cr.action,
  });
  renderVerify(d);
  $("#dl-report").addEventListener("click", () => downloadReport(d));
}

function graphLegend(color, action) {
  const depLabel = action === "remove" ? "Breaks if removed" : "Conflicting dependent";
  return `<div class="legend">
    <span class="legend-item"><span class="swatch ring" style="--risk-color:${color}"></span>Affected project</span>
    <span class="legend-item"><span class="swatch dash"></span>Separate venv, not affected</span>
    <span class="legend-item"><span class="swatch" style="background:var(--critical)"></span>${depLabel}</span>
    <span class="legend-item"><span class="swatch" style="background:var(--text-2)"></span>Dependent package</span>
  </div>`;
}

function compatTable(checks, cr) {
  if (!checks.length) return `<div class="empty">${icon("info")}<h3>Nothing to check</h3>The package is not installed in any scanned project.</div>`;
  const isRemove = cr.action === "remove";
  const rows = checks.map((c) => {
    if (c.error) return `<tr><td class="strong">${esc(c.project)}</td><td colspan="6">${pill(c.error, "warn", "alert")}</td></tr>`;
    const py = c.python_ok === true ? pill("OK", "good", "check") : c.python_ok === false ? pill("Unsupported", "crit", "octagon") : pill("n/a");
    const wheel = c.wheel_status === "wheel" ? pill("Wheel", "good", "check")
      : c.wheel_status === "sdist_only" ? pill("Source only", "warn", "alert")
      : c.wheel_status === "none" ? pill("None", "crit", "octagon") : pill("n/a");
    const issues = isRemove ? (c.breaks_on_remove || []) : (c.conflicts || []);
    const issueCell = issues.length
      ? issues.slice(0, 6).map((x) => pill(`${x.package} ${x.specifier}`, "crit", "octagon")).join(" ") + (issues.length > 6 ? ` <span class="cell-sub">+${issues.length - 6} more</span>` : "")
      : pill("None", "good", "check");
    const chain = (c.chains || [])[0];
    return `<tr>
      <td class="strong">${esc(c.project)}<span class="cell-sub">Python ${esc(c.python_version || "?")}</span></td>
      <td><span class="mono">${esc(c.installed_version || "not installed")}</span></td>
      <td>${c.is_direct ? pill("Direct", "accent") : pill("Transitive")}${chain ? `<span class="cell-sub">via ${esc(chain.slice(0, -1).join(" → "))}</span>` : ""}</td>
      <td><b style="color:var(--text)">${(c.required_by || []).length}</b> direct<span class="cell-sub">${c.dependent_count || 0} in total</span></td>
      <td>${py}</td><td>${wheel}</td><td>${issueCell}</td>
    </tr>`;
  }).join("");
  return `<div class="table-wrap"><table>
    <thead><tr><th>Project</th><th>Installed</th><th>Declared</th><th>Needed by</th><th>Python</th><th>Wheel</th><th>${isRemove ? "Would break" : "Conflicts"}</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

function evidenceList(findings) {
  const groups = [["compatibility", "Compatibility checks"], ["graph", "Dependency graph"], ["inventory", "Installed packages"], ["evidence", "PyPI metadata"]];
  return groups.map(([key, label], i) => {
    const items = findings.filter((f) => f.source === key);
    if (!items.length) return "";
    return `<details class="ev" ${i === 0 ? "open" : ""}><summary><span>${label} <span class="card-sub">(${items.length})</span></span>${icon("chev", "chev")}</summary>
      <ul>${items.map((f) => `<li>${esc(f.text.length > 320 ? f.text.slice(0, 320) + "..." : f.text)}</li>`).join("")}</ul></details>`;
  }).join("");
}

/* ---------- Blast radius graph (pure SVG, radial layout) ---------- */
function renderBlast(el, opts) {
  const W = 760, H = 470, cx = W / 2, cy = H / 2, R1 = 118, R2 = 196;
  const { locations, checks, affected, color, action } = opts;
  const byProject = Object.fromEntries(checks.map((c) => [c.project, c]));
  const n = Math.max(locations.length, 1);
  const rad = (deg) => (deg * Math.PI) / 180;
  const textW = (s, size = 7) => s.length * size + 22;
  let edges = "", nodes = "", outer = "";

  locations.forEach((loc, i) => {
    const angle = -90 + (i * 360) / n;
    const px = cx + R1 * Math.cos(rad(angle)), py = cy + R1 * Math.sin(rad(angle));
    const hit = affected === null || affected.has(loc.project_name);
    const check = byProject[loc.project_name];
    edges += `<line class="g-edge ${hit ? "hit" : "dash"}" x1="${cx}" y1="${cy}" x2="${px}" y2="${py}" style="${hit ? `stroke:${color}` : ""}"/>`;
    const vx = (px - cx) / R1, vy = (py - cy) / R1;
    const lx0 = cx + (px - cx) * 0.45 - vy * 12, ly0 = cy + (py - cy) * 0.45 + vx * 12 + 4;
    edges += `<text class="g-small" x="${lx0}" y="${ly0}" text-anchor="middle">${esc(loc.version)}</text>`;

    // Outer ring: installed packages in this project that require the package
    if (hit && check && !check.error) {
      const issues = new Set((action === "remove" ? check.breaks_on_remove || [] : check.conflicts || []).map((x) => x.package));
      const deps = [...(check.required_by || [])].sort((a, b) => (issues.has(b.package) ? 1 : 0) - (issues.has(a.package) ? 1 : 0)).slice(0, 7);
      const span = Math.min(110, 300 / n);
      deps.forEach((dep, j) => {
        const a = deps.length === 1 ? angle : angle - span / 2 + (j * span) / (deps.length - 1);
        const dx = cx + R2 * Math.cos(rad(a)), dy = cy + R2 * Math.sin(rad(a));
        const bad = issues.has(dep.package);
        const anchor = Math.cos(rad(a)) > 0.25 ? "start" : Math.cos(rad(a)) < -0.25 ? "end" : "middle";
        const lx = dx + (anchor === "start" ? 10 : anchor === "end" ? -10 : 0);
        const ly = dy + (anchor === "middle" ? (Math.sin(rad(a)) < 0 ? -12 : 18) : 4);
        const tip = `<b>${esc(dep.package)}</b> in ${esc(loc.project_name)}<br>requires ${esc(opts.package)} ${esc(dep.specifier)}${bad ? `<br><span style="color:var(--critical)">${action === "remove" ? "Breaks if removed" : "Conflicts with the target version"}</span>` : ""}`;
        outer += `<line class="g-edge" x1="${px}" y1="${py}" x2="${dx}" y2="${dy}" style="${bad ? "stroke:var(--critical)" : ""}"/>`;
        outer += `<g class="g-node" data-tip="${esc(tip)}">
          <circle cx="${dx}" cy="${dy}" r="14" fill="transparent"/>
          <circle cx="${dx}" cy="${dy}" r="${bad ? 7 : 5.5}" style="fill:${bad ? "var(--critical)" : "var(--text-2)"};stroke:var(--surface);stroke-width:2"/>
          <text class="g-label" x="${lx}" y="${ly}" text-anchor="${anchor}">${esc(dep.package)}</text></g>`;
      });
    }

    const w = textW(loc.project_name);
    const extra = hit && check && !check.error ? (check.required_by || []).length - Math.min(7, (check.required_by || []).length) : 0;
    if (extra > 0) {
      nodes += `<text class="g-small" x="${px + w / 2 + 8}" y="${py + 4}">+${extra}</text>`;
    }
    const tip = `<b>${esc(loc.project_name)}</b><br>${esc(opts.package)} ${esc(loc.version)}` +
      (check && !check.error ? `<br>${check.is_direct ? "Declared directly" : "Transitive dependency"}<br>${(check.required_by || []).length} packages need it directly, ${check.dependent_count} in total` : "") +
      (hit ? "" : "<br><i>Separate environment, not affected</i>");
    nodes += `<g class="g-node" data-tip="${esc(tip)}">
      <rect x="${px - w / 2}" y="${py - 16}" width="${w}" height="32" rx="16"
        style="fill:var(--surface-2);stroke:${hit ? color : "var(--muted)"};stroke-width:${hit ? 2 : 1.5};${hit ? "" : "stroke-dasharray:5 4"}"/>
      <text class="g-label strong" x="${px}" y="${py + 4}" text-anchor="middle" style="${hit ? "" : "fill:var(--muted)"}">${esc(loc.project_name)}</text></g>`;
  });

  const center = `<g class="g-node" data-tip="<b>${esc(opts.package)}</b><br>Installed in ${locations.length} project(s)">
    <circle cx="${cx}" cy="${cy}" r="46" style="fill:${color};opacity:.16"/>
    <circle cx="${cx}" cy="${cy}" r="34" style="fill:${color}"/>
    <text x="${cx}" y="${cy + 5}" text-anchor="middle" style="fill:#fff;font-weight:700;font-size:13px;font-family:Inter,sans-serif">${esc(opts.package)}</text></g>`;

  el.innerHTML = locations.length
    ? `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Blast radius of ${esc(opts.package)}">${outer}${edges}${nodes}${center}</svg>`
    : `<div class="empty">${icon("info")}<h3>Not installed anywhere</h3>No scanned project has ${esc(opts.package)} installed.</div>`;
}

/* ---------- Verify (human-approved dry run) ---------- */
function renderVerify(d) {
  const el = $("#verify-card");
  const cr = d.change_request;
  const head = `<div class="card-head"><div><h3>Verify with pip</h3><div class="card-sub">Human approval required</div></div>${icon("shield")}</div>`;
  let blocker = "";
  if (d.is_noop) blocker = "Nothing would change, so there is nothing to verify.";
  else if (!d.affected_projects.length) blocker = "No scanned project is affected.";
  else if (cr.action !== "remove" && !cr.target_version) blocker = "A dry run needs a target version. Ask again with a version number.";
  if (blocker) { el.innerHTML = `${head}<p class="card-sub">${esc(blocker)}</p>`; return; }

  el.innerHTML = `${head}
    <p class="card-sub" style="margin:0">Runs pip's resolver with <code class="mono-inline">--dry-run</code>, keeping every dependent package at its installed version. Nothing is installed or removed.</p>
    <label class="toggle"><input type="checkbox" id="approve"><span class="switch"></span>
      <span>I approve a dry run on <b style="color:var(--text)">${d.affected_projects.map(esc).join(", ")}</b></span></label>
    <button class="primary-btn" id="verify-btn" type="button" disabled>${"Verify with dry run"}</button>
    <div id="dry-out"></div>`;
  $("#approve").addEventListener("change", (e) => { $("#verify-btn").disabled = !e.target.checked; });
  $("#verify-btn").addEventListener("click", () => runDryRun(d));
}

function dryItem(r) {
  const [kind, ic, label] = DRY[r.status] || ["warn", "alert", r.status];
  const lines = [...(r.changes || []), ...(r.details || [])];
  return `<div class="dry-head"><b>${esc(r.project)}</b>${pill(label, kind, ic)}</div>
    <div class="dry-summary">${esc(r.summary)}</div>
    ${r.command ? `<code class="dry-cmd">${esc(r.command)}</code>` : ""}
    ${lines.length ? `<ul class="dry-details">${lines.slice(0, 8).map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : ""}`;
}

async function runDryRun(d) {
  const btn = $("#verify-btn");
  btn.disabled = true;
  btn.textContent = "Running pip...";
  const out = $("#dry-out");
  out.innerHTML = '<div class="dry-list"></div>';
  const list = $(".dry-list", out);
  const items = {};
  try {
    await streamNDJSON("/api/dryrun", {
      package: d.change_request.package_name,
      action: d.change_request.action,
      target_version: d.change_request.target_version,
      projects: d.affected_projects,
      memory_id: d.memory_id,
    }, (ev) => {
      if (ev.type === "progress") {
        const div = document.createElement("div");
        div.className = "dry-item";
        div.innerHTML = `<div class="dry-head"><b>${esc(ev.project)}</b><span class="spinner"></span></div><div class="dry-summary">Asking pip's resolver...</div>`;
        list.appendChild(div);
        items[ev.project] = div;
      } else if (ev.type === "result") {
        const div = items[ev.data.project];
        if (div) div.innerHTML = dryItem(ev.data);
      } else if (ev.type === "done") {
        const [kind, ic, label] = DRY[ev.overall] || ["warn", "alert", ev.overall];
        out.insertAdjacentHTML("afterbegin", `<div class="overall">Overall ${pill(label, kind, ic)}</div>`);
      }
    });
    btn.textContent = "Verified";
  } catch (err) {
    out.insertAdjacentHTML("beforeend", `<div class="error-box">${icon("alert")}<div>${esc(err.message)}</div></div>`);
    btn.disabled = false;
    btn.textContent = "Verify with dry run";
  }
}

function downloadReport(d) {
  const cr = d.change_request;
  const lines = [
    "# Change impact report", "",
    `**Question:** ${d.query}`,
    `**Risk:** ${d.risk_level.toUpperCase()}`,
    `**Affected projects:** ${d.affected_projects.join(", ") || "none"}`, "",
    "## Report", "", d.narrative, "",
    "## Why this risk level", "", ...d.risk_reasons.map((x) => `- ${x}`), "",
    "## Evidence", "", ...d.findings.map((f) => `- [${f.source}] ${f.text.length > 300 ? f.text.slice(0, 300) + "..." : f.text}`),
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `impact-${cr.package_name}-${cr.action}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ================= Inventory ================= */
async function loadInventory() {
  const body = $("#inventory-body");
  try {
    const inv = await getJSON("/api/inventory");
    loaded.inventory = true;
    const projects = inv.projects || [];
    const shared = inv.shared || [];
    const total = projects.reduce((n, p) => n + p.packages, 0);
    const drift = shared.filter((s) => s.version_count > 1);
    const max = Math.max(1, ...projects.map((p) => p.packages));
    body.innerHTML = `
      <div class="stats">
        <div class="stat"><div class="stat-value">${projects.length}</div><div class="stat-label">Projects with a virtualenv</div></div>
        <div class="stat"><div class="stat-value">${total}</div><div class="stat-label">Installed packages</div></div>
        <div class="stat"><div class="stat-value">${shared.length}</div><div class="stat-label">Shared across projects</div></div>
        <div class="stat"><div class="stat-value">${drift.length}</div><div class="stat-label">With version drift</div></div>
      </div>
      <div class="section"><div class="section-title"><h3>Projects</h3><span class="card-sub">Click a project to see its packages</span></div>
        <div class="project-grid">${projects.map((p) => `
          <div class="card project-card" data-project="${esc(p.project)}">
            <div class="project-name">${esc(p.project)}</div>
            <div class="project-count">${p.packages}<span>packages</span></div>
            <div class="bar-track" data-tip="${p.packages} of ${max} (largest project)"><div class="bar-fill" style="width:${(p.packages / max) * 100}%"></div></div>
            <div class="path mono">${esc(p.path)}</div>
          </div>`).join("")}</div>
      </div>
      <div class="section card" id="pkg-panel"><div class="empty">${icon("grid")}<h3>Pick a project</h3>Its full package list appears here.</div></div>
      <div class="section card">
        <div class="section-title"><div><h3>Shared dependencies</h3><div class="card-sub">A change to any of these touches more than one project</div></div></div>
        <div class="table-wrap scroll-y"><table>
          <thead><tr><th>Package</th><th>Projects</th><th>Used by</th><th>Versions</th><th>Drift</th></tr></thead>
          <tbody>${shared.map((s) => `<tr>
            <td class="strong">${esc(s.package)}</td><td>${s.project_count}</td><td>${s.projects.map(esc).join(", ")}</td>
            <td class="mono">${s.versions.map(esc).join(", ")}</td>
            <td>${s.version_count > 1 ? pill("Drift", "warn", "alert") : pill("Aligned", "good", "check")}</td></tr>`).join("")}</tbody>
        </table></div>
      </div>`;
    $$(".project-card", body).forEach((card) => card.addEventListener("click", () => {
      $$(".project-card", body).forEach((c) => c.classList.toggle("active", c === card));
      loadPackages(card.dataset.project);
    }));
  } catch (err) {
    body.innerHTML = `<div class="error-box">${icon("alert")}<div>Could not load the inventory: ${esc(err.message)}</div></div>`;
  }
}

async function loadPackages(project) {
  const panel = $("#pkg-panel");
  panel.innerHTML = '<div class="skeleton"></div>';
  const rows = await getJSON(`/api/projects/${encodeURIComponent(project)}/packages`);
  panel.innerHTML = `<div class="section-title"><div><h3>${esc(project)}</h3><div class="card-sub">${rows.length} packages</div></div>
    <input class="filter" id="pkg-filter" placeholder="Filter packages..."></div>
    <div class="table-wrap scroll-y"><table><thead><tr><th>Package</th><th>Version</th><th>Requires Python</th></tr></thead><tbody id="pkg-rows"></tbody></table></div>`;
  const draw = (q) => {
    const f = rows.filter((r) => r.name.toLowerCase().includes(q.toLowerCase()));
    $("#pkg-rows").innerHTML = f.map((r) => `<tr><td class="strong">${esc(r.name)}</td><td class="mono">${esc(r.version)}</td><td class="mono">${esc(r.requires_python || "")}</td></tr>`).join("");
  };
  draw("");
  $("#pkg-filter").addEventListener("input", (e) => draw(e.target.value));
}

/* ================= Explorer ================= */
async function explore(pkg) {
  pkg = pkg.trim();
  if (!pkg) return;
  const out = $("#explore-result");
  out.innerHTML = '<div class="skeleton tall"></div>';
  try {
    const data = await getJSON(`/api/explore/${encodeURIComponent(pkg)}`);
    if (!data.locations.length) {
      out.innerHTML = `<div class="card empty" style="margin-top:18px">${icon("search")}<h3>Not installed anywhere</h3>No scanned project has ${esc(pkg)} installed.</div>`;
      return;
    }
    const versions = [...new Set(data.locations.map((l) => l.version))];
    out.innerHTML = `
      <div class="bento">
        <div class="card span-2"><div class="card-head"><div><h3>${esc(pkg)} across your projects</h3><div class="card-sub">Hover a node for details</div></div>
          ${versions.length > 1 ? pill(`Version drift: ${versions.join(", ")}`, "warn", "alert") : pill(`Version ${versions[0]} everywhere`, "good", "check")}</div>
          <div class="graph" id="explore-graph"></div></div>
        <div class="card span-1"><div class="card-head"><h3>Why it is installed</h3></div>
          ${data.projects.map((p) => `<div class="dry-item" style="margin-bottom:10px">
            <div class="dry-head"><b>${esc(p.project)}</b>${p.error ? pill("Unreadable", "warn", "alert") : p.is_direct ? pill("Direct", "accent") : pill("Transitive")}</div>
            <div class="dry-summary">${p.error ? esc(p.error) : `${(p.required_by || []).length} packages need it directly, ${p.dependent_count} in total.`}</div>
            ${(p.chains || []).slice(0, 2).map((c) => `<code class="dry-cmd">${c.map(esc).join(" → ")}</code>`).join("")}
          </div>`).join("")}
        </div>
      </div>`;
    const checks = data.projects.filter((p) => !p.error).map((p) => ({ ...p, conflicts: [], breaks_on_remove: [] }));
    renderBlast($("#explore-graph"), { package: pkg, locations: data.locations, checks, affected: null, color: "var(--accent)", action: "explore" });
  } catch (err) {
    out.innerHTML = `<div class="error-box">${icon("alert")}<div>${esc(err.message)}</div></div>`;
  }
}

/* ================= History ================= */
async function loadHistory() {
  const body = $("#history-body");
  try {
    const records = await getJSON("/api/history");
    if (!records.length) {
      body.innerHTML = `<div class="card empty">${icon("memory")}<h3>No analyses yet</h3>Run one from the Analyze page and it will be remembered here.</div>`;
      return;
    }
    const count = (lvl) => records.filter((r) => r.risk_level === lvl).length;
    body.innerHTML = `
      <div class="stats">
        <div class="stat"><div class="stat-value">${records.length}</div><div class="stat-label">Analyses remembered</div></div>
        <div class="stat"><div class="stat-value">${count("high")}</div><div class="stat-label">Rated high risk</div></div>
        <div class="stat"><div class="stat-value">${count("medium") + count("low")}</div><div class="stat-label">Rated medium or low</div></div>
        <div class="stat"><div class="stat-value">${records.filter((r) => r.dry_run_status).length}</div><div class="stat-label">Verified with a dry run</div></div>
      </div>
      <div class="timeline section">${records.map((r, i) => {
        const risk = RISK[r.risk_level] || RISK.low;
        const kind = { critical: "crit", warning: "warn", good: "good" }[risk.cls];
        const dry = r.dry_run_status ? DRY[r.dry_run_status] || ["warn", "alert", r.dry_run_status] : null;
        return `<div class="card h-item" data-i="${i}">
          <div class="h-row">${pill(risk.label, kind, risk.icon)}<div class="h-q">${esc(r.query)}</div>${icon("chev", "chev")}</div>
          <div class="h-meta"><span>${esc(r.created_at)}</span><span>·</span><span>${esc(r.projects.join(", ") || "no projects affected")}</span>
            ${dry ? `<span>·</span>${pill(`Dry run: ${dry[2]}`, dry[0], dry[1])}` : ""}</div>
          <div class="h-body hidden"><div class="narrative">${renderNarrative(r.report)}</div>
            ${r.dry_run_summary ? `<div class="callout">${icon("shield")}<div><b>Dry run:</b> ${esc(r.dry_run_summary)}</div></div>` : ""}</div>
        </div>`;
      }).join("")}</div>`;
    $$(".h-item", body).forEach((item) => item.addEventListener("click", () => $(".h-body", item).classList.toggle("hidden")));
  } catch (err) {
    body.innerHTML = `<div class="error-box">${icon("alert")}<div>Could not load history: ${esc(err.message)}</div></div>`;
  }
}

/* ================= Boot ================= */
hydrateIcons();
renderExamples();
$("#ask-form").addEventListener("submit", (e) => { e.preventDefault(); runAnalysis($("#ask-input").value); });
$("#explore-form").addEventListener("submit", (e) => { e.preventDefault(); explore($("#explore-input").value); });
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement.tagName !== "INPUT") { e.preventDefault(); location.hash = "#analyze"; $("#ask-input").focus(); }
});
route();
loadHealth();
setInterval(loadHealth, 30000);