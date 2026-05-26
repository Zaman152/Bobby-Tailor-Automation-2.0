/**
 * Bobby Tailor — Estimation Automation
 * Client-side application logic
 *
 * Layout: Master.md §8.2–8.7
 */

// ── State ──────────────────────────────────────────────────────────────────
let currentMode = 'all';
let selectedFile = null;
let pollInterval = null;
let projectsLoaded = false;
let allPlans = [];
let selectedProjectId = null;
let activeJobPollInterval = null;

// ── Navigation ─────────────────────────────────────────────────────────────
const PAGE_TITLES = {
  projects: 'StackCT Projects',
  pdf: 'Upload PDF',
  reports: 'Reports',
  settings: 'Settings'
};

function navigateTo(pageName) {
  // Hide all sections
  document.querySelectorAll('.page-section').forEach(s => s.classList.remove('active'));
  // Show target section
  const target = document.getElementById('page-' + pageName);
  if (target) target.classList.add('active');

  // Update nav active state
  document.querySelectorAll('.nav-item[data-page]').forEach(n => n.classList.remove('active'));
  const navItem = document.querySelector('.nav-item[data-page="' + pageName + '"]');
  if (navItem) navItem.classList.add('active');

  // Update page title
  const titleEl = document.getElementById('pageTitle');
  if (titleEl) titleEl.textContent = PAGE_TITLES[pageName] || pageName;

  // Trigger data loads on navigation
  if (pageName === 'reports') loadReports();
  if (pageName === 'projects' && !projectsLoaded) loadProjects();
}

// ── Mode ───────────────────────────────────────────────────────────────────
function setMode(mode) {
  currentMode = mode;
  document.getElementById('modeAll').classList.toggle('active', mode === 'all');
  document.getElementById('modeOne').classList.toggle('active', mode === 'specific');
  document.getElementById('projectDropdownField').style.display = mode === 'specific' ? 'block' : 'none';
  if (mode === 'specific' && !projectsLoaded) loadProjects();
}

// ── Projects Dropdown ──────────────────────────────────────────────────────
async function loadProjects(force = false) {
  const sel = document.getElementById('projectSelect');
  const status = document.getElementById('cacheStatus');
  const refreshBtn = document.getElementById('refreshBtn');

  sel.innerHTML = '<option>Loading…</option>';
  if (status) status.textContent = force ? '🔄 Fetching live…' : '⏳ Loading…';
  if (refreshBtn) refreshBtn.disabled = true;

  try {
    const url = force ? '/api/projects?refresh=1' : '/api/projects';
    const res = await fetch(url);
    const data = await res.json();

    if (data.error && !data.projects?.length) {
      sel.innerHTML = '<option>Error loading projects</option>';
      if (status) status.textContent = '⚠ Could not load';
      return;
    }

    sel.innerHTML = '<option value="">— Select a project —</option>';
    (data.projects || []).forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.name;
      opt.dataset.name = p.name;
      sel.appendChild(opt);
    });
    projectsLoaded = true;

    if (status) {
      const when = data.fetched_at ? new Date(data.fetched_at).toLocaleString() : '';
      const tag = data.from_cache ? '📦 Cached' + (data.stale ? ' (stale)' : '') : '✓ Live';
      status.textContent = tag + ' · ' + (data.projects?.length || 0) + ' projects · ' + when;
      status.style.color = data.stale ? '#f59e0b' : '#475569';
    }

    sel.onchange = () => {
      const opt = sel.options[sel.selectedIndex];
      document.getElementById('projectMeta').textContent =
        opt.value ? 'Project ID: ' + opt.value : '';
      selectedProjectId = opt.value ? parseInt(opt.value) : null;
      const previewBtn = document.getElementById('previewPlansBtn');
      if (previewBtn) {
        previewBtn.disabled = !selectedProjectId;
        previewBtn.style.opacity = selectedProjectId ? '1' : '0.5';
      }
      document.getElementById('planSelectionPanel').style.display = 'none';
      allPlans = [];
    };
  } catch (e) {
    sel.innerHTML = '<option>Could not load projects</option>';
    if (status) status.textContent = '⚠ Network error';
  } finally {
    if (refreshBtn) refreshBtn.disabled = false;
  }
}

async function refreshProjects() {
  projectsLoaded = false;
  await loadProjects(true);
}

