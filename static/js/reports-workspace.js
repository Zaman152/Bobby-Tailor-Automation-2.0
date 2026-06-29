/**
 * Report Preview Workspace — Bobby Tailor
 * Full-screen drawer with run list, tabs, and export rail
 * 
 * Replaces inline card accordion with dedicated preview experience
 * 
 * Usage:
 *   import { openReportWorkspace, closeReportWorkspace } from './reports-workspace.js';
 *   openReportWorkspace('takeoff_morehouse_2026-05-25_143022');
 */

import { animate } from 'https://cdn.jsdelivr.net/npm/motion@11.13.5/+esm';

let activeWorkspace = null;
let currentRun = null;
let currentTab = 'summary';
let allRuns = [];
let currentReportMeta = null;

const BASE_TAB_IDS = ['summary', 'calculations', 'raw', 'json'];
let TAB_IDS = [...BASE_TAB_IDS];

// Scale module state — calibration table + a sheet the user wants to focus on
// after clicking a source-sheet link in the Takeoff Summary.
let scaleCalibration = null;
let pendingScaleFocus = '';
let sheetImageMap = {};  // normalized sheet key → { sheet, image }

// Common architectural / engineering scales → feet represented by one inch.
const COMMON_SCALES = [
  { label: '3" = 1\'-0"',     fpi: 4 },
  { label: '1-1/2" = 1\'-0"', fpi: 8 },
  { label: '1" = 1\'-0"',     fpi: 12 },
  { label: '3/4" = 1\'-0"',   fpi: 16 },
  { label: '1/2" = 1\'-0"',   fpi: 24 },
  { label: '3/8" = 1\'-0"',   fpi: 32 },
  { label: '1/4" = 1\'-0"',   fpi: 48 },
  { label: '3/16" = 1\'-0"',  fpi: 64 },
  { label: '1/8" = 1\'-0"',   fpi: 96 },
  { label: '1" = 10\'',       fpi: 120 },
  { label: '1/16" = 1\'-0"',  fpi: 192 },
  { label: '1" = 20\'',       fpi: 240 },
  { label: '1" = 30\'',       fpi: 360 },
  { label: '1" = 40\'',       fpi: 480 },
  { label: '1" = 50\'',       fpi: 600 },
  { label: '1" = 60\'',       fpi: 720 },
];

/**
 * Open the report preview workspace
 * @param {string} runFolder - Report folder ID
 */
export async function openReportWorkspace(runFolder) {
  currentRun = runFolder;
  sheetImageMap = {};
  pendingScaleFocus = '';

  // Fetch report metadata
  let report;
  try {
    const response = await fetch(`/api/reports/${encodeURIComponent(runFolder)}`, { credentials: 'same-origin' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    report = await response.json();
  } catch (err) {
    console.error('Failed to load report metadata:', err);
    return;
  }
  currentReportMeta = report;

  // Build dynamic tab list — Takeoff Summary first if available, then the
  // Scale & Verify module (human-verifiable scale → exact recompute).
  TAB_IDS = report.files?.takeoff_summary_csv
    ? ['takeoff', 'scale', ...BASE_TAB_IDS]
    : ['scale', ...BASE_TAB_IDS];

  currentTab = TAB_IDS[0];

  // Override with URL param if valid
  const params = new URLSearchParams(window.location.search);
  if (params.get('tab') && TAB_IDS.includes(params.get('tab'))) {
    currentTab = params.get('tab');
  }
  
  // Build workspace HTML
  const workspace = document.createElement('div');
  workspace.className = 'report-workspace-overlay';
  workspace.innerHTML = `
    <div class="report-workspace">
      <div class="workspace-header">
        <div class="header-left">
          <button type="button" class="workspace-back-btn" aria-label="Close workspace">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
            <span>Back to Reports</span>
          </button>
        </div>
        <div class="header-center">
          <h2 class="workspace-title">${report.project_name || 'Report'}</h2>
          <div class="workspace-meta">
            <span class="meta-date">${formatDate(report.timestamp)}</span>
            ${renderCachePill(report)}
          </div>
        </div>
        <div class="header-right"></div>
      </div>
      
      <div class="workspace-body">
        <aside class="workspace-runs">
          <div class="runs-header">
            <h3>Report Runs</h3>
          </div>
          <div class="runs-list" id="workspaceRunsList">
            <div class="run-item active" data-folder="${runFolder}">
              <div class="run-label">Current Run</div>
              <div class="run-date">${formatDate(report.timestamp)}</div>
            </div>
          </div>
        </aside>
        
        <main class="workspace-content">
          <nav class="workspace-tabs" role="tablist">
            ${TAB_IDS.map(t => {
              const labels = { takeoff: 'Takeoff Summary', scale: 'Scale & Verify', summary: 'Run Log', calculations: 'Calculations', raw: 'Raw Data', json: 'JSON' };
              return `<button type="button" class="tab-btn ${currentTab === t ? 'active' : ''}" data-tab="${t}" role="tab" aria-selected="${currentTab === t}">${labels[t] || t}</button>`;
            }).join('')}
          </nav>
          
          <div class="tab-content" id="workspaceTabContent">
            <div class="loading-spinner">Loading...</div>
          </div>
        </main>
        
        <aside class="workspace-export">
          <div class="export-header">
            <h3>Downloads</h3>
          </div>
          <div class="export-actions">
            ${report.files?.takeoff_summary_csv ? `
            <button type="button" class="export-btn export-btn-primary" data-type="takeoff">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              <span>Takeoff Summary CSV</span>
            </button>` : ''}
            <button type="button" class="export-btn" data-type="calculations">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              <span>Calculations CSV</span>
            </button>
            <button type="button" class="export-btn" data-type="raw">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              <span>Raw CSV</span>
            </button>
            <button type="button" class="export-btn" data-type="json">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              <span>JSON Export</span>
            </button>
            <button type="button" class="export-btn" data-type="summary">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              <span>Summary TXT</span>
            </button>
          </div>
        </aside>
      </div>
    </div>
  `;
  
  document.body.appendChild(workspace);
  activeWorkspace = workspace;
  
  // Event listeners
  workspace.querySelector('.workspace-back-btn').addEventListener('click', closeReportWorkspace);
  workspace.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
  workspace.querySelectorAll('.export-btn').forEach(btn => {
    btn.addEventListener('click', () => exportReport(currentRun, btn.dataset.type));
  });
  
  // Keyboard shortcuts
  document.addEventListener('keydown', handleWorkspaceKeyboard);
  
  // Animate entrance
  if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const drawer = workspace.querySelector('.report-workspace');
    animate(workspace, { opacity: [0, 1] }, { duration: 0.25 });
    animate(drawer, { x: ['100%', '0%'] }, { duration: 0.35, easing: [0.22, 1, 0.36, 1] });
  }
  
  // Load initial tab
  await loadTabContent(currentTab);
  
  // Update URL
  updateWorkspaceURL();
}

/**
 * Close the report preview workspace
 */
export function closeReportWorkspace() {
  if (!activeWorkspace) return;
  
  document.removeEventListener('keydown', handleWorkspaceKeyboard);
  
  const cleanup = () => {
    activeWorkspace.remove();
    activeWorkspace = null;
    currentRun = null;
    
    // Clear URL params
    const url = new URL(window.location);
    url.searchParams.delete('run');
    url.searchParams.delete('tab');
    window.history.replaceState({}, '', url);
  };
  
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    cleanup();
  } else {
    const drawer = activeWorkspace.querySelector('.report-workspace');
    Promise.all([
      animate(activeWorkspace, { opacity: 0 }, { duration: 0.2 }),
      animate(drawer, { x: '100%' }, { duration: 0.3 })
    ]).then(cleanup);
  }
}

