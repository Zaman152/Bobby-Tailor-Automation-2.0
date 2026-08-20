/* Bobby Tailor v2 — app controller.
   Hash-routed views over the existing API. No framework, no build step. */
"use strict";

const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || "";
const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v) => (v === null || v === undefined || v === "" ? null : Number(v));
const fmt = (v) => (num(v) === null || Number.isNaN(num(v))) ? "—"
  : Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });

async function api(url, opts = {}) {
  const o = { headers: {}, ...opts };
  if (o.body && !(o.body instanceof FormData)) {
    o.headers["Content-Type"] = "application/json";
    o.body = JSON.stringify(o.body);
  }
  if (o.method && o.method !== "GET") o.headers["X-CSRFToken"] = CSRF;
  const r = await fetch(url, o);
  const text = await r.text();
  let data = null; try { data = text ? JSON.parse(text) : null; } catch { /* not json */ }
  if (!r.ok) throw new Error(data?.error || `${r.status} ${r.statusText}`);
  return data;
}
const note = (kind, title, body) =>
  `<div class="note ${kind}"><span class="eyebrow">${esc(title)}</span><p>${body}</p></div>`;

/* ── router ─────────────────────────────────────────────────────────── */
const VIEWS = ["new", "progress", "reports", "worksheet", "history", "guide"];
let state = { uploadId: null, manifestId: null, jobId: null, run: null, rows: [], poll: null };

function show(view) {
  VIEWS.forEach((v) => { const el = $(`section[data-view="${v}"]`); if (el) el.hidden = v !== view; });
  $$("#nav a").forEach((a) => a.removeAttribute("aria-current"));
  const link = $(`#nav a[data-view="${view}"]`);
  if (link) link.setAttribute("aria-current", "page");
  window.scrollTo(0, 0);
}
function route() {
  const [, view, arg] = (location.hash || "#/new").split("/");
  if (view === "reports")  { show("reports");  return loadReports(); }
  if (view === "history")  { show("history");  return loadHistory(); }
  if (view === "guide")    { return show("guide"); }
  if (view === "run")      { show("worksheet"); return loadWorksheet(decodeURIComponent(arg || "")); }
  if (view === "progress") { return show("progress"); }
  show("new");
}
addEventListener("hashchange", route);

/* ── step 1: plans ──────────────────────────────────────────────────── */
function wireDrop(dropEl, inputEl, onFile) {
  dropEl.addEventListener("click", () => inputEl.click());
  dropEl.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inputEl.click(); } });
  ["dragenter", "dragover"].forEach((t) => dropEl.addEventListener(t, (e) => { e.preventDefault(); dropEl.dataset.over = "1"; }));
  ["dragleave", "drop"].forEach((t) => dropEl.addEventListener(t, (e) => { e.preventDefault(); delete dropEl.dataset.over; }));
  dropEl.addEventListener("drop", (e) => { const f = e.dataTransfer?.files?.[0]; if (f) onFile(f); });
  inputEl.addEventListener("change", () => { const f = inputEl.files?.[0]; if (f) onFile(f); });
}

async function uploadPlans(file) {
  $("#dropTitle").textContent = `Reading ${file.name}…`;
  $("#uploadNote").innerHTML = "";
  try {
    const fd = new FormData(); fd.append("file", file);
    const d = await api("/api/pdf/upload", { method: "POST", body: fd });
    state.uploadId = d.upload_id;
    $("#dropTitle").textContent = file.name;
    $("#dropSub").textContent = `${d.page_count} page${d.page_count === 1 ? "" : "s"} · ready`;
    if (!$("#projName").value) $("#projName").value = (d.filename || "").replace(/\.pdf$/i, "");
    $("#sheetsBody").innerHTML = (d.pages || []).map((p) =>
      `<tr><td class="mono">${p.page_num}</td><td>${esc(p.sheet_name || "—")}</td>
        <td class="muted">${esc((p.sheet_type_hint || "").replace(/_/g, " "))}</td></tr>`).join("");
    $("#sheetsWrap").hidden = false;
    if (d.plans_only_warning) {
      $("#uploadNote").innerHTML = note("note-warn", "This looks like a take-off",
        esc(d.plans_only_warning) +
        `<br><label class="ui" style="display:flex;gap:8px;align-items:center;margin-top:8px;font-weight:500">
          <input type="checkbox" id="ackTakeoff"> I confirm this file is a set of PLANS</label>`);
      $("#ackTakeoff").addEventListener("change", refreshRunGate);
    }
    refreshRunGate();
  } catch (err) {
    $("#dropTitle").textContent = "Drop a PDF here, or click to browse";
    $("#uploadNote").innerHTML = note("note-warn", "Could not read that file", esc(err.message));
    state.uploadId = null; refreshRunGate();
  }
}