// ── Run StackCT ────────────────────────────────────────────────────────────
async function runStackCT() {
  const btn = document.getElementById('runStackctBtn');
  let projectId = null, projectName = 'All Projects';

  if (currentMode === 'specific') {
    const sel = document.getElementById('projectSelect');
    if (!sel.value) { alert('Please select a project.'); return; }
    projectId = parseInt(sel.value);
    projectName = sel.options[sel.selectedIndex].dataset.name || 'Project';
  }

  btn.disabled = true;
  btn.textContent = '⏳ Starting…';

  try {
    const res = await fetch('/api/run/stackct', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: currentMode, project_id: projectId, project_name: projectName })
    });
    const data = await res.json();
    startPolling(data.job_id, projectName);
  } catch (e) {
    alert('Failed to start job: ' + e);
  } finally {
    btn.disabled = false;
    btn.textContent = '▶ Run All';
  }
}

// ── PDF File Handling ──────────────────────────────────────────────────────
function onFileSelected(input) {
  selectedFile = input.files[0];
  if (selectedFile) {
    document.getElementById('selectedFileName').textContent =
      '✓ ' + selectedFile.name + ' (' + (selectedFile.size / 1024 / 1024).toFixed(1) + ' MB)';
    if (!document.getElementById('pdfProjectName').value)
      document.getElementById('pdfProjectName').value = selectedFile.name.replace('.pdf', '');
    document.getElementById('runPdfBtn').disabled = false;
  }
}

// Drag & drop
const dz = document.getElementById('dropZone');
if (dz) {
  dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag-over'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('drag-over'));
  dz.addEventListener('drop', e => {
    e.preventDefault(); dz.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file && file.name.endsWith('.pdf')) {
      const dt = new DataTransfer(); dt.items.add(file);
      const inp = document.getElementById('fileInput');
      inp.files = dt.files;
      onFileSelected(inp);
    }
  });
}

async function runPDF() {
  if (!selectedFile) return;
  const btn = document.getElementById('runPdfBtn');
  const name = document.getElementById('pdfProjectName').value || selectedFile.name;
  btn.disabled = true;
  btn.textContent = '⏳ Uploading…';

  const form = new FormData();
  form.append('file', selectedFile);
  form.append('project_name', name);

  try {
    const res = await fetch('/api/run/pdf', { method: 'POST', body: form });
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    startPolling(data.job_id, name);
  } catch (e) {
    alert('Upload failed: ' + e);
  } finally {
    btn.disabled = false;
    btn.textContent = '▶ Analyze PDF';
  }
}