/**
 * Switch to a different tab
 * @param {string} tabId - Tab identifier
 */
export async function switchTab(tabId) {
  if (!TAB_IDS.includes(tabId) || tabId === currentTab) return;
  
  currentTab = tabId;
  
  // Update tab buttons
  activeWorkspace.querySelectorAll('.tab-btn').forEach(btn => {
    const isActive = btn.dataset.tab === tabId;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-selected', isActive);
  });
  
  // Load content
  await loadTabContent(tabId);
  
  // Update URL
  updateWorkspaceURL();
}

async function loadTabContent(tabId) {
  const container = activeWorkspace.querySelector('#workspaceTabContent');
  container.innerHTML = '<div class="loading-spinner">Loading...</div>';
  
  try {
    switch (tabId) {
      case 'takeoff':
        await loadTakeoffTab(container);
        break;
      case 'scale':
        await loadScaleTab(container);
        break;
      case 'summary':
        await loadSummaryTab(container);
        break;
      case 'calculations':
        await loadCalculationsTab(container);
        break;
      case 'raw':
        await loadRawTab(container);
        break;
      case 'json':
        await loadJsonTab(container);
        break;
    }
  } catch (error) {
    container.innerHTML = `<div class="tab-error">Failed to load ${tabId} content: ${error.message}</div>`;
    console.error(`Tab load error (${tabId}):`, error);
  }
}

// Takeoff Summary is an interactive VERIFICATION WORKSHEET: every quantity can
// be edited or confirmed; verified lines lock to exact. Progress → 100%.
let takeoffRows = [];