async function uploadManifest(file) {
  $("#mdropTitle").textContent = `Reading ${file.name}…`;
  try {
    const fd = new FormData(); fd.append("file", file);
    const d = await api("/api/pdf/manifest/upload", { method: "POST", body: fd });
    state.manifestId = d.manifest_id;
    $("#mdropTitle").textContent = file.name;
    $("#manifestNote").innerHTML = note("note-key", "Catalog loaded",
      `<b>${d.count}</b> objects. Every one will appear in the take-off — measured, or flagged so nothing is silently missed.`);
  } catch (err) {
    $("#mdropTitle").textContent = "Drop a manifest (.json or .csv)";
    $("#manifestNote").innerHTML = note("note-warn", "Could not read that manifest", esc(err.message));
    state.manifestId = null;
  }
}

function refreshRunGate() {
  const ack = $("#ackTakeoff");
  const blocked = !state.uploadId || (ack && !ack.checked);
  $("#runBtn").disabled = blocked;
  $("#runHint").textContent = !state.uploadId ? "Upload a PDF to begin."
    : (ack && !ack.checked) ? "Confirm the file is plans before running."
    : state.manifestId ? "Ready. Your catalog is attached."
    : "Ready. Running without a catalog is fine — names will come from the drawings.";
}

/* ── step 3: run + progress ─────────────────────────────────────────── */
async function startRun() {
  $("#runBtn").disabled = true;
  try {
    const body = { upload_id: state.uploadId, project_name: $("#projName").value || "Untitled" };
    if (state.manifestId) body.manifest_id = state.manifestId;
    const d = await api("/api/pdf/run", { method: "POST", body });
    state.jobId = d.job_id;
    $("#pgProject").textContent = body.project_name;
    location.hash = "#/progress"; show("progress");
    poll();
  } catch (err) {
    $("#runGuard").innerHTML = note("note-warn", "Could not start", esc(err.message));
    refreshRunGate();
  }
}

function poll() {
  clearInterval(state.poll);
  let fails = 0;
  state.poll = setInterval(async () => {
    try {
      const s = await api(`/api/status/${state.jobId}`);
      fails = 0;
      const pct = Math.max(0, Math.min(100, Number(s.percent ?? s.progress ?? 0)));
      $("#pgBar").style.width = pct + "%";
      $("#pgPct").textContent = Math.round(pct) + "%";
      $("#pgPhase").textContent = s.phase || s.status || "Working…";
      $("#pgSheet").textContent = s.current_sheet ? `Sheet ${esc(s.current_sheet)}` : "";
      if (Array.isArray(s.log)) $("#pgLog").textContent = s.log.slice(-60).join("\n");
      if (s.status === "complete" || s.status === "completed" || s.run_folder) {
        clearInterval(state.poll);
        if (s.run_folder) location.hash = `#/run/${encodeURIComponent(s.run_folder)}`;
        else location.hash = "#/reports";
      }
      if (s.status === "error" || s.status === "failed") {
        clearInterval(state.poll);
        $("#pgAlert").innerHTML = note("note-warn", "The run stopped", esc(s.error || "See the log below."));
      }
    } catch (err) {
      if (String(err.message).startsWith("401")) { clearInterval(state.poll); location.href = "/login"; return; }
      if (++fails >= 3) {
        clearInterval(state.poll);
        $("#pgAlert").innerHTML = note("note-warn", "Lost contact with the run",
          "Three status checks failed, so polling stopped. The run may still be going — check Reports in a few minutes.");
      }
    }
  }, 2000);
}