// ── Polling ────────────────────────────────────────────────────────────────
function startPolling(jobId, projectName) {
  if (pollInterval) clearInterval(pollInterval);
  const card = document.getElementById('progressCard');
  card.classList.add('visible');
  document.getElementById('jobInfo').textContent = 'Project: ' + projectName + '  ·  Job: ' + jobId;
  document.getElementById('logBox').innerHTML = '';

  pollInterval = setInterval(() => pollStatus(jobId), 2000);
  pollStatus(jobId);

  card.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function pollStatus(jobId) {
  try {
    const res = await fetch('/api/status/' + jobId);
    const job = await res.json();

    const badge = document.getElementById('statusBadge');
    badge.className = 'status-badge badge-' + job.status;
    const labels = { queued: '⏳ Queued', running: '⚙ Running', done: '✓ Done', error: '✕ Error' };
    badge.innerHTML = (job.status === 'running' ? '<span class="spinner"></span> ' : '') + (labels[job.status] || job.status);

    document.getElementById('progressFill').style.width = (job.progress || 0) + '%';

    // Update job info with current sheet
    if (job.current_sheet && job.current_sheet.name) {
      const cs = job.current_sheet;
      const countStr = cs.total ? ' (' + cs.index + '/' + cs.total + ')' : '';
      document.getElementById('jobInfo').textContent =
        'Project: ' + job.project + '  ·  Job: ' + job.id + '  ·  ' + cs.name + countStr;
    }

    // Log — handle both plain strings and structured entries
    const logBox = document.getElementById('logBox');
    logBox.innerHTML = (job.log || []).map(l => {
      const msg = typeof l === 'object' ? l.message : l;
      const isComplete = typeof l === 'object' && l.type === 'sheet_complete';
      const style = isComplete ? ' style="color:#4ade80"' : '';
      return '<div class="log-line"' + style + '>' + escHtml(String(msg)) + '</div>';
    }).join('');
    logBox.scrollTop = logBox.scrollHeight;

    if (job.status === 'done' || job.status === 'error') {
      clearInterval(pollInterval);
      if (job.status === 'done') {
        document.getElementById('progressFill').style.width = '100%';
        loadReports();
      }
      if (job.error) {
        logBox.innerHTML += '<div class="log-line" style="color:#f87171">Error: ' + escHtml(job.error) + '</div>';
      }
    }
  } catch (e) { /* ignore polling errors */ }
}

// ── Reports ────────────────────────────────────────────────────────────────
async function loadReports() {
  const el = document.getElementById('reportsList');
  el.innerHTML = '<p class="empty">Loading…</p>';
  try {
    const res = await fetch('/api/reports');
    const data = await res.json();
    if (!data.reports.length) {
      el.innerHTML = '<p class="empty">No reports yet. Run an estimation to generate one.</p>';
      return;
    }
    el.innerHTML = data.reports.map(r => {
      const files = r.files || {};
      const folder = encodeURIComponent(r.run_folder);
      const fileLink = (key, label, color) => {
        const f = files[key];
        if (!f) return '';
        const sizeKB = (f.size / 1024).toFixed(1);
        return '<a class="dl-btn" style="background:' + color + '" href="/api/reports/' + folder + '/' + encodeURIComponent(f.filename) + '" title="' + escHtml(f.filename) + ' (' + sizeKB + ' KB)">' + label + ' <span style="opacity:.7;font-size:11px">' + sizeKB + 'KB</span></a>';
      };
      return '<div class="report-item">' +
        '<div>' +
          '<div class="report-name">' + escHtml(r.project_name) + '</div>' +
          '<div class="report-meta">' + new Date(r.created * 1000).toLocaleString() + (r.sheets_processed ? ' · ' + r.sheets_processed + ' sheets' : '') + (r.total_cost_usd != null ? ' · <span style="color:#4ade80;font-weight:500">$' + r.total_cost_usd.toFixed(4) + '</span>' : '') + ' · <code style="font-size:11px;color:#888">' + escHtml(r.run_folder) + '/</code></div>' +
        '</div>' +
        '<div style="display:flex;gap:6px;flex-wrap:wrap">' +
          fileLink('calculated_csv', '📐 Calculations', '#1958c4') +
          fileLink('raw_csv', '📋 Raw items', '#0a7d4d') +
          fileLink('summary', '📄 Summary', '#7a4ad6') +
          fileLink('json', '{ } JSON', '#777') +
        '</div>' +
      '</div>';
    }).join('');
  } catch (e) {
    el.innerHTML = '<p class="empty">Failed to load reports.</p>';
  }
}

// ── Active Job Mini-Card Polling ───────────────────────────────────────────
async function pollActiveJob() {
  try {
    const resp = await fetch('/api/jobs/active');
    const data = await resp.json();
    const el = document.getElementById('sidebarJobCard');
    if (!el) return;

    if (data.active && data.job) {
      el.style.display = 'block';
      document.getElementById('miniProjectName').textContent = data.job.project || '—';
      document.getElementById('miniProgressBar').style.width = (data.job.progress || 0) + '%';
      document.getElementById('miniProgressPct').textContent = (data.job.progress || 0) + '%';
      const cs = data.job.current_sheet || {};
      document.getElementById('miniSheetCount').textContent = cs.total ? cs.index + '/' + cs.total : '';
      const phaseLbl = cs.phase ? ' (' + cs.phase + ')' : '';
      document.getElementById('miniCurrentSheet').textContent = cs.name ? cs.name + phaseLbl : '—';
    } else {
      el.style.display = 'none';
    }
  } catch (e) { /* ignore */ }
}

function startActiveJobPolling() {
  if (!activeJobPollInterval) {
    pollActiveJob();
    activeJobPollInterval = setInterval(pollActiveJob, 1500);
  }
}

function stopActiveJobPolling() {
  if (activeJobPollInterval) {
    clearInterval(activeJobPollInterval);
    activeJobPollInterval = null;
  }
}

function scrollToJobStatus() {
  const card = document.getElementById('progressCard');
  if (card && card.classList.contains('visible')) {
    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) stopActiveJobPolling();
  else startActiveJobPolling();
});

// ── Plan Selection ─────────────────────────────────────────────────────────
function getSheetType(sheetName) {
  const upper = (sheetName || '').toUpperCase();
  if (upper.match(/^A\d/) || upper.includes('FLOOR') || upper.includes('ELEVATION') || upper.includes('CEILING')) return 'architectural';
  if (upper.match(/^E\d/) || upper.includes('ELECTRICAL') || upper.includes('PANEL') || upper.includes('LIGHTING')) return 'electrical';
  if (upper.match(/^M\d/) || upper.includes('MECHANICAL') || upper.includes('HVAC') || upper.includes('PLUMBING')) return 'mechanical';
  if (upper.includes('SCHEDULE') || upper.includes('ROOM FINISH') || upper.includes('DOOR SCHED')) return 'schedule';
  return 'other';
}