async function loadTakeoffTab(container) {
  // Pull the structured summary from takeoff.json (richer than the CSV preview).
  const resp = await fetch(`/api/reports/${encodeURIComponent(currentRun)}/preview/takeoff.json`, { credentials: 'same-origin' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  if (data.error) throw new Error(data.error);
  const report = data.data ?? data;
  takeoffRows = report.takeoff_summary || [];
  ingestSheetAssets(report.sheet_assets || {});
  renderTakeoffWorksheet(container);
}

function normalizeSheetKey(name) {
  return String(name || '').split('/').pop().trim().toLowerCase().replace(/\s+/g, ' ');
}

function ingestSheetAssets(assets) {
  if (!assets || typeof assets !== 'object') return;
  for (const [name, meta] of Object.entries(assets)) {
    if (!meta || !meta.image) continue;
    sheetImageMap[normalizeSheetKey(name)] = { sheet: name, image: meta.image };
  }
}

async function ensureSheetImageMap() {
  if (Object.keys(sheetImageMap).length) return;
  try {
    const resp = await fetch(`/api/reports/${encodeURIComponent(currentRun)}/scale`, { credentials: 'same-origin' });
    if (!resp.ok) return;
    const data = await resp.json();
    for (const s of data.sheets || []) {
      if (!s.sheet) continue;
      sheetImageMap[normalizeSheetKey(s.sheet)] = {
        sheet: s.sheet,
        image: s.image || '',
      };
    }
  } catch (err) {
    console.warn('sheet image map load failed', err);
  }
}

function resolveSheetContext(token) {
  const raw = String(token || '').trim();
  if (!raw) return null;
  if (raw.includes('screenshots/') || /\.(png|jpg|jpeg)$/i.test(raw)) {
    let rel = raw.replace(/\\/g, '/');
    const idx = rel.indexOf('screenshots/');
    if (idx >= 0) rel = rel.slice(idx);
    else if (rel.startsWith('output/')) rel = rel.slice('output/'.length);
    return { imageRel: rel, sheet: raw, focusSheet: raw };
  }
  const key = normalizeSheetKey(raw);
  const hit = sheetImageMap[key];
  if (hit) return { imageRel: hit.image, sheet: hit.sheet, focusSheet: hit.sheet };
  for (const [k, v] of Object.entries(sheetImageMap)) {
    if (k.includes(key) || key.includes(k)) {
      return { imageRel: v.image, sheet: v.sheet, focusSheet: v.sheet };
    }
  }
  return { imageRel: '', sheet: raw, focusSheet: raw };
}

function rowStatus(r) {
  const src = String(r.source || '').toLowerCase();
  const qtyMissing = r.quantity === null || r.quantity === undefined ||
                     r.quantity_fmt === '—' || r.quantity === '—';
  if (src === 'user_verified') return { cls: 'verified', label: 'Verified', icon: '✓' };
  // Auto-accepted by the pipeline from a high-confidence (cleanly read) scale.
  if (!qtyMissing && !r.needs_review && (r.auto_verified || src === 'measured_auto'))
    return { cls: 'auto', label: 'Auto', icon: '⚡' };
  if (src === 'measured_verified') return { cls: 'measured', label: 'Measured', icon: '▣' };
  if (r.needs_review || qtyMissing) return { cls: 'review', label: 'Needs review', icon: '!' };
  return { cls: 'ok', label: 'Confirmed', icon: '✓' };
}

function isVerifiedRow(r) {
  const s = rowStatus(r);
  return s.cls === 'verified' || s.cls === 'measured' || s.cls === 'auto' || s.cls === 'ok';
}

// A line is unproven when it still needs review or has no usable quantity.
function rowNeedsVerification(r) {
  return rowStatus(r).cls === 'review';
}
function rowQtyNum(r) {
  const q = r.quantity;
  if (q === null || q === undefined || q === '—' || q === '') return null;
  const n = parseFloat(String(q).replace(/,/g, ''));
  return Number.isFinite(n) ? n : null;
}

// View state: focus on only the lines that still need attention.
let wsFocusNeedsReview = false;

function renderTakeoffWorksheet(container) {
  const total = takeoffRows.length;
  const needs = takeoffRows.filter(rowNeedsVerification);
  const verified = total - needs.length;
  const needsValue = needs.filter(r => rowQtyNum(r) === null).length;
  const estimatesPending = needs.length - needsValue;  // have a number, just unconfirmed
  const pct = total ? Math.round((verified / total) * 100) : 100;
  const done = needs.length === 0;

  // Rows to show: all, or only unproven (sorted by impact — biggest numbers first).
  let pairs = takeoffRows.map((r, i) => ({ r, i }));
  if (wsFocusNeedsReview) {
    pairs = pairs.filter(p => rowNeedsVerification(p.r))
                 .sort((a, b) => (rowQtyNum(b.r) ?? -1) - (rowQtyNum(a.r) ?? -1));
  }

  container.innerHTML = `
    <div class="worksheet">
      <div class="ws-banner ${done ? 'ws-done' : ''}">
        <div class="ws-progress-text">
          <strong>${verified} / ${total} line items verified</strong>
          <span>${done ? '✓ Takeoff is 100% verified — every line is exact or human-confirmed'
                       : `${needs.length} still need review${needsValue ? ` · ${needsValue} need a value entered` : ''}`}</span>
        </div>
        <div class="ws-progress-bar"><div class="ws-progress-fill" style="width:${pct}%"></div></div>
        <span class="ws-progress-pct">${pct}%</span>
      </div>
      <div class="ws-toolbar">
        <label class="ws-toggle">
          <input type="checkbox" class="ws-focus-toggle" ${wsFocusNeedsReview ? 'checked' : ''}>
          Show only lines that need verification${needs.length ? ` (${needs.length})` : ''}
        </label>
        <div class="ws-toolbar-actions">
          ${estimatesPending ? `<button type="button" class="ws-confirm-all">Confirm ${estimatesPending} remaining estimate${estimatesPending > 1 ? 's' : ''} → 100%</button>` : ''}
          ${verified > 0 ? `<button type="button" class="ws-reset-all" title="Remove all your manual confirmations and restore the original auto values">Reset my edits</button>` : ''}
        </div>
      </div>
      <p class="ws-help">Click a quantity to edit it, or press <strong>Verify</strong> to confirm the value. <strong>Confirm remaining</strong> accepts every estimated line at once. Verified lines are exact and locked. Use the <strong>sheet link</strong> to trace a number back to its drawing, or <strong>Scale &amp; Verify</strong> to measure areas/lengths.</p>
      ${wsFocusNeedsReview && pairs.length === 0
        ? `<p class="ws-empty">✓ Nothing left to verify — this takeoff is 100% confirmed.</p>`
        : `
      <div class="ws-table-wrap">
      <table class="ws-table data-table">
        <thead><tr>
          <th>Status</th><th>Item</th><th>Quantity</th><th>Unit</th>
          <th>Source</th><th>Sheet</th><th>Action</th>
        </tr></thead>
        <tbody>
          ${pairs.map(({ r, i }) => {
            const st = rowStatus(r);
            const qty = (r.quantity_fmt ?? r.quantity ?? '—');
            const noVal = rowQtyNum(r) === null;
            return `
            <tr class="ws-row ws-${st.cls}" data-idx="${i}" data-item="${escapeHtml(r.item)}">
              <td><span class="ws-badge ws-badge-${st.cls}" title="${st.label}">${st.icon} ${st.label}</span></td>
              <td class="ws-item">${escapeHtml(r.item)}</td>
              <td class="ws-qty ${noVal ? 'ws-qty-empty' : ''}" data-idx="${i}" title="Click to edit">${noVal ? 'enter value' : escapeHtml(String(qty))}</td>
              <td>${escapeHtml(r.unit || '')}</td>
              <td class="ws-src">${escapeHtml(r.source || 'vision')}</td>
              <td>${renderSourceLinks((r.source_sheets || []).join(', '))}</td>
              <td class="ws-actions">
                <button type="button" class="ws-verify-btn" data-idx="${i}" ${noVal ? 'disabled title="Enter a value first"' : ''}>${st.cls === 'verified' ? 'Unverify' : 'Verify ✓'}</button>
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
      </div>`}
    </div>`;

  bindWorksheetEvents(container);
}

function bindWorksheetEvents(container) {
  // Inline-edit a quantity
  container.querySelectorAll('.ws-qty').forEach(cell => {
    cell.addEventListener('click', () => startEditQty(container, cell));
  });
  // Verify / unverify
  container.querySelectorAll('.ws-verify-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const r = takeoffRows[Number(btn.dataset.idx)];
      const verified = rowStatus(r).cls === 'verified';
      postVerify(container, { item: r.item, verified: !verified,
                              clear: verified });
    });
  });
  // Source-sheet chips → open the sheet image (with a Verify-scale shortcut).
  container.querySelectorAll('.source-sheet-link').forEach(el => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      openSheetLightbox(el.dataset.sheet || '');
    });
  });
  // Focus toggle: show only lines that still need verification.
  const focusToggle = container.querySelector('.ws-focus-toggle');
  if (focusToggle) {
    focusToggle.addEventListener('change', () => {
      wsFocusNeedsReview = focusToggle.checked;
      renderTakeoffWorksheet(container);
    });
  }
  // Confirm-all: accept every remaining estimate in one click → 100%.
  const confirmAll = container.querySelector('.ws-confirm-all');
  if (confirmAll) {
    confirmAll.addEventListener('click', () => {
      confirmAll.disabled = true;
      confirmAll.textContent = 'Confirming…';
      postVerifyBatch(container, { accept_all_estimates: true });
    });
  }
  // Reset: drop all manual confirmations, restore original auto values.
  const resetAll = container.querySelector('.ws-reset-all');
  if (resetAll) {
    resetAll.addEventListener('click', () => {
      if (!confirm('Remove all your manual confirmations and restore the original auto-calculated values?')) return;
      postVerifyBatch(container, { clear_all: true });
    });
  }
}

// Build the sheet-image URL from a stored source-sheet path. Stored paths look
// like "output/screenshots/<run>/page_0005.png"; the endpoint serves paths
// relative to OUTPUT_DIR, so we slice from "screenshots/".
function sheetImageUrl(fullPath) {
  let rel = String(fullPath || '').replace(/\\/g, '/');
  const idx = rel.indexOf('screenshots/');
  if (idx >= 0) rel = rel.slice(idx);
  else if (rel.startsWith('output/')) rel = rel.slice('output/'.length);
  const enc = rel.split('/').map(encodeURIComponent).join('/');
  return `/api/reports/${encodeURIComponent(currentRun)}/sheet-image/${enc}`;
}

function removeSheetLightbox() {
  const ex = document.getElementById('sheetLightbox');
  if (ex) ex.remove();
  document.removeEventListener('keydown', onSheetLightboxKey);
}

function onSheetLightboxKey(e) {
  if (e.key === 'Escape') removeSheetLightbox();
}

// Show a sheet image in a lightbox so the user can trace a line back to the
// drawing it came from, with a shortcut into Scale & Verify for that sheet.
async function openSheetLightbox(sheetToken) {
  if (!sheetToken) return;
  await ensureSheetImageMap();
  const ctx = resolveSheetContext(sheetToken);
  if (!ctx) return;

  if (!ctx.imageRel) {
    pendingScaleFocus = ctx.focusSheet || ctx.sheet;
    switchTab('scale');
    return;
  }

  const url = sheetImageUrl(ctx.imageRel);
  const base = String(ctx.sheet).split('/').pop();
  removeSheetLightbox();
  const ov = document.createElement('div');
  ov.className = 'sheet-lightbox';
  ov.id = 'sheetLightbox';
  ov.innerHTML = `
    <div class="sheet-lightbox-panel">
      <div class="sheet-lightbox-head">
        <strong title="${escapeHtml(ctx.sheet)}">${escapeHtml(base)}</strong>
        <div class="sheet-lightbox-actions">
          <a href="${url}" target="_blank" rel="noopener" class="sheet-lightbox-open">Open full size ↗</a>
          <button type="button" class="sheet-lightbox-verify">Verify scale →</button>
          <button type="button" class="sheet-lightbox-close" aria-label="Close">✕</button>
        </div>
      </div>
      <div class="sheet-lightbox-body"><img src="${url}" alt="${escapeHtml(base)}"></div>
    </div>`;
  (activeWorkspace || document.body).appendChild(ov);

  const img = ov.querySelector('.sheet-lightbox-body img');
  img.addEventListener('error', () => {
    ov.querySelector('.sheet-lightbox-body').innerHTML =
      '<p class="sheet-lightbox-missing">Sheet image not available for this run.</p>';
  });
  ov.addEventListener('click', (e) => { if (e.target === ov) removeSheetLightbox(); });
  ov.querySelector('.sheet-lightbox-close').addEventListener('click', removeSheetLightbox);
  ov.querySelector('.sheet-lightbox-verify').addEventListener('click', () => {
    pendingScaleFocus = ctx.focusSheet || ctx.sheet;
    removeSheetLightbox();
    switchTab('scale');
  });
  document.addEventListener('keydown', onSheetLightboxKey);
}

function startEditQty(container, cell) {
  if (cell.querySelector('input')) return;
  const idx = Number(cell.dataset.idx);
  const r = takeoffRows[idx];
  const cur = (r.quantity != null && r.quantity !== '—') ? r.quantity : '';
  cell.innerHTML = `<input type="number" step="any" class="ws-qty-input" value="${cur}">`;
  const inp = cell.querySelector('input');
  inp.focus();
  const commit = () => {
    const val = parseFloat(inp.value);
    if (Number.isFinite(val)) {
      postVerify(container, { item: r.item, quantity: val, unit: r.unit, verified: true });
    } else {
      renderTakeoffWorksheet(container);
    }
  };
  inp.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') commit();
    if (e.key === 'Escape') renderTakeoffWorksheet(container);
  });
  inp.addEventListener('blur', commit);
}

async function postVerify(container, body) {
  try {
    const resp = await fetch(`/api/reports/${encodeURIComponent(currentRun)}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      credentials: 'same-origin',
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    takeoffRows = data.takeoff_summary || takeoffRows;
    renderTakeoffWorksheet(container);
  } catch (err) {
    console.error('verify failed', err);
  }
}

// Batch verification — the fast path to 100% (confirm-all / reset).
async function postVerifyBatch(container, body) {
  try {
    const resp = await fetch(`/api/reports/${encodeURIComponent(currentRun)}/verify-batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      credentials: 'same-origin',
      body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    takeoffRows = data.takeoff_summary || takeoffRows;
    renderTakeoffWorksheet(container);
    if (Array.isArray(data.skipped_no_value) && data.skipped_no_value.length) {
      const n = data.skipped_no_value.length;
      alert(`${n} line${n > 1 ? 's' : ''} still need a value entered before they can be confirmed:\n\n` +
            data.skipped_no_value.slice(0, 12).join('\n') +
            (n > 12 ? `\n…and ${n - 12} more` : ''));
    }
  } catch (err) {
    console.error('batch verify failed', err);
    renderTakeoffWorksheet(container);
  }
}

// Render a comma-separated source_sheets value as clickable chips.
function renderSourceLinks(value) {
  const raw = String(value ?? '').trim();
  if (!raw) return '';
  return raw.split(',').map(tok => {
    const name = tok.trim();
    if (!name) return '';
    const base = name.split('/').pop();
    return `<a href="#" class="source-sheet-link" data-sheet="${escapeHtml(name)}" title="View sheet ${escapeHtml(base)}">${escapeHtml(base)}</a>`;
  }).filter(Boolean).join(', ');
}

// ─── Scale & Verify module ──────────────────────────────────────────────────
// Vector geometry is captured once as scale-independent point measures. The
// user verifies/corrects the drawing scale per sheet; quantities recompute
// deterministically (client-side instant + server-persisted). This is the path
// to 100% on measured SF/LF — scale is the single human-verified input.

const PT_PER_IN = 72;

function recomputeClient(raw, fpi) {
  if (!raw || !fpi || fpi <= 0) {
    return { footprint_sf: null, total_linework_lf: null, long_run_lf: null };
  }
  const fpp = fpi / PT_PER_IN;
  const r1 = (n) => Math.round((n + Number.EPSILON) * 10) / 10;
  return {
    footprint_sf: r1((raw.footprint_pt2 || 0) * fpp * fpp),
    total_linework_lf: r1((raw.total_linework_pt || 0) * fpp),
    long_run_lf: r1((raw.long_run_pt || 0) * fpp),
    width_ft: r1((raw.width_pt || 0) * fpp),
    height_ft: r1((raw.height_pt || 0) * fpp),
  };
}

function fmtQty(v) {
  if (v === null || v === undefined || v === '') return '—';
  return Number(v).toLocaleString('en-US', { maximumFractionDigits: 1 });
}

function confBadge(conf) {
  const c = String(conf || 'none').toLowerCase();
  return `<span class="scale-conf scale-conf-${c}">${escapeHtml(c)}</span>`;
}

async function loadScaleTab(container) {
  const response = await fetch(`/api/reports/${encodeURIComponent(currentRun)}/scale`, { credentials: 'same-origin' });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  scaleCalibration = data;
  const sheets = data.sheets || [];
  for (const s of sheets) {
    if (s.sheet) {
      sheetImageMap[normalizeSheetKey(s.sheet)] = { sheet: s.sheet, image: s.image || '' };
    }
  }

  if (!sheets.length) {
    container.innerHTML = `
      <div class="scale-empty">
        <h3>No scale-dependent sheets</h3>
        <p>This run produced no vector floor / site / roof plan geometry, so there
        are no measured quantities to recalibrate. Counted (EA) and schedule
        quantities are not scale-dependent.</p>
      </div>`;
    return;
  }

  const optionsHtml = COMMON_SCALES.map(s =>
    `<option value="${s.fpi}">${escapeHtml(s.label)}  (1" = ${s.fpi}')</option>`).join('');

  container.innerHTML = `
    <div class="scale-module">
      <div class="scale-intro">
        <h3>Verify drawing scale → exact measured quantities</h3>
        <p>We detect each sheet's scale automatically, but printed scales can be
        wrong or multi-scale. Confirm or correct the scale below and the measured
        areas/lengths recompute instantly and exactly. Open each sheet to read its
        scale bar or a known dimension.</p>
      </div>
      <div class="scale-table-wrap">
      <table class="scale-table data-table">
        <thead><tr>
          <th>Sheet</th><th>Detected scale</th><th>Confidence</th>
          <th>Scale (1" = ? ft)</th><th>Preset</th>
          <th>Footprint (SF)</th><th>Linework (LF)</th><th>Long runs (LF)</th>
          <th>Actions</th>
        </tr></thead>
        <tbody>
          ${sheets.map((s, i) => {
            const fpi = s.feet_per_inch ?? '';
            const m = s.measured || {};
            const userVerified = s.scale_source === 'user_verified';
            const autoVerified = !userVerified && s.auto_verified;
            const verified = userVerified || autoVerified;
            const needsScale = s.needs_scale_verify && !verified;
            const vpCount = (s.viewports || []).length;
            const canMeasure = s.image && s.page_width_pt && s.page_height_pt;
            const imgLink = s.image
              ? `<a class="scale-view-link" target="_blank" rel="noopener" href="/api/reports/${encodeURIComponent(currentRun)}/sheet-image/${encodeURI(s.image)}">View</a>`
              : '<span class="scale-view-link disabled" title="Sheet image unavailable">No image</span>';
            const measureBtn = canMeasure
              ? `<button type="button" class="scale-measure-btn" data-idx="${i}">Measure items →</button>`
              : '';
            return `
            <tr class="scale-row${verified ? ' scale-verified' : ''}${needsScale ? ' scale-needs-verify' : ''}" data-idx="${i}" data-sheet="${escapeHtml(s.sheet)}">
              <td class="scale-sheet-name">${escapeHtml(String(s.sheet).split('/').pop())}</td>
              <td class="scale-detected">${escapeHtml(s.scale_text || '—')}${vpCount > 1 ? ` <span class="scale-vp-tag" title="${vpCount} viewports measured per-scale">${vpCount} viewports</span>` : ''}</td>
              <td>${confBadge(s.scale_confidence)}${userVerified ? ' <span class="scale-verified-tag">verified</span>' : (autoVerified ? ' <span class="scale-auto-tag" title="Read cleanly from the sheet and snapped to a standard scale — accepted automatically">⚡ Auto</span>' : '')}</td>
              <td><input type="number" class="scale-fpi-input" min="0.1" step="0.1" value="${fpi}" data-idx="${i}" placeholder="?"></td>
              <td>
                <select class="scale-preset" data-idx="${i}">
                  <option value="">— pick —</option>${optionsHtml}
                </select>
              </td>
              <td class="scale-out scale-out-footprint">${fmtQty(m.footprint_sf)}</td>
              <td class="scale-out scale-out-linework">${fmtQty(m.total_linework_lf)}</td>
              <td class="scale-out scale-out-long">${fmtQty(m.long_run_lf)}</td>
              <td class="scale-actions">${imgLink} ${measureBtn}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
      </div>
      <div class="scale-footer">
        <span class="scale-save-status" id="scaleSaveStatus"></span>
        <button type="button" class="scale-save-btn" id="scaleSaveBtn">Save verified scales</button>
      </div>
    </div>`;

  bindScaleEvents(container, sheets);

  if (pendingScaleFocus) {
    focusScaleSheet(container, pendingScaleFocus);
    pendingScaleFocus = '';
  }
}

function focusScaleSheet(container, sheetToken) {
  const key = normalizeSheetKey(sheetToken);
  const rows = Array.from(container.querySelectorAll('.scale-row'));
  let match = rows.find(r => normalizeSheetKey(r.dataset.sheet) === key);
  if (!match) {
    match = rows.find(r => {
      const n = normalizeSheetKey(r.dataset.sheet);
      return n.includes(key) || key.includes(n);
    });
  }
  if (match) {
    match.scrollIntoView({ behavior: 'smooth', block: 'center' });
    match.classList.add('scale-focus');
    setTimeout(() => match.classList.remove('scale-focus'), 2800);
    const inp = match.querySelector('.scale-fpi-input');
    if (inp) setTimeout(() => inp.focus(), 350);
    return;
  }
  const intro = container.querySelector('.scale-intro');
  if (intro && !intro.querySelector('.scale-focus-miss')) {
    const warn = document.createElement('p');
    warn.className = 'scale-focus-miss';
    const label = String(sheetToken).split('/').pop();
    warn.textContent = `Sheet "${label}" is not in the scale table — re-run this project with the latest app to capture PDF geometry, or pick the matching row below.`;
    intro.appendChild(warn);
    setTimeout(() => warn.remove(), 8000);
  }
}

function bindScaleEvents(container, sheets) {
  const applyRow = (idx, fpi) => {
    const sheet = sheets[idx];
    if (!sheet) return;
    sheet.feet_per_inch = fpi;
    const out = recomputeClient(sheet.raw, fpi);
    sheet.measured = out;
    const row = container.querySelector(`.scale-row[data-idx="${idx}"]`);
    if (!row) return;
    row.querySelector('.scale-out-footprint').textContent = fmtQty(out.footprint_sf);
    row.querySelector('.scale-out-linework').textContent = fmtQty(out.total_linework_lf);
    row.querySelector('.scale-out-long').textContent = fmtQty(out.long_run_lf);
    row.classList.add('scale-dirty');
    markScaleStatus('Unsaved changes', 'dirty');
  };

  container.querySelectorAll('.scale-fpi-input').forEach(inp => {
    inp.addEventListener('input', () => {
      const idx = Number(inp.dataset.idx);
      const fpi = parseFloat(inp.value);
      if (fpi > 0) applyRow(idx, fpi);
    });
  });

  container.querySelectorAll('.scale-preset').forEach(sel => {
    sel.addEventListener('change', () => {
      const idx = Number(sel.dataset.idx);
      const fpi = parseFloat(sel.value);
      if (fpi > 0) {
        const inp = container.querySelector(`.scale-fpi-input[data-idx="${idx}"]`);
        if (inp) inp.value = fpi;
        applyRow(idx, fpi);
      }
    });
  });

  const saveBtn = container.querySelector('#scaleSaveBtn');
  if (saveBtn) saveBtn.addEventListener('click', () => saveScaleOverrides(container, sheets));

  container.querySelectorAll('.scale-measure-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = Number(btn.dataset.idx);
      openMeasureEditor(sheets[idx]);
    });
  });
}

function markScaleStatus(text, cls) {
  const el = document.getElementById('scaleSaveStatus');
  if (!el) return;
  el.textContent = text;
  el.className = `scale-save-status ${cls || ''}`;
}

async function saveScaleOverrides(container, sheets) {
  const overrides = {};
  sheets.forEach(s => {
    if (s.feet_per_inch > 0) overrides[s.sheet] = s.feet_per_inch;
  });
  markScaleStatus('Saving…', 'saving');
  try {
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const resp = await fetch(`/api/reports/${encodeURIComponent(currentRun)}/scale`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfMeta ? csrfMeta.content : '',
      },
      credentials: 'same-origin',
      body: JSON.stringify({ overrides }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    scaleCalibration = data;
    container.querySelectorAll('.scale-row').forEach(r => r.classList.remove('scale-dirty'));
    markScaleStatus('Saved — quantities recomputed exactly', 'saved');
  } catch (err) {
    markScaleStatus(`Save failed: ${err.message}`, 'error');
  }
}

// ─── Interactive measurement editor ─────────────────────────────────────────
// Draw scale-bound geometry on the real sheet image. Geometry is stored in PDF
// points (scale-independent); quantity = geometry × verified scale → exact.

let allMeasurements = [];   // measurements for the whole run
let editor = null;          // { sheet, tool, vertices, ppx, ppy }

// Client-side mirror of takeoff_measurements.py (kept exact / in sync).
function _polylineLenPt(pts) {
  let t = 0;
  for (let i = 1; i < pts.length; i++) {
    t += Math.hypot(pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1]);
  }
  return t;
}
function _polyAreaPt2(pts) {
  if (pts.length < 3) return 0;
  const r = pts[0][0] === pts[pts.length-1][0] && pts[0][1] === pts[pts.length-1][1]
    ? pts : [...pts, pts[0]];
  let s = 0;
  for (let i = 1; i < r.length; i++) s += r[i-1][0]*r[i][1] - r[i][0]*r[i-1][1];
  return Math.abs(s) / 2;
}
function _perimeterPt(pts) {
  if (pts.length < 2) return 0;
  const r = pts[0][0] === pts[pts.length-1][0] && pts[0][1] === pts[pts.length-1][1]
    ? pts : [...pts, pts[0]];
  return _polylineLenPt(r);
}
function measureQty(m) {
  const fpi = m.feet_per_inch;
  if (m.measure_type === 'count') return (m.count != null ? m.count : (m.points_pt||[]).length);
  if (!fpi || fpi <= 0) return null;
  const fpp = fpi / PT_PER_IN;
  const pts = m.points_pt || [];
  if (m.measure_type === 'length') return round2(_polylineLenPt(pts) * fpp);
  if (m.measure_type === 'area')   return round2(_polyAreaPt2(pts) * fpp * fpp);
  if (m.measure_type === 'wall_area') {
    const run = m.closed ? _perimeterPt(pts) : _polylineLenPt(pts);
    return round2(run * fpp * (Number(m.height_ft) || 0));
  }
  return null;
}
function round2(n) { return Math.round((n + Number.EPSILON) * 100) / 100; }

async function openMeasureEditor(sheet) {
  try {
    const resp = await fetch(`/api/reports/${encodeURIComponent(currentRun)}/measurements`, { credentials: 'same-origin' });
    const data = await resp.json();
    allMeasurements = (data.measurements || []);
  } catch { allMeasurements = []; }
  editor = { sheet, tool: 'length', vertices: [], ppx: 0, ppy: 0 };
  renderMeasureEditor();
  exposeMeasureTestHook();
}

function removeMeasureOverlayDom() {
  const el = document.getElementById('measureOverlay');
  if (el) el.remove();
}

function closeMeasureEditor() {
  removeMeasureOverlayDom();
  editor = null;
}

function renderMeasureEditor() {
  const s = editor.sheet;
  removeMeasureOverlayDom();
  const imgUrl = `/api/reports/${encodeURIComponent(currentRun)}/sheet-image/${encodeURI(s.image)}`;
  const overlay = document.createElement('div');
  overlay.className = 'measure-overlay';
  overlay.id = 'measureOverlay';
  overlay.innerHTML = `
    <div class="measure-panel">
      <div class="measure-head">
        <div>
          <strong>Measure — ${escapeHtml(String(s.sheet).split('/').pop())}</strong>
          <span class="measure-scale-readout" id="measureScale">Scale: 1" = ${s.feet_per_inch || '?'} ft</span>
        </div>
        <button type="button" class="measure-close" id="measureClose">✕ Close</button>
      </div>
      <div class="measure-toolbar">
        <div class="measure-tools">
          ${['calibrate','length','area','wall_area','count'].map(t =>
            `<button type="button" class="measure-tool${t==='length'?' active':''}" data-tool="${t}">${({calibrate:'Calibrate scale',length:'Length (LF)',area:'Area (SF)',wall_area:'Wall (SF)',count:'Count (EA)'})[t]}</button>`).join('')}
        </div>
        <div class="measure-bind">
          <input type="text" id="measureItem" placeholder="Bind to item (e.g. Gas Piping)">
          <input type="text" id="measureUnit" placeholder="Unit" style="width:4.5rem">
          <input type="number" id="measureHeight" placeholder="Ht ft" style="width:5rem" title="Wall height (wall_area)">
          <button type="button" id="measureUndo">Undo pt</button>
          <button type="button" id="measureFinish" class="measure-primary">Add measurement</button>
        </div>
      </div>
      <p class="measure-steps"><strong>How to measure:</strong> 1) Pick a tool · 2) Type the item name (and unit) · 3) Click points on the drawing to trace it · 4) <em>Add measurement</em> · 5) <em>Save &amp; recompute</em>. For accuracy, first use <em>Calibrate scale</em>: click two points of a known distance.</p>
      <div class="measure-body">
        <div class="measure-canvas-wrap" id="measureCanvasWrap">
          <img id="measureImg" src="${imgUrl}" alt="sheet">
          <svg id="measureSvg" class="measure-svg"></svg>
          <div class="measure-live" id="measureLive"></div>
        </div>
        <aside class="measure-list" id="measureList"></aside>
      </div>
      <div class="measure-foot">
        <span class="measure-save-status" id="measureSaveStatus"></span>
        <button type="button" id="measureSaveAll" class="measure-primary">Save &amp; recompute summary</button>
      </div>
    </div>`;
  activeWorkspace.appendChild(overlay);

  const img = overlay.querySelector('#measureImg');
  img.addEventListener('load', () => {
    const rect = img.getBoundingClientRect();
    editor.ppx = (s.page_width_pt || rect.width) / rect.width;   // pt per displayed px
    editor.ppy = (s.page_height_pt || rect.height) / rect.height;
    const svg = overlay.querySelector('#measureSvg');
    svg.setAttribute('width', rect.width);
    svg.setAttribute('height', rect.height);
    redrawMeasure();
  });

  bindMeasureEvents(overlay);
  renderMeasureList();
}

function bindMeasureEvents(overlay) {
  overlay.querySelector('#measureClose').addEventListener('click', closeMeasureEditor);
  overlay.querySelectorAll('.measure-tool').forEach(b => {
    b.addEventListener('click', () => {
      editor.tool = b.dataset.tool;
      editor.vertices = [];
      overlay.querySelectorAll('.measure-tool').forEach(x => x.classList.toggle('active', x === b));
      redrawMeasure();
    });
  });
  overlay.querySelector('#measureUndo').addEventListener('click', () => {
    editor.vertices.pop(); redrawMeasure();
  });
  overlay.querySelector('#measureFinish').addEventListener('click', finishMeasureShape);
  overlay.querySelector('#measureSaveAll').addEventListener('click', saveAllMeasurements);

  const svg = overlay.querySelector('#measureSvg');
  svg.addEventListener('click', (e) => {
    const rect = svg.getBoundingClientRect();
    const px = e.clientX - rect.left, py = e.clientY - rect.top;
    addVertexPt(px * editor.ppx, py * editor.ppy, px, py);
  });
}

// Add a vertex in PDF-point space (px coords optional, for display).
function addVertexPt(ptx, pty, dispX, dispY) {
  editor.vertices.push({ pt: [ptx, pty], px: [dispX ?? ptx / editor.ppx, dispY ?? pty / editor.ppy] });
  if (editor.tool === 'count') {
    // each click is its own marker — finalize immediately into a pending list
  }
  redrawMeasure();
}

function currentShapePts() { return editor.vertices.map(v => v.pt); }

function redrawMeasure() {
  const overlay = document.getElementById('measureOverlay');
  if (!overlay) return;
  const svg = overlay.querySelector('#measureSvg');
  if (!svg) return;
  const v = editor.vertices;
  const isArea = editor.tool === 'area';
  let shapes = '';
  if (v.length) {
    const ptsAttr = v.map(p => `${p.px[0]},${p.px[1]}`).join(' ');
    if (isArea && v.length >= 2) {
      shapes += `<polygon points="${ptsAttr}" fill="rgba(79,140,255,0.18)" stroke="#4f8cff" stroke-width="2"/>`;
    } else if (v.length >= 2) {
      shapes += `<polyline points="${ptsAttr}" fill="none" stroke="#4f8cff" stroke-width="2"/>`;
    }
    shapes += v.map(p => `<circle cx="${p.px[0]}" cy="${p.px[1]}" r="4" fill="#4f8cff"/>`).join('');
  }
  svg.innerHTML = shapes;

  // live quantity preview
  const live = overlay.querySelector('#measureLive');
  if (live) {
    const m = pendingMeasurement();
    const q = measureQty(m);
    const label = editor.tool === 'calibrate'
      ? `Calibrate: click 2 points (${v.length}/2)`
      : `${editor.tool} • pts: ${v.length} • qty: ${q == null ? '— (set scale)' : q.toLocaleString()}`;
    live.textContent = label;
  }
}

function pendingMeasurement() {
  const overlay = document.getElementById('measureOverlay');
  const item = overlay?.querySelector('#measureItem')?.value || '';
  const unit = overlay?.querySelector('#measureUnit')?.value || '';
  const height = overlay?.querySelector('#measureHeight')?.value || '';
  return {
    item, unit, measure_type: editor.tool, sheet: editor.sheet.sheet,
    points_pt: currentShapePts(), feet_per_inch: editor.sheet.feet_per_inch,
    height_ft: height ? Number(height) : null,
    closed: editor.tool === 'area', verified: true,
  };
}

async function finishMeasureShape() {
  const overlay = document.getElementById('measureOverlay');
  if (editor.tool === 'calibrate') {
    if (editor.vertices.length < 2) { setMeasureStatus('Click 2 points to calibrate', 'dirty'); return; }
    const realFeet = parseFloat(prompt('Real-world distance between the two points (feet):'));
    if (!(realFeet > 0)) return;
    const p1 = editor.vertices[0].pt, p2 = editor.vertices[1].pt;
    try {
      const resp = await fetch(`/api/reports/${encodeURIComponent(currentRun)}/calibrate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
        credentials: 'same-origin',
        body: JSON.stringify({ p1, p2, real_feet: realFeet }),
      });
      const data = await resp.json();
      if (data.feet_per_inch) {
        editor.sheet.feet_per_inch = data.feet_per_inch;
        overlay.querySelector('#measureScale').textContent = `Scale: 1" = ${data.feet_per_inch} ft (calibrated)`;
        // recompute existing measurements on this sheet with the new scale
        allMeasurements.forEach(m => {
          if (m.sheet === editor.sheet.sheet) { m.feet_per_inch = data.feet_per_inch; m.quantity = measureQty(m); }
        });
        editor.vertices = [];
        redrawMeasure(); renderMeasureList();
        setMeasureStatus(`Calibrated: 1" = ${data.feet_per_inch} ft`, 'saved');
      }
    } catch (err) { setMeasureStatus('Calibrate failed', 'error'); }
    return;
  }

  const m = pendingMeasurement();
  if (!m.item.trim()) { setMeasureStatus('Enter an item name to bind', 'dirty'); return; }
  if (m.measure_type !== 'count' && (!m.feet_per_inch || m.feet_per_inch <= 0)) {
    setMeasureStatus('Set/calibrate scale first', 'dirty'); return;
  }
  if (m.measure_type === 'count') {
    m.count = m.points_pt.length;
  } else if (m.points_pt.length < 2) {
    setMeasureStatus('Need at least 2 points', 'dirty'); return;
  }
  m.id = 'm' + Math.random().toString(36).slice(2, 10);
  m.quantity = measureQty(m);
  if (!m.unit) m.unit = { length: 'LF', area: 'SF', wall_area: 'SF', count: 'EA' }[m.measure_type];
  allMeasurements.push(m);
  editor.vertices = [];
  redrawMeasure(); renderMeasureList();
  setMeasureStatus(`Added ${m.item} = ${m.quantity} ${m.unit}`, 'saved');
}