/* ── reports ────────────────────────────────────────────────────────── */
async function loadReports() {
  const body = $("#reportsBody");
  try {
    const d = await api("/api/reports");
    const rows = Array.isArray(d) ? d : (d.reports || []);
    body.innerHTML = rows.length ? rows.map((r) => `
      <tr><td><b class="ui">${esc(r.project_name || r.run_folder)}</b></td>
        <td class="muted">${esc(r.created || r.timestamp || "")}</td>
        <td class="num">${esc(r.sheets_processed ?? "—")}</td>
        <td class="num">${esc(r.calculated_count ?? "—")}</td>
        <td class="num">${r.total_cost_usd ? "$" + Number(r.total_cost_usd).toFixed(2) : "—"}</td>
        <td><a class="btn btn-quiet" href="#/run/${encodeURIComponent(r.run_folder)}">Open</a></td></tr>`).join("")
      : `<tr><td colspan="6" class="muted">No reports yet. Start a take-off to make one.</td></tr>`;
  } catch (err) { body.innerHTML = `<tr><td colspan="6" class="muted">${esc(err.message)}</td></tr>`; }
}

async function loadHistory() {
  const body = $("#histBody");
  try {
    const d = await api("/api/jobs/history");
    const rows = Array.isArray(d) ? d : (d.jobs || d.history || []);
    body.innerHTML = rows.length ? rows.map((j) => `
      <tr><td>${esc(j.project_name || j.job_id)}</td>
        <td class="muted">${esc(j.started_at || j.created || "")}</td>
        <td>${esc(j.status || "")}</td>
        <td class="num">${esc(j.sheets ?? "—")}</td>
        <td class="num">${j.cost_usd ? "$" + Number(j.cost_usd).toFixed(2) : "—"}</td></tr>`).join("")
      : `<tr><td colspan="5" class="muted">No jobs recorded yet.</td></tr>`;
  } catch (err) { body.innerHTML = `<tr><td colspan="5" class="muted">${esc(err.message)}</td></tr>`; }
}

/* ── worksheet ──────────────────────────────────────────────────────── */
const STATES = {
  "MEASURED":     ["chip-measured", "✓ Measured", "measured off the drawing; not yet confirmed by a human"],
  "NEEDS REVIEW": ["chip-review",   "! Needs review", "measured but flagged — confirm before bidding"],
  "NOT MEASURED": ["chip-blank",    "∅ Not measured", "no measurement path on these drawings. A blank, not a zero"],
  "NOT APPLICABLE":["chip-quiet",   "– Not applicable", "the set contains none of these"],
  "STANDARD ITEM":["chip-quiet",    "≡ Standard item", "a convention the app injects"],
  "HUMAN INPUT":  ["chip-human",    "✎ Human input", "you supplied this number"],
};
function chipFor(row) {
  const p = String(row.provenance || "").toUpperCase();
  const s = STATES[p] || (row.needs_review ? STATES["NEEDS REVIEW"] : STATES["MEASURED"]);
  return `<span class="chip ${s[0]}" title="${esc(s[2])}">${s[1]}</span>`;
}

async function loadWorksheet(run) {
  state.run = run;
  $("#wsCsv").href = `/api/reports/${encodeURIComponent(run)}/takeoff_summary.csv`;
  $("#wsCoverage").href = `/api/reports/${encodeURIComponent(run)}/coverage.json`;
  $("#wsProject").textContent = run;
  $("#wsBody").innerHTML = `<tr><td colspan="5" class="muted">Loading…</td></tr>`;
  try {
    const res = await api(`/api/reports/${encodeURIComponent(run)}/preview/takeoff.json`);
    const d = res?.data || res || {};
    state.rows = d.takeoff_summary || [];
    renderCoverage(d);
    renderRows();
  } catch (err) {
    $("#wsBody").innerHTML = `<tr><td colspan="5" class="muted">${esc(err.message)}</td></tr>`;
  }
}