function getTypeBadgeStyle(type) {
  const colors = {
    architectural: '#3b82f6',
    electrical: '#f59e0b',
    mechanical: '#f97316',
    schedule: '#8b5cf6',
    other: '#6b7280'
  };
  return 'background:' + (colors[type] || colors.other) + ';padding:2px 8px;border-radius:4px;font-size:11px;color:white;flex-shrink:0;';
}

async function loadProjectPlans() {
  if (!selectedProjectId) { alert('Please select a project first'); return; }
  const panel = document.getElementById('planSelectionPanel');
  const plansList = document.getElementById('plansList');
  panel.style.display = 'block';
  plansList.innerHTML = '<div style="color:#94a3b8;padding:20px;text-align:center;">Loading plans…</div>';
  try {
    const res = await fetch('/api/projects/' + selectedProjectId + '/plans');
    const data = await res.json();
    if (data.error) {
      plansList.innerHTML = '<div style="color:#ef4444;padding:20px;">Error: ' + escHtml(data.error) + '</div>';
      return;
    }
    allPlans = data.plans || [];
    if (!allPlans.length) {
      plansList.innerHTML = '<div style="color:#94a3b8;padding:20px;">No plans found for this project</div>';
      return;
    }
    renderPlansList(allPlans);
    updateSelectedCount();
  } catch (err) {
    plansList.innerHTML = '<div style="color:#ef4444;padding:20px;">Failed to load plans: ' + escHtml(err.message) + '</div>';
  }
}

function renderPlansList(plans) {
  const filter = document.getElementById('sheetTypeFilter').value;
  const filtered = filter === 'all' ? plans : plans.filter(p => getSheetType(p.sheet_name) === filter);
  if (!filtered.length) {
    document.getElementById('plansList').innerHTML = '<div style="color:#94a3b8;padding:20px;">No plans match the selected filter</div>';
    return;
  }
  document.getElementById('plansList').innerHTML = filtered.map(plan => {
    const type = getSheetType(plan.sheet_name);
    return '<label style="display:flex;align-items:center;padding:10px 12px;border-bottom:1px solid #252a3a;cursor:pointer;gap:12px;" data-type="' + type + '">' +
      '<input type="checkbox" class="plan-checkbox" value="' + plan.page_id + '" onchange="updateSelectedCount()" style="width:16px;height:16px;flex-shrink:0;">' +
      '<span style="flex:1;color:#f1f5f9;font-size:13px;">' + escHtml(plan.sheet_name || 'Unnamed Sheet') + '</span>' +
      '<span style="' + getTypeBadgeStyle(type) + '">' + type + '</span>' +
    '</label>';
  }).join('');
}

function toggleAllPlans(checked) {
  document.querySelectorAll('.plan-checkbox').forEach(cb => { cb.checked = checked; });
  updateSelectedCount();
}

function selectNone() {
  document.getElementById('selectAllPlans').checked = false;
  toggleAllPlans(false);
}

function filterPlansByType(type) {
  renderPlansList(allPlans);
  updateSelectedCount();
}

function updateSelectedCount() {
  const checked = document.querySelectorAll('.plan-checkbox:checked');
  const total = document.querySelectorAll('.plan-checkbox').length;
  const count = checked.length;
  document.getElementById('selectedCount').textContent = count + ' sheet' + (count !== 1 ? 's' : '') + ' selected';
  const btn = document.getElementById('runSelectedBtn');
  btn.disabled = count === 0;
  btn.style.opacity = count > 0 ? '1' : '0.5';
  document.getElementById('selectAllPlans').checked = count === total && total > 0;
}

async function runSelectedPlans() {
  const checked = document.querySelectorAll('.plan-checkbox:checked');
  const pageIds = Array.from(checked).map(cb => parseInt(cb.value));
  if (!pageIds.length) { alert('Please select at least one plan'); return; }
  const sel = document.getElementById('projectSelect');
  const projectName = sel.options[sel.selectedIndex]?.textContent || 'Project';
  try {
    const res = await fetch('/api/run/stackct', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'specific', project_id: selectedProjectId, project_name: projectName, page_ids: pageIds })
    });
    const data = await res.json();
    if (data.job_id) {
      document.getElementById('planSelectionPanel').style.display = 'none';
      startPolling(data.job_id, projectName);
    } else {
      alert('Failed to start job: ' + (data.error || 'Unknown error'));
    }
  } catch (err) {
    alert('Failed to start job: ' + err.message);
  }
}

// ── Utilities ──────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── Init ───────────────────────────────────────────────────────────────────
loadProjects();
startActiveJobPolling();