function renderMeasureList() {
  const overlay = document.getElementById('measureOverlay');
  if (!overlay) return;
  const list = overlay.querySelector('#measureList');
  const mine = allMeasurements.filter(m => m.sheet === editor.sheet.sheet);
  list.innerHTML = `
    <h4>Measurements on this sheet</h4>
    ${mine.length ? mine.map(m => `
      <div class="measure-item">
        <span class="measure-item-name">${escapeHtml(m.item)}</span>
        <span class="measure-item-qty">${(m.quantity ?? measureQty(m) ?? '—').toLocaleString?.() ?? m.quantity} ${escapeHtml(m.unit||'')}</span>
        <button type="button" class="measure-item-del" data-id="${m.id}">✕</button>
      </div>`).join('') : '<p class="measure-empty">None yet. Pick a tool and click on the sheet.</p>'}`;
  list.querySelectorAll('.measure-item-del').forEach(b => {
    b.addEventListener('click', () => {
      allMeasurements = allMeasurements.filter(m => m.id !== b.dataset.id);
      renderMeasureList();
    });
  });
}

function setMeasureStatus(text, cls) {
  const el = document.getElementById('measureSaveStatus');
  if (el) { el.textContent = text; el.className = `measure-save-status ${cls||''}`; }
}

function csrfToken() {
  const m = document.querySelector('meta[name="csrf-token"]');
  return m ? m.content : '';
}