function renderCoverage(d) {
  const c = d.coverage || d.coverage_ledger?.summary || {};
  const pct = num(c.coverage_pct_items);
  $("#wsPct").textContent = pct === null ? "—" : pct.toFixed(1) + "%";
  $("#wsBar").style.width = (pct || 0) + "%";
  const tally = {};
  state.rows.forEach((r) => { const p = String(r.provenance || "").toUpperCase() || "MEASURED"; tally[p] = (tally[p] || 0) + 1; });
  const order = ["MEASURED", "NEEDS REVIEW", "NOT MEASURED", "HUMAN INPUT", "STANDARD ITEM", "NOT APPLICABLE"];
  const colour = { "MEASURED": "var(--measured)", "NEEDS REVIEW": "var(--review)",
    "NOT MEASURED": "var(--blank)", "HUMAN INPUT": "var(--human)" };
  $("#wsCounts").innerHTML = order.filter((k) => tally[k]).map((k) =>
    `<div><span class="eyebrow">${esc(k.toLowerCase())}</span>
      <b style="color:${colour[k] || "var(--ink-2)"}">${tally[k]}</b></div>`).join("");
  const gaps = d.input_gaps || d.coverage_warnings || [];
  $("#wsGaps").innerHTML = (Array.isArray(gaps) && gaps.length)
    ? note("note-warn", "Input gaps", gaps.slice(0, 4).map((g) => esc(typeof g === "string" ? g : JSON.stringify(g))).join("<br>"))
    : "";
}

function renderRows() {
  const only = $("#wsOnlyFlagged").checked;
  const rows = only ? state.rows.filter((r) => r.needs_review || num(r.quantity) === null) : state.rows;
  $("#wsBody").innerHTML = rows.length ? rows.map((r) => {
    const q = num(r.quantity);
    const blank = q === null;
    const why = (r.review_reasons || [])[0] || r.detail?.[0]?.description || "";
    return `<tr data-item="${esc(r.item)}">
      <td>${chipFor(r)}</td>
      <td><b class="ui">${esc(r.item)}</b></td>
      <td class="qty ${blank ? "muted" : ""}" data-editable="1" tabindex="0"
          title="Click to type your own number">${blank ? "type a value" : fmt(q)}</td>
      <td class="mono">${esc(r.unit || "")}</td>
      <td class="muted" style="max-width:44ch">${esc(String(why).slice(0, 150))}</td></tr>`;
  }).join("") : `<tr><td colspan="5" class="muted">Nothing to show.</td></tr>`;
}

async function editQty(cell) {
  if (cell.querySelector("input")) return;
  const tr = cell.closest("tr"), item = tr.dataset.item;
  const row = state.rows.find((r) => String(r.item) === item);
  const cur = num(row?.quantity);
  cell.innerHTML = `<input class="input" type="number" step="any" style="width:11ch;text-align:right"
      value="${cur ?? ""}">`;
  const inp = cell.querySelector("input"); inp.focus(); inp.select();
  const commit = async () => {
    const v = parseFloat(inp.value);
    if (!Number.isFinite(v)) return renderRows();
    try {
      await api(`/api/reports/${encodeURIComponent(state.run)}/verify`,
        { method: "POST", body: { item, quantity: v, unit: row?.unit || "", verified: true } });
      await loadWorksheet(state.run);
    } catch (err) {
      cell.innerHTML = `<span class="muted">${esc(err.message)}</span>`;
    }
  };
  inp.addEventListener("keydown", (e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") renderRows(); });
  inp.addEventListener("blur", commit);
}

/* ── boot ───────────────────────────────────────────────────────────── */
addEventListener("DOMContentLoaded", () => {
  wireDrop($("#drop"),  $("#file"),  uploadPlans);
  wireDrop($("#mdrop"), $("#mfile"), uploadManifest);
  $("#runBtn").addEventListener("click", startRun);
  $("#cancelBtn").addEventListener("click", async () => {
    clearInterval(state.poll);
    try { await api(`/api/cancel/${state.jobId}`, { method: "POST" }); } catch { /* already gone */ }
    location.hash = "#/new";
  });
  $("#wsOnlyFlagged").addEventListener("change", renderRows);
  $("#wsBody").addEventListener("click", (e) => {
    const cell = e.target.closest('td.qty[data-editable="1"]'); if (cell) editQty(cell);
  });
  $("#wsBody").addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const cell = e.target.closest('td.qty[data-editable="1"]'); if (cell) { e.preventDefault(); editQty(cell); }
  });
  route();
});