async function saveAllMeasurements() {
  setMeasureStatus('Saving…', 'saving');
  try {
    const resp = await fetch(`/api/reports/${encodeURIComponent(currentRun)}/measurements`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      credentials: 'same-origin',
      body: JSON.stringify({ measurements: allMeasurements }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    allMeasurements = data.measurements || allMeasurements;
    renderMeasureList();
    setMeasureStatus('Saved — takeoff summary recomputed exactly', 'saved');
  } catch (err) {
    setMeasureStatus(`Save failed: ${err.message}`, 'error');
  }
}

// Testing/automation hook — drives the same code paths deterministically.
function exposeMeasureTestHook() {
  window.__scaleMeasure = {
    setTool: (t) => { editor.tool = t; editor.vertices = []; },
    setScale: (fpi) => { editor.sheet.feet_per_inch = Number(fpi); },
    addPt: (ptx, pty) => addVertexPt(ptx, pty),
    setBind: (item, unit, height) => {
      const o = document.getElementById('measureOverlay');
      if (o) { o.querySelector('#measureItem').value = item || '';
        o.querySelector('#measureUnit').value = unit || '';
        o.querySelector('#measureHeight').value = height || ''; }
    },
    finish: () => finishMeasureShape(),
    saveAll: () => saveAllMeasurements(),
    list: () => allMeasurements.filter(m => m.sheet === editor.sheet.sheet),
  };
}

async function loadSummaryTab(container) {
  const response = await fetch(`/api/reports/${encodeURIComponent(currentRun)}/preview/summary.txt`, { credentials: 'same-origin' });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  if (data.error) throw new Error(data.error);
  container.innerHTML = `<div class="summary-view"><pre class="summary-pre">${escapeHtml(data.content || '')}</pre></div>`;
}

async function loadCalculationsTab(container) {
  const response = await fetch(`/api/reports/${encodeURIComponent(currentRun)}/preview/calculations.csv`, { credentials: 'same-origin' });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  if (data.error) throw new Error(data.error);

  let html = '';
  if (data.capped) {
    html += `<div class="cap-banner">Showing ${(data.rows || []).length} of ${data.total || 'many'} rows. <a href="/api/reports/${encodeURIComponent(currentRun)}/calculations.csv" class="download-full-link">Download full CSV</a></div>`;
  }
  html += renderDataTable(data.headers || [], data.rows || []);
  container.innerHTML = html;
}

async function loadRawTab(container) {
  const response = await fetch(`/api/reports/${encodeURIComponent(currentRun)}/preview/raw_items.csv`, { credentials: 'same-origin' });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  if (data.error) throw new Error(data.error);
  container.innerHTML = renderDataTable(data.headers || [], data.rows || []);
}

async function loadJsonTab(container) {
  const response = await fetch(`/api/reports/${encodeURIComponent(currentRun)}/preview/takeoff.json`, { credentials: 'same-origin' });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  if (data.error) throw new Error(data.error);
  const json = data.data ?? data;
  container.innerHTML = `
    <div class="json-search">
      <input type="text" placeholder="Search JSON..." class="json-search-input" />
    </div>
    <pre class="json-view">${escapeHtml(JSON.stringify(json, null, 2))}</pre>
  `;
}

function renderDataTable(headers, rows) {
  const bodyRows = rows.map(row => {
    const cells = Array.isArray(row)
      ? row.map(cell => `<td>${escapeHtml(cell ?? '')}</td>`).join('')
      : headers.map(h => `<td>${escapeHtml(row[h] ?? '')}</td>`).join('');
    return `<tr>${cells}</tr>`;
  }).join('');
  return `
    <div class="data-table-container">
      <table class="data-table">
        <thead><tr>${headers.map(h => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>
  `;
}

function handleWorkspaceKeyboard(e) {
  if (e.key === 'Escape') {
    e.preventDefault();
    closeReportWorkspace();
  }
  
  if (e.key >= '1' && e.key <= '9') {
    e.preventDefault();
    const tabIndex = parseInt(e.key) - 1;
    if (TAB_IDS[tabIndex]) switchTab(TAB_IDS[tabIndex]);
  }
}

function updateWorkspaceURL() {
  const url = new URL(window.location);
  url.searchParams.set('run', currentRun);
  url.searchParams.set('tab', currentTab);
  window.history.replaceState({}, '', url);
}

function exportReport(runFolder, type) {
  const fileMap = {
    summary: 'summary.txt',
    json: 'takeoff.json',
    calculations: 'calculations.csv',
    raw: 'raw_items.csv',
    takeoff: 'takeoff_summary.csv',
  };
  const filename = fileMap[type] || `${type}.csv`;
  const link = document.createElement('a');
  link.href = `/api/reports/${encodeURIComponent(runFolder)}/${encodeURIComponent(filename)}`;
  link.download = `${runFolder}_${filename}`;
  link.click();
}

function formatDate(timestamp) {
  if (!timestamp) return '';
  // Handle "20260526_172639" format from folder names
  if (typeof timestamp === 'string' && /^\d{8}_\d{6}$/.test(timestamp)) {
    const d = timestamp.slice(0, 8);
    const t = timestamp.slice(9);
    const iso = `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)}T${t.slice(0,2)}:${t.slice(2,4)}:${t.slice(4,6)}`;
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  // Unix timestamp (seconds or milliseconds)
  const ms = typeof timestamp === 'number' && timestamp < 1e12 ? timestamp * 1000 : timestamp;
  return new Date(ms).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderCachePill(report) {
  if (report.from_cache) {
    return '<span class="pill pill-success">Cached</span>';
  }
  return '';
}

// Global exposure
window.reportWorkspace = { openReportWorkspace, closeReportWorkspace, switchTab };
