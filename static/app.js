/**
 * Bobby Tailor — Estimation Automation
 * Client-side application logic
 *
 * Layout: Master.md §8.2–8.7
 */

// ── CSRF & Fetch Helpers ────────────────────────────────────────────────────

/**
 * Get CSRF token from meta tag.
 * @returns {string} CSRF token or empty string if not found
 */
function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : '';
}

/**
 * Fetch wrapper that automatically adds CSRF token and credentials.
 * Use for all API calls instead of raw fetch().
 * @param {string} url - API endpoint
 * @param {object} options - fetch options
 * @returns {Promise<Response>}
 */
function apiFetch(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const needsCsrf = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method);

  const headers = { ...(options.headers || {}) };
  if (needsCsrf) {
    headers['X-CSRFToken'] = getCsrfToken();
  }

  return fetch(url, {
    ...options,
    credentials: 'same-origin',
    headers,
  });
}

// ── State ──────────────────────────────────────────────────────────────────
let currentMode = 'all';
let selectedFile = null;
let pollInterval = null;
let projectsLoaded = false;
let allProjects = [];
let allPlans = [];
let allPlanSets = [];
let selectedProject = null;
let selectedPlanSet = null;
let projectSheetCounts = {};
let searchDebounceTimer = null;
let activeJobPollInterval = null;

// ── Navigation ─────────────────────────────────────────────────────────────
const PAGE_TITLES = {
  projects: 'StackCT Projects',
  pdf: 'Upload PDF',
  reports: 'Reports',
  'job-monitor': 'Job Monitor',
  settings: 'Settings'
};

let allReports = [];
let reportsSearchQuery = '';
let openPreviewFolder = null;
let openPreviewTab = {};
let currentJobId = null;
let monitorPollInterval = null;
let currentPdfUpload = null;

function navigateTo(pageName) {
  const target = document.getElementById('page-' + pageName);
  if (!target) return;

  document.querySelectorAll('.page-section').forEach(s => s.classList.remove('active'));
  target.classList.add('active');

  if (window.uiMotion?.pageEnter) {
    window.uiMotion.pageEnter(target);
  }

  document.querySelectorAll('.nav-item[data-page]').forEach(n => n.classList.remove('active'));
  const navItem = document.querySelector('.nav-item[data-page="' + pageName + '"]');
  if (navItem) navItem.classList.add('active');

  const titleEl = document.getElementById('pageTitle');
  if (titleEl) titleEl.textContent = PAGE_TITLES[pageName] || pageName;

  if (pageName === 'reports') loadReports();
  if (pageName === 'projects' && !projectsLoaded) loadProjects();
}

// ── Mode ───────────────────────────────────────────────────────────────────
function setMode(mode) {
  currentMode = mode;
  document.getElementById('modeAll').classList.toggle('active', mode === 'all');
  document.getElementById('modeOne').classList.toggle('active', mode === 'specific');
  document.getElementById('projectListField').style.display = mode === 'specific' ? 'block' : 'none';
  if (mode === 'all') {
    resetPlanSelection();
    selectedProject = null;
    updatePreviewButton();
  }
  if (mode === 'specific' && !projectsLoaded) loadProjects();
}

// ── Projects List (Master §8.3) ────────────────────────────────────────────
async function loadProjects(force = false) {
  const listEl = document.getElementById('projectList');
  const status = document.getElementById('cacheStatus');
  const refreshBtn = document.getElementById('refreshBtn');

  listEl.innerHTML = '<p class="empty">Loading…</p>';
  if (status) status.textContent = force ? 'Fetching live…' : 'Loading…';
  if (refreshBtn) refreshBtn.disabled = true;

  try {
    const url = force ? '/api/projects?refresh=1' : '/api/projects';
    const res = await fetch(url, { credentials: 'same-origin' });
    const data = await res.json();

    if (data.error && !data.projects?.length) {
      listEl.innerHTML = '<p class="empty">Could not load projects</p>';
      if (status) status.textContent = 'Could not load';
      return;
    }

    allProjects = data.projects || [];
    projectsLoaded = true;
    await loadSheetCounts();
    renderProjectList(allProjects);

    if (status) {
      const when = data.fetched_at ? new Date(data.fetched_at).toLocaleString() : '';
      let tag;
      if (data.names_refreshing) {
        tag = 'Refreshing names…';
      } else if (data.syncing) {
        tag = 'Syncing…';
      } else if (data.from_cache && data.stale) {
        tag = 'Cached · refreshing';
      } else if (data.from_cache) {
        tag = 'Cached';
      } else {
        tag = 'Live';
      }
      status.textContent = tag + ' · ' + allProjects.length + ' projects' + (when ? ' · ' + when : '');

      // Warn when most names are still placeholders (stale DB)
      const placeholders = allProjects.filter(p => /^Project_\d+$/.test(p.name || '')).length;
      if (placeholders > allProjects.length * 0.3) {
        status.textContent += ' · ' + placeholders + ' unnamed — click ↻ Refresh to fix';
      }
    }
  } catch (e) {
    listEl.innerHTML = '<p class="empty">Network error loading projects</p>';
    if (status) status.textContent = 'Network error';
  } finally {
    if (refreshBtn) refreshBtn.disabled = false;
  }
}

async function loadSheetCounts() {
  try {
    const res = await fetch('/api/projects/sheet-counts', { credentials: 'same-origin' });
    if (!res.ok) return;
    const data = await res.json();
    const counts = data.counts || {};
    Object.keys(counts).forEach(id => {
      projectSheetCounts[parseInt(id, 10)] = counts[id];
    });
    if (allProjects.length) renderProjectList(allProjects);
  } catch (_) {
    /* non-fatal */
  }
}

function renderProjectList(projects) {
  const listEl = document.getElementById('projectList');
  const query = (document.getElementById('projectSearch')?.value || '').toLowerCase();

  const filtered = projects.filter(p =>
    !query || (p.name || '').toLowerCase().includes(query)
  );

  if (!filtered.length) {
    listEl.innerHTML = '<p class="empty">' + (query ? 'No projects match your search' : 'No projects found') + '</p>';
    return;
  }

  listEl.innerHTML = filtered.map(p => {
    const isSelected = selectedProject && selectedProject.id === p.id;
    const meta = projectSheetCounts[p.id];
    let countLabel = '<span class="sheet-count-unknown" title="Plan set count loads from cache or background sync">—</span>';
    if (meta != null) {
      if (typeof meta === 'object') {
        const sets = meta.plan_set_count;
        const sheets = meta.sheet_count;
        if (sets != null && sets > 0) {
          countLabel = sets + ' set' + (sets !== 1 ? 's' : '');
          if (sheets != null) countLabel += ' · ' + sheets + ' sheets';
        } else if (sheets != null) {
          countLabel = sheets + ' sheet' + (sheets !== 1 ? 's' : '');
        }
      } else if (typeof meta === 'number') {
        countLabel = meta + ' sheet' + (meta !== 1 ? 's' : '');
      }
    }
    return '<div class="project-item' + (isSelected ? ' selected' : '') + '" data-id="' + p.id + '" data-name="' + escHtml(p.name) + '" role="button" tabindex="0" aria-label="Select project ' + escHtml(p.name) + '">' +
      '<input type="radio" name="projectPick" class="project-radio"' + (isSelected ? ' checked' : '') + ' tabindex="-1" aria-hidden="true">' +
      '<div class="project-info">' +
        '<div class="project-name">' + escHtml(p.name) + '</div>' +
        '<div class="project-id">ID: ' + p.id + '</div>' +
      '</div>' +
      '<span class="sheet-count">' + countLabel + '</span>' +
    '</div>';
  }).join('');
}

function applyPlanSetCountsFromApi(projectId, data) {
  const sets = data.plan_sets || [];
  if (!sets.length && !data.syncing) return;
  let sheetTotal = null;
  if (sets.length && sets.every(s => s.sheet_count != null)) {
    sheetTotal = sets.reduce((n, s) => n + (s.sheet_count || 0), 0);
  }
  projectSheetCounts[projectId] = {
    plan_set_count: sets.length || projectSheetCounts[projectId]?.plan_set_count,
    sheet_count: sheetTotal,
  };
  renderProjectList(allProjects);
}

function pollPlanSetCounts(projectId, attemptsLeft) {
  if (attemptsLeft <= 0) return;
  if (!selectedProject || selectedProject.id !== projectId) return;
  fetch('/api/projects/' + projectId + '/plan-sets', { credentials: 'same-origin' })
    .then(r => (r.ok ? r.json() : null))
    .then(data => {
      if (!data) return;
      applyPlanSetCountsFromApi(projectId, data);
      if (data.syncing && attemptsLeft > 1) {
        setTimeout(() => pollPlanSetCounts(projectId, attemptsLeft - 1), 2500);
      }
    })
    .catch(() => {});
}

/** DB-first plan set index — never blocks on a full StackCT login from the UI thread. */
function warmPlanSetCounts(projectId) {
  const meta = projectSheetCounts[projectId];
  if (meta && meta.plan_set_count != null) return;

  fetch('/api/projects/' + projectId + '/plan-sets', { credentials: 'same-origin' })
    .then(r => (r.ok ? r.json() : null))
    .then(data => {
      if (!data) return;
      applyPlanSetCountsFromApi(projectId, data);
      if (data.syncing) pollPlanSetCounts(projectId, 12);
    })
    .catch(() => {});
}

function onProjectSelect(projectId, projectName) {
  resetPlanSelection();
  selectedProject = { id: projectId, name: projectName };
  document.getElementById('projectMeta').textContent = 'Project ID: ' + projectId;
  renderProjectList(allProjects);
  updatePreviewButton();
  warmPlanSetCounts(projectId);
}

function updatePreviewButton() {
  const btn = document.getElementById('previewPlansBtn');
  const refreshPlansBtn = document.getElementById('refreshPlansBtn');
  const on = !!selectedProject;
  if (btn) btn.disabled = !on;
  if (refreshPlansBtn) refreshPlansBtn.disabled = !on;
}

function filterProjects(query) {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => renderProjectList(allProjects), 200);
}

async function refreshProjects() {
  projectsLoaded = false;
  resetPlanSelection();
  selectedProject = null;
  updatePreviewButton();
  await loadProjects(true);
}

// ── Run StackCT ────────────────────────────────────────────────────────────
async function runStackCT() {
  const btn = document.getElementById('runStackctBtn');

  if (currentMode === 'specific') {
    const panel = document.getElementById('planSelectionPanel');
    if (panel && panel.style.display !== 'none') {
      return runSelectedPlans();
    }
    if (!selectedProject) {
      alert('Please select a project first.');
      return;
    }
    document.getElementById('previewPlansBtn').click();
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Starting…';

  try {
    const res = await apiFetch('/api/run/stackct', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'all', project_name: 'All Projects' })
    });
    const data = await res.json();
    if (data.error) {
      alert('Error: ' + data.error);
      return;
    }
    startPolling(data.job_id, 'All Projects');
  } catch (e) {
    alert('Failed to start job: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '▶ Run All';
  }
}

// ── PDF Upload & Page Selection (Master §8.6) ───────────────────────────────
function formatFileSize(bytes) {
  if (bytes == null) return '—';
  const mb = bytes / 1024 / 1024;
  return mb >= 0.1 ? mb.toFixed(1) + ' MB' : (bytes / 1024).toFixed(0) + ' KB';
}

async function uploadPdfFile(file) {
  selectedFile = file;
  currentPdfUpload = null;

  const metaEl = document.getElementById('pdfUploadMeta');
  const pageSel = document.getElementById('pageSelection');
  const runBtn = document.getElementById('runPdfBtn');

  metaEl.style.display = 'block';
  metaEl.textContent = 'Uploading…';
  pageSel.style.display = 'none';
  runBtn.disabled = true;

  const form = new FormData();
  form.append('file', file);

  try {
    const res = await apiFetch('/api/pdf/upload', { method: 'POST', body: form });
    const data = await res.json();
    if (data.error) {
      metaEl.textContent = 'Error: ' + data.error;
      return;
    }

    currentPdfUpload = data;
    if (!document.getElementById('pdfProjectName').value) {
      document.getElementById('pdfProjectName').value = file.name.replace(/\.pdf$/i, '');
    }

    metaEl.textContent = '✓ ' + data.filename + ' · ' + data.page_count + ' pages · ' + formatFileSize(data.file_size_bytes);
    document.getElementById('totalPageCount').textContent = data.page_count;
    renderPdfPageList(data.pages || []);
    pageSel.style.display = 'block';
    runBtn.disabled = false;
  } catch (e) {
    metaEl.textContent = 'Upload failed: ' + e.message;
  }
}

function onFileSelected(input) {
  const file = input.files[0];
  if (!file) return;
  document.getElementById('selectedFileName').textContent = file.name;
  uploadPdfFile(file);
}

function renderPdfPageList(pages) {
  const list = document.getElementById('pdfPageList');
  list.innerHTML = pages.map(p =>
    '<label class="page-checkbox-label">' +
      '<input type="checkbox" value="' + p.page_num + '" checked> ' +
      p.page_num + '. ' + escHtml(p.sheet_name) +
    '</label>'
  ).join('');
}

function togglePdfPageList() {
  const mode = document.querySelector('input[name="pageMode"]:checked')?.value;
  const wrap = document.getElementById('pdfPageListWrap');
  if (wrap) wrap.style.display = mode === 'select' ? 'block' : 'none';
}

function selectAllPdfPages(checked) {
  document.querySelectorAll('#pdfPageList input[type="checkbox"]').forEach(cb => {
    cb.checked = checked;
  });
}

function getSelectedPdfPages() {
  const mode = document.querySelector('input[name="pageMode"]:checked')?.value;
  if (mode === 'all') return null;
  const pages = Array.from(document.querySelectorAll('#pdfPageList input:checked'))
    .map(cb => parseInt(cb.value, 10));
  return pages.length ? pages : [];
}

async function runPDF() {
  if (!currentPdfUpload) {
    alert('Please upload a PDF first.');
    return;
  }

  const selectedPages = getSelectedPdfPages();
  if (Array.isArray(selectedPages) && selectedPages.length === 0) {
    alert('Please select at least one page.');
    return;
  }

  const btn = document.getElementById('runPdfBtn');
  const name = document.getElementById('pdfProjectName').value || currentPdfUpload.filename.replace(/\.pdf$/i, '');
  btn.disabled = true;
  btn.textContent = 'Starting…';

  try {
    const res = await apiFetch('/api/pdf/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        upload_id: currentPdfUpload.upload_id,
        project_name: name,
        selected_pages: selectedPages,
      }),
    });
    const data = await res.json();
    if (data.error) {
      alert(data.error);
      return;
    }
    startPolling(data.job_id, name);
  } catch (e) {
    alert('Failed to start analysis: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '▶ Analyze PDF';
  }
}

function bindPdfEvents() {
  const inp = document.getElementById('fileInput');
  const dz = document.getElementById('dropZone');
  if (inp) inp.addEventListener('change', () => onFileSelected(inp));

  if (dz) {
    dz.addEventListener('click', () => inp?.click());
    dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag-over'); });
    dz.addEventListener('dragleave', () => dz.classList.remove('drag-over'));
    dz.addEventListener('drop', e => {
      e.preventDefault();
      dz.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file && file.name.toLowerCase().endsWith('.pdf')) {
        const dt = new DataTransfer();
        dt.items.add(file);
        inp.files = dt.files;
        onFileSelected(inp);
      }
    });
  }

  document.querySelectorAll('input[name="pageMode"]').forEach(r => {
    r.addEventListener('change', togglePdfPageList);
  });

  const runBtn = document.getElementById('runPdfBtn');
  if (runBtn) runBtn.addEventListener('click', runPDF);

  document.getElementById('pdfSelectAllBtn')?.addEventListener('click', () => selectAllPdfPages(true));
  document.getElementById('pdfSelectNoneBtn')?.addEventListener('click', () => selectAllPdfPages(false));
}

// ── Job polling & monitor (Master §8.4) ────────────────────────────────────
function startPolling(jobId, projectName) {
  currentJobId = jobId;
  if (pollInterval) clearInterval(pollInterval);
  if (monitorPollInterval) clearInterval(monitorPollInterval);

  const navMonitor = document.getElementById('navJobMonitor');
  if (navMonitor) navMonitor.style.display = 'flex';

  navigateTo('job-monitor');
  document.getElementById('monitorProjectName').textContent = projectName;
  document.getElementById('monitorJobId').textContent = 'Job: ' + jobId;
  document.getElementById('cancelJobBtn').style.display = 'inline-block';

  const card = document.getElementById('progressCard');
  if (card) card.classList.remove('visible');

  pollJobMonitor(jobId);
  monitorPollInterval = setInterval(() => pollJobMonitor(jobId), 1500);
}

function stopJobPolling() {
  if (monitorPollInterval) {
    clearInterval(monitorPollInterval);
    monitorPollInterval = null;
  }
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
}

async function pollJobMonitor(jobId) {
  try {
    const res = await fetch('/api/status/' + jobId, { credentials: 'same-origin' });
    if (!res.ok) return;
    const job = await res.json();

    updateMonitorUI(job);

    if (['done', 'error', 'cancelled'].includes(job.status)) {
      stopJobPolling();
      handleJobCompletion(job);
    }
  } catch (e) { /* ignore */ }
}

function updateMonitorUI(job) {
  const statusEl = document.getElementById('monitorStatus');
  const statusLabels = {
    queued: '● QUEUED',
    running: '● RUNNING',
    done: '✓ COMPLETED',
    error: '✗ ERROR',
    cancelled: '⊘ CANCELLED'
  };
  statusEl.textContent = statusLabels[job.status] || job.status;
  statusEl.className = 'status-badge badge-' + (job.status === 'cancelled' ? 'cancelled' : job.status);

  // Phase badge — shows current operation phase during a run
  const phaseBadge = document.getElementById('monitorPhaseBadge');
  if (phaseBadge) {
    const phase = job.current_phase || (job.current_sheet && job.current_sheet.phase);
    const phaseLabels = {
      capturing:  'Capturing',
      analyzing:  'Analyzing',
      reporting:  'Reporting',
      complete:   'Analyzing',
    };
    const phaseLabel = phase && phaseLabels[phase];
    if (phaseLabel && job.status === 'running') {
      phaseBadge.textContent = phaseLabel;
      phaseBadge.className = 'phase-badge phase-' + phase;
      phaseBadge.style.display = '';
    } else {
      phaseBadge.style.display = 'none';
    }
  }

  const pct = job.progress || 0;
  document.getElementById('monitorProgressFill').style.width = pct + '%';
  document.getElementById('monitorPercent').textContent = pct + '%';

  const cs = job.current_sheet || {};
  const total = cs.total || job.total_sheets || 0;
  const completed = job.sheets_completed || 0;
  document.getElementById('monitorSheetCount').textContent =
    '[' + completed + ' / ' + (total || '?') + ' sheets]';

  if (job.started_at) {
    const t = new Date(job.started_at);
    document.getElementById('monitorStarted').textContent =
      'Started: ' + t.toLocaleTimeString();
  }

  const sheetEl = document.getElementById('monitorCurrentSheet');
  if (cs.name && job.status === 'running') {
    const phaseVerb = cs.phase === 'capturing' ? 'Capturing' : 'Analyzing';
    sheetEl.innerHTML =
      phaseVerb + ': <strong>' + escHtml(cs.name) + '</strong>';
    sheetEl.className = 'monitor-current-sheet';
  }

  renderMonitorSheetLog(job);
  renderMonitorLogConsole(job.log || []);
}

function renderMonitorSheetLog(job) {
  const container = document.getElementById('monitorSheetLog');
  if (!container) return;

  const rows = [];
  const completed = job.sheet_log_full || job.sheet_log || [];
  completed.forEach(s => {
    const ext = s.extraction || {};
    rows.push({
      status: 'done',
      name: s.name || '—',
      metrics: (ext.measurements || 0) + ' meas  ' + (ext.rooms || 0) + ' rooms  ' + (ext.components || 0) + ' comp'
    });
  });

  const cs = job.current_sheet || {};
  if (cs.name && cs.phase && cs.phase !== 'complete') {
    rows.push({ status: 'analyzing', name: cs.name, metrics: 'analyzing…' });
  }

  if (!rows.length) {
    container.innerHTML = '<div class="sheet-row"><span class="sheet-status">○</span><span>Waiting for sheets…</span></div>';
    return;
  }

  const icons = { done: '✓', analyzing: '⟳', pending: '○' };
  container.innerHTML = rows.map(r =>
    '<div class="sheet-row ' + r.status + '">' +
      '<span class="sheet-status">' + (icons[r.status] || '○') + '</span>' +
      '<span class="sheet-name">' + escHtml(r.name) + '</span>' +
      '<span class="sheet-metrics">' + escHtml(r.metrics) + '</span>' +
    '</div>'
  ).join('');
}

function renderMonitorLogConsole(logs) {
  const console = document.getElementById('monitorLogConsole');
  if (!console) return;

  console.innerHTML = logs.map(l => {
    const msg = typeof l === 'object' ? (l.message || '') : String(l);
    const ts = typeof l === 'object' && l.timestamp
      ? new Date(l.timestamp).toLocaleTimeString()
      : '';
    return '<div class="log-entry">' +
      (ts ? '<span class="log-time">[' + ts + ']</span> ' : '') +
      escHtml(msg) + '</div>';
  }).join('');
  console.scrollTop = console.scrollHeight;
}

function handleJobCompletion(job) {
  document.getElementById('cancelJobBtn').style.display = 'none';
  const navMonitor = document.getElementById('navJobMonitor');
  if (navMonitor) navMonitor.style.display = 'none';

  // Hide phase badge on completion
  const phaseBadge = document.getElementById('monitorPhaseBadge');
  if (phaseBadge) phaseBadge.style.display = 'none';

  const sheetEl = document.getElementById('monitorCurrentSheet');
  if (job.status === 'done') {
    if (job.warning) {
      sheetEl.innerHTML =
        '<span class="monitor-warning-banner">⚠ ' + escHtml(job.warning) + '</span>';
    } else {
      sheetEl.innerHTML = '<span class="monitor-success-text">✓ Job completed successfully.</span>';
    }
    setTimeout(() => {
      navigateTo('reports');
      loadReports();
    }, 2000);
  } else if (job.status === 'cancelled') {
    if (job.warning) {
      sheetEl.innerHTML =
        '<span class="monitor-warning-banner">⊘ ' + escHtml(job.warning) + '</span>';
    } else {
      sheetEl.innerHTML = '<span class="monitor-warning-banner">⊘ Job cancelled.</span>';
    }
    if (job.has_result) {
      setTimeout(() => { navigateTo('reports'); loadReports(); }, 2500);
    }
  } else if (job.status === 'error' && job.error) {
    sheetEl.innerHTML =
      '<span class="monitor-error-banner">✗ ' + escHtml(job.error) + '</span>';
  }
}

async function cancelJob() {
  if (!currentJobId) return;
  if (!confirm('Cancel this job?')) return;

  try {
    const res = await apiFetch('/api/cancel/' + currentJobId, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      stopJobPolling();
      document.getElementById('monitorStatus').textContent = '⊘ CANCELLED';
      document.getElementById('monitorStatus').className = 'status-badge badge-cancelled';
      document.getElementById('cancelJobBtn').style.display = 'none';
    } else if (data.error) {
      alert(data.error);
    }
  } catch (e) {
    alert('Cancel failed: ' + e.message);
  }
}

// ── Reports (Master §8.5) ────────────────────────────────────────────────────
async function loadReports() {
  const grid = document.getElementById('reportsGrid');
  if (!grid) return;
  grid.innerHTML = '<p class="empty">Loading…</p>';

  try {
    const res = await fetch('/api/reports', { credentials: 'same-origin' });
    const data = await res.json();
    allReports = data.reports || [];
    renderReportsGrid();
  } catch (e) {
    grid.innerHTML = '<p class="empty">Failed to load reports.</p>';
  }
}

function filterReports(query) {
  reportsSearchQuery = (query || '').toLowerCase();
  renderReportsGrid();
}

function renderReportsGrid() {
  const grid = document.getElementById('reportsGrid');
  const filtered = allReports.filter(r =>
    !reportsSearchQuery || (r.project_name || '').toLowerCase().includes(reportsSearchQuery)
  );

  if (!filtered.length) {
    grid.innerHTML = '<p class="empty">' +
      (reportsSearchQuery ? 'No reports match your search.' : 'No reports yet. Run an estimation to generate one.') +
      '</p>';
    return;
  }

  grid.innerHTML = filtered.map(r => renderReportCard(r)).join('');

  if (window.uiMotion?.staggerChildren) {
    window.uiMotion.staggerChildren(grid, '.report-card');
  }

  // Phase 15: Open report workspace instead of inline preview
  grid.querySelectorAll('.btn-preview-workspace').forEach(btn => {
    btn.addEventListener('click', () => {
      if (window.reportWorkspace) {
        window.reportWorkspace.openReportWorkspace(btn.dataset.folder);
      }
    });
  });
  
  grid.querySelectorAll('.btn-download').forEach(btn => {
    btn.addEventListener('click', () => downloadReportFile(btn.dataset.folder, btn.dataset.file));
  });
  
  // Export dropdown toggle
  grid.querySelectorAll('.btn-export-toggle').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const dropdown = btn.closest('.export-dropdown');
      dropdown.classList.toggle('open');
    });
  });
}

function renderReportCard(r) {
  const folder = r.run_folder;
  const enc = encodeURIComponent(folder);
  const date = r.created ? new Date(r.created * 1000).toLocaleDateString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric'
  }) : '';
  const sheets = r.sheets_processed != null ? r.sheets_processed + ' sheets' : '— sheets';
  const raw = r.raw_items_count != null ? r.raw_items_count + ' raw items' : '';
  const calc = r.calculated_count != null ? r.calculated_count + ' calculated' : '';
  const cost = r.total_cost_usd != null ? '$' + r.total_cost_usd.toFixed(4) : '';
  const files = r.files || {};
  
  // Phase 15: Simple download links, workspace replaces inline preview
  const dl = (fileKey, label) => {
    const f = files[fileKey];
    if (!f) return '';
    return '<button type="button" class="btn-download" data-folder="' + escHtml(folder) + '" data-file="' + escHtml(f.filename) + '">' + label + '</button>';
  };

  const cachePill = r.from_cache ? '<span class="pill pill-success">Cached</span>' : '';

  return '<div class="report-card" data-folder="' + escHtml(folder) + '">' +
    '<div class="card-header">' +
      '<span class="project-name">' + escHtml(r.project_name) + '</span>' +
      '<div class="card-header-right">' +
        cachePill +
        '<span class="report-date">' + escHtml(date) + '</span>' +
      '</div>' +
    '</div>' +
    '<div class="card-meta">' +
      '<span>' + sheets + '</span>' +
      (raw ? '<span>·</span><span>' + raw + '</span>' : '') +
      (calc ? '<span>·</span><span>' + calc + '</span>' : '') +
      (cost ? '<span>·</span><span class="cost">' + cost + '</span>' : '') +
    '</div>' +
    '<div class="card-actions">' +
      '<button type="button" class="btn-preview-workspace btn-primary-cta" data-folder="' + escHtml(folder) + '">' +
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
          '<path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>' +
        '</svg>' +
        'Open Preview' +
      '</button>' +
      '<div class="export-dropdown">' +
        '<button type="button" class="btn-export-toggle">Export ▾</button>' +
        '<div class="export-menu">' +
          dl('takeoff_summary_csv', 'Summary CSV') +
          dl('calculated_csv', 'Calc CSV') +
          dl('raw_csv', 'Raw CSV') +
          dl('json', 'JSON') +
          dl('summary', 'TXT') +
        '</div>' +
      '</div>' +
    '</div>' +
  '</div>';
}

function renderPreviewPanel(folder, activeTab, hasTakeoffSummary) {
  const tabs = [];
  if (hasTakeoffSummary) tabs.push('takeoff');
  tabs.push('summary', 'calculations', 'raw', 'json');
  const labels = {
    takeoff: 'Takeoff Summary',
    summary: 'Run Log',
    calculations: 'Calculations',
    raw: 'Raw Items',
    json: 'JSON'
  };
  return '<div class="preview-panel glass-panel" id="preview-panel-' + escHtml(folder) + '">' +
    '<div class="preview-tabs">' +
      tabs.map(t =>
        '<button type="button" class="tab' + (t === activeTab ? ' active' : '') + '" data-folder="' + escHtml(folder) + '" data-tab="' + t + '">' + labels[t] + '</button>'
      ).join('') +
    '</div>' +
    '<div class="preview-content" data-folder="' + escHtml(folder) + '">' +
      '<p class="loading"><span class="spinner"></span> Loading…</p>' +
    '</div>' +
  '</div>';
}

async function togglePreview(folder) {
  if (openPreviewFolder === folder) {
    openPreviewFolder = null;
    renderReportsGrid();
    return;
  }
  openPreviewFolder = folder;
  const report = allReports.find(r => r.run_folder === folder);
  const hasTakeoff = report?.files?.takeoff_summary_csv;
  if (!openPreviewTab[folder]) openPreviewTab[folder] = hasTakeoff ? 'takeoff' : 'summary';
  renderReportsGrid();
  await loadPreviewTab(folder, openPreviewTab[folder]);
}

async function switchPreviewTab(folder, tab) {
  openPreviewTab[folder] = tab;
  const card = document.querySelector('.report-card[data-folder="' + CSS.escape(folder) + '"]');
  card?.querySelectorAll('.preview-tabs .tab').forEach(el => {
    el.classList.toggle('active', el.dataset.tab === tab);
  });
  await loadPreviewTab(folder, tab);
}

async function loadPreviewTab(folder, tab) {
  const content = document.querySelector('.preview-content[data-folder="' + CSS.escape(folder) + '"]');
  if (!content) return;
  content.innerHTML = '<p class="loading"><span class="spinner"></span> Loading…</p>';

  const enc = encodeURIComponent(folder);
  try {
    if (tab === 'takeoff') {
      const res = await fetch('/api/reports/' + enc + '/preview/takeoff_summary.csv', { credentials: 'same-origin' });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      content.innerHTML = renderTakeoffSummaryTable(data.rows || []);
    } else if (tab === 'summary') {
      const res = await fetch('/api/reports/' + enc + '/preview/summary.txt', { credentials: 'same-origin' });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      content.innerHTML = formatSummaryHtml(data.content || '');
    } else if (tab === 'calculations') {
      await loadCsvPreview(content, enc, 'calculations.csv', {
        filterCols: ['source_sheet', 'item_type'],
        searchCols: ['description', 'formula_applied']
      });
    } else if (tab === 'raw') {
      await loadCsvPreview(content, enc, 'raw_items.csv', {
        filterCols: ['source_sheet', 'type'],
        searchCols: ['description', 'source_location']
      });
    } else if (tab === 'json') {
      const res = await fetch('/api/reports/' + enc + '/preview/takeoff.json', { credentials: 'same-origin' });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      content.innerHTML = '<div class="json-tree">' + renderJsonTree(data.data, 0, true) + '</div>';
      bindJsonToggles(content);
    }
  } catch (e) {
    content.innerHTML = '<p class="error">Failed to load preview: ' + escHtml(e.message) + '</p>';
  }
}

async function loadCsvPreview(container, encFolder, filename, opts) {
  const res = await fetch('/api/reports/' + encFolder + '/preview/' + filename, { credentials: 'same-origin' });
  const data = await res.json();
  if (data.error) throw new Error(data.error);

  const capNote = data.capped
    ? '<p class="preview-cap-note">Showing ' + data.count + ' of ' + data.total + ' rows (cap: ' + data.cap_limit + ')</p>'
    : '';

  container.innerHTML = capNote + renderDataTable(data.headers, data.rows, opts);
  bindDataTable(container.querySelector('.data-table'), data.headers, data.rows, opts);
}

function renderDataTable(headers, rows, opts) {
  const filterCols = opts.filterCols || [];
  const id = 'tbl-' + Math.random().toString(36).slice(2, 8);

  let toolbar = '<div class="table-toolbar">';
  toolbar += '<input type="text" placeholder="Search…" class="table-search" data-table="' + id + '">';
  filterCols.forEach(col => {
    const vals = [...new Set(rows.map(r => r[col]).filter(Boolean))].sort();
    toolbar += '<select class="table-filter" data-table="' + id + '" data-col="' + col + '">' +
      '<option value="">All ' + col.replace(/_/g, ' ') + '</option>' +
      vals.map(v => '<option value="' + escHtml(String(v)) + '">' + escHtml(String(v)) + '</option>').join('') +
    '</select>';
  });
  toolbar += '</div>';

  const ths = headers.map(h =>
    '<th data-col="' + escHtml(h) + '">' + escHtml(h) + '</th>'
  ).join('');

  const trs = rows.map((row, i) =>
    '<tr data-idx="' + i + '">' + headers.map(h => '<td>' + escHtml(row[h] ?? '') + '</td>').join('') + '</tr>'
  ).join('');

  return toolbar +
    '<div class="data-table-wrap"><table class="data-table" id="' + id + '" data-headers="' + escHtml(JSON.stringify(headers)) + '">' +
    '<thead><tr>' + ths + '</tr></thead><tbody>' + trs + '</tbody></table></div>';
}

function bindDataTable(table, headers, allRows, opts) {
  if (!table) return;
  const wrap = table.closest('.preview-content') || table.parentElement;
  const searchInput = wrap.querySelector('.table-search');
  const filters = wrap.querySelectorAll('.table-filter');
  let sortCol = null;
  let sortDir = 1;

  function applyFilters() {
    let rows = [...allRows];
    const q = (searchInput?.value || '').toLowerCase();
    if (q) {
      const cols = opts.searchCols || headers;
      rows = rows.filter(r => cols.some(c => String(r[c] || '').toLowerCase().includes(q)));
    }
    filters.forEach(sel => {
      const col = sel.dataset.col;
      if (sel.value) rows = rows.filter(r => String(r[col]) === sel.value);
    });
    if (sortCol) {
      rows.sort((a, b) => {
        const av = String(a[sortCol] ?? '');
        const bv = String(b[sortCol] ?? '');
        return sortDir * av.localeCompare(bv, undefined, { numeric: true });
      });
    }
    const tbody = table.querySelector('tbody');
    tbody.innerHTML = rows.map(row =>
      '<tr>' + headers.map(h => '<td>' + escHtml(row[h] ?? '') + '</td>').join('') + '</tr>'
    ).join('');
  }

  searchInput?.addEventListener('input', applyFilters);
  filters.forEach(f => f.addEventListener('change', applyFilters));
  table.querySelectorAll('th').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (sortCol === col) sortDir *= -1;
      else { sortCol = col; sortDir = 1; }
      table.querySelectorAll('th').forEach(h => h.classList.remove('sorted-asc', 'sorted-desc'));
      th.classList.add(sortDir === 1 ? 'sorted-asc' : 'sorted-desc');
      applyFilters();
    });
  });
}

function renderJsonTree(obj, depth, expanded) {
  if (obj === null || typeof obj !== 'object') {
    return '<span class="json-value">' + escHtml(JSON.stringify(obj)) + '</span>';
  }
  const isArr = Array.isArray(obj);
  const entries = isArr ? obj.map((v, i) => [i, v]) : Object.entries(obj);
  const id = 'jn-' + Math.random().toString(36).slice(2, 9);

  let html = '<div class="json-node">';
  if (entries.length) {
    html += '<span class="json-toggle" data-target="' + id + '">' + (expanded ? '▼' : '▶') + '</span>';
    html += '<span class="json-bracket">' + (isArr ? '[' : '{') + '</span>';
    html += '<div class="json-children' + (expanded ? '' : ' collapsed') + '" id="' + id + '">';
    entries.forEach(([key, val]) => {
      html += '<div class="json-entry">';
      if (!isArr) html += '<span class="json-key">"' + escHtml(String(key)) + '"</span>: ';
      if (val !== null && typeof val === 'object') {
        html += renderJsonTree(val, depth + 1, depth < 1);
      } else {
        html += '<span class="json-value">' + escHtml(JSON.stringify(val)) + '</span>';
      }
      html += '</div>';
    });
    html += '</div>';
    html += '<span class="json-bracket">' + (isArr ? ']' : '}') + '</span>';
  } else {
    html += '<span class="json-bracket">' + (isArr ? '[]' : '{}') + '</span>';
  }
  html += '</div>';
  return html;
}

function bindJsonToggles(container) {
  container.querySelectorAll('.json-toggle').forEach(toggle => {
    toggle.addEventListener('click', () => {
      const target = document.getElementById(toggle.dataset.target);
      if (!target) return;
      target.classList.toggle('collapsed');
      toggle.textContent = target.classList.contains('collapsed') ? '▶' : '▼';
    });
  });
}

function downloadReportFile(folder, filename) {
  const url = '/api/reports/' + encodeURIComponent(folder) + '/' + encodeURIComponent(filename);
  window.open(url, '_blank');
}

// ── Active Job Mini-Card Polling ───────────────────────────────────────────
async function pollActiveJob() {
  try {
    const resp = await fetch('/api/jobs/active', { credentials: 'same-origin' });
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
  if (currentJobId) navigateTo('job-monitor');
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) stopActiveJobPolling();
  else startActiveJobPolling();
});

// ── Plan Selection (Master §8.3 + Phase 4 APIs) ────────────────────────────
function inferSheetType(sheetName, apiType) {
  if (apiType) return apiType;
  const upper = (sheetName || '').toUpperCase();
  if (upper.match(/^A\d/) || upper.includes('FLOOR') || upper.includes('ELEVATION') || upper.includes('CEILING')) {
    return upper.includes('FLOOR') ? 'floor_plan' : 'architectural';
  }
  if (upper.match(/^E\d/) || upper.includes('ELECTRICAL') || upper.includes('PANEL') || upper.includes('LIGHTING')) return 'electrical';
  if (upper.match(/^M\d/) || upper.includes('MECHANICAL') || upper.includes('HVAC') || upper.includes('PLUMBING')) return 'mechanical';
  if (upper.includes('SCHEDULE') || upper.includes('ROOM FINISH') || upper.includes('DOOR SCHED')) return 'schedule';
  return 'other';
}

function getSheetTypeBadgeClass(sheetType) {
  const types = {
    floor_plan: 'badge-floor_plan',
    architectural: 'badge-architectural',
    electrical: 'badge-electrical',
    mechanical: 'badge-mechanical',
    schedule: 'badge-schedule'
  };
  return types[sheetType] || 'badge-other';
}

function formatSheetType(type) {
  const names = {
    floor_plan: 'Floor Plan',
    architectural: 'Architectural',
    electrical: 'Electrical',
    mechanical: 'Mechanical',
    schedule: 'Schedule',
    structural: 'Structural'
  };
  return names[type] || 'Other';
}

function resetPlanSelection() {
  const setPanel = document.getElementById('planSetPanel');
  if (setPanel) setPanel.style.display = 'none';
  const panel = document.getElementById('planSelectionPanel');
  if (panel) panel.style.display = 'none';
  const planList = document.getElementById('planList');
  if (planList) planList.innerHTML = '';
  const planSetList = document.getElementById('planSetList');
  if (planSetList) planSetList.innerHTML = '';
  const selectAll = document.getElementById('selectAllPlans');
  if (selectAll) selectAll.checked = false;
  const filter = document.getElementById('planTypeFilter');
  if (filter) filter.value = '';
  const loadBtn = document.getElementById('loadSheetsBtn');
  if (loadBtn) loadBtn.disabled = true;
  const backBtn = document.getElementById('backToPlanSetsBtn');
  if (backBtn) backBtn.style.display = 'none';
  allPlans = [];
  allPlanSets = [];
  selectedPlanSet = null;
  updateRunButtonCount();
}

function formatCachePill(data) {
  if (data.syncing) return '<span class="cache-pill syncing">syncing</span>';
  if (data.stale) return '<span class="cache-pill stale">stale · refreshing</span>';
  if (data.from_cache) return '<span class="cache-pill fresh">cached</span>';
  return '<span class="cache-pill fresh">live</span>';
}

function renderPlanSets(planSets) {
  const list = document.getElementById('planSetList');
  const badge = document.getElementById('planSetCount');
  if (!list) return;
  if (badge) badge.textContent = planSets.length + ' available';

  list.innerHTML = planSets.map(ps => {
    const fid = ps.folder_id;
    const selected = selectedPlanSet && selectedPlanSet.folder_id === fid;
    const sheets = ps.sheet_count != null
      ? ps.sheet_count + ' sheets'
      : 'use Load sheets for count';
    return '<label class="plan-set-card' + (selected ? ' selected' : '') + '" data-folder-id="' + fid + '">' +
      '<input type="radio" name="planSetPick" value="' + fid + '"' + (selected ? ' checked' : '') + '>' +
      '<div class="plan-set-card-body">' +
        '<div class="plan-set-name">' + escHtml(ps.name || 'Plan set ' + fid) + '</div>' +
        '<div class="plan-set-meta">' + sheets + ' · folder ' + fid + '</div>' +
      '</div>' +
    '</label>';
  }).join('');

  list.querySelectorAll('.plan-set-card').forEach(card => {
    card.addEventListener('click', () => {
      const fid = parseInt(card.dataset.folderId, 10);
      const ps = allPlanSets.find(s => s.folder_id === fid);
      if (ps) selectPlanSet(ps);
    });
  });
}

function selectPlanSet(ps) {
  selectedPlanSet = { folder_id: ps.folder_id, name: ps.name || ('Folder ' + ps.folder_id) };
  renderPlanSets(allPlanSets);
  const loadBtn = document.getElementById('loadSheetsBtn');
  if (loadBtn) loadBtn.disabled = false;
  const meta = document.getElementById('projectMeta');
  if (meta && selectedProject) {
    meta.textContent = 'Project ID: ' + selectedProject.id + ' · Plan set: ' + selectedPlanSet.name;
  }
}

async function fetchPlanSets(projectId, forceRefresh) {
  const setPanel = document.getElementById('planSetPanel');
  const planSetList = document.getElementById('planSetList');
  const sheetPanel = document.getElementById('planSelectionPanel');
  if (setPanel) setPanel.style.display = 'block';
  if (sheetPanel) sheetPanel.style.display = 'none';
  planSetList.innerHTML = '<p class="loading"><span class="spinner"></span> ' +
    (forceRefresh ? 'Syncing from StackCT…' : 'Loading plan sets…') + '</p>';

  const params = new URLSearchParams();
  if (forceRefresh) params.set('refresh', '1');
  else params.set('wait', '1');
  const url = '/api/projects/' + projectId + '/plan-sets?' + params.toString();
  const maxPolls = 40;
  let polls = 0;

  async function loadOnce() {
    const res = await fetch(url, { credentials: 'same-origin' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  }

  try {
    let data = await loadOnce();
    // Show cached plan sets immediately while a background refresh runs
    if (data.plan_sets && data.plan_sets.length && data.syncing) {
      allPlanSets = data.plan_sets;
      renderPlanSets(allPlanSets);
      const hint = document.getElementById('planSetHint');
      if (hint) {
        hint.innerHTML = 'Select an issue package (plan set), then load sheets.' + formatCachePill(data);
      }
    }
    while (
      data.syncing &&
      !(data.plan_sets && data.plan_sets.length) &&
      polls < maxPolls
    ) {
      planSetList.innerHTML = '<p class="loading"><span class="spinner"></span> Syncing plan sets from StackCT…</p>';
      await new Promise(r => setTimeout(r, 1500));
      polls++;
      data = await loadOnce();
    }

    if (data.error && !(data.plan_sets && data.plan_sets.length)) {
      planSetList.innerHTML = '<p class="error">' + escHtml(data.error) + '</p>' +
        planSyncErrorHint(data.error);
      return;
    }

    allPlanSets = data.plan_sets || [];
    if (!allPlanSets.length) {
      planSetList.innerHTML = '<p class="empty">No plan sets found. Use <strong>Sync from StackCT</strong> above to fetch the latest folders.</p>';
      return;
    }

    const hint = document.getElementById('planSetHint');
    if (hint) {
      hint.innerHTML = 'Select an issue package (plan set), then load sheets.' + formatCachePill(data);
    }

    const allHaveCounts = allPlanSets.every(s => s.sheet_count != null);
    projectSheetCounts[projectId] = {
      plan_set_count: allPlanSets.length,
      sheet_count: allHaveCounts
        ? allPlanSets.reduce((n, s) => n + (s.sheet_count || 0), 0)
        : null,
    };
    renderProjectList(allProjects);

    if (allPlanSets.length === 1) {
      selectPlanSet(allPlanSets[0]);
    }

    renderPlanSets(allPlanSets);
  } catch (e) {
    planSetList.innerHTML = '<p class="error">Failed to load plan sets: ' + escHtml(e.message) + '</p>';
  }
}

function planSyncErrorHint(err) {
  const s = String(err || '');
  if (/dns|network|reach stackct|internet|vpn/i.test(s)) {
    return '<p class="help-text" style="margin-top:8px;color:var(--text-tertiary)">Could not reach StackCT — check internet or VPN.</p>';
  }
  if (/login|credential/i.test(s)) {
    return '<p class="help-text" style="margin-top:8px;color:var(--text-tertiary)">StackCT login failed — check credentials in Settings.</p>';
  }
  return '';
}

let plansFetchAbort = null;
let plansFetchProjectId = null;

async function fetchPlans(projectId, folderId, forceRefresh) {
  if (folderId == null && selectedPlanSet) folderId = selectedPlanSet.folder_id;
  if (folderId == null) {
    alert('Select a plan set first.');
    return;
  }

  const planList = document.getElementById('planList');
  const sheetPanel = document.getElementById('planSelectionPanel');
  const setPanel = document.getElementById('planSetPanel');
  const previewBtn = document.getElementById('previewPlansBtn');
  if (sheetPanel) sheetPanel.style.display = 'block';
  if (setPanel) setPanel.style.display = 'none';
  const backBtn = document.getElementById('backToPlanSetsBtn');
  if (backBtn) backBtn.style.display = allPlanSets.length > 1 ? 'inline-block' : 'none';

  planList.innerHTML = '<p class="loading"><span class="spinner"></span> Loading sheets…</p>';
  if (previewBtn) previewBtn.disabled = true;

  if (plansFetchAbort) plansFetchAbort.abort();
  plansFetchAbort = new AbortController();
  plansFetchProjectId = projectId;
  const signal = plansFetchAbort.signal;

  const url = '/api/projects/' + projectId + '/plan-sets/' + folderId + '/plans' +
    (forceRefresh ? '?refresh=1' : '');
  const maxPolls = 40;
  let polls = 0;

  async function loadOnce() {
    const res = await fetch(url, { signal, credentials: 'same-origin' });
    if (res.status === 404) {
      return { error: 'Project not found', plans: [] };
    }
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  }

  try {
    let data = await loadOnce();
    if (!data) return;

    while (data.syncing && polls < maxPolls) {
      planList.innerHTML = '<p class="loading"><span class="spinner"></span> Syncing sheets from StackCT…</p>';
      await new Promise(r => setTimeout(r, 3000));
      polls++;
      data = await loadOnce();
    }

    if (data.error && !(data.plans && data.plans.length)) {
      let hint = '';
      hint = planSyncErrorHint(data.error);
      if (/syncing|in progress/i.test(data.error)) {
        hint += '<p class="help-text" style="margin-top:8px;color:var(--text-tertiary)">Sheets are still syncing — wait and try again.</p>';
      }
      if (selectedProject && selectedProject.id === projectId) {
        planList.innerHTML = '<p class="error">Error: ' + escHtml(data.error) + '</p>' + hint;
      }
      return;
    }

    if (selectedProject && selectedProject.id !== projectId) return;

    if (data.warning) {
      const meta = document.getElementById('projectMeta');
      if (meta) meta.textContent = data.warning;
    }

    allPlans = (data.plans || []).map(p => ({
      ...p,
      sheet_type: inferSheetType(p.sheet_name, p.sheet_type)
    }));

    if (!allPlans.length) {
      planList.innerHTML = '<p class="empty">No drawing pages found for this project.</p>';
      return;
    }

    renderPlans(allPlans);
    enrichPlanPreviews(projectId, folderId);
    const meta = document.getElementById('projectMeta');
    if (meta && selectedProject && selectedPlanSet) {
      meta.textContent = 'Project ID: ' + projectId + ' · ' + selectedPlanSet.name +
        ' · ' + allPlans.length + ' sheets' +
        (data.from_cache ? (data.stale ? ' · cached (refreshing)' : ' · cached') : ' · live');
    }
    const prev = projectSheetCounts[projectId];
    projectSheetCounts[projectId] = {
      plan_set_count: (prev && prev.plan_set_count) || allPlanSets.length || 1,
      sheet_count: allPlans.length,
    };
    renderProjectList(allProjects);
  } catch (e) {
    if (e.name === 'AbortError') return;
    planList.innerHTML = '<p class="error">Failed to load plans: ' + escHtml(e.message || 'network error') + '. Try Preview again in a few seconds.</p>';
  } finally {
    if (plansFetchProjectId === projectId) {
      updatePreviewButton();
      plansFetchAbort = null;
    }
  }
}

function stackctSheetUrl(projectId, pageId) {
  return 'https://go.stackct.com/app/#/Takeoff/' + projectId + '/Page/' + pageId + '/@0,0,0z';
}

function planPreviewCell(plan, projectId) {
  const stackUrl = plan.stackct_url || stackctSheetUrl(projectId, plan.page_id);
  if (plan.preview_url) {
    const title = escAttr(plan.sheet_name || 'Sheet');
    return '<button type="button" class="plan-thumb-btn" data-preview-url="' + escAttr(plan.preview_url) + '" data-title="' + title + '" title="View HD screenshot">' +
      '<img class="plan-thumb" src="' + escAttr(plan.preview_url) + '" alt="" loading="lazy">' +
    '</button>';
  }
  return '<a class="plan-open-stackct" href="' + escAttr(stackUrl) + '" target="_blank" rel="noopener noreferrer" title="Open drawing in StackCT">Open ↗</a>';
}

async function enrichPlanPreviews(projectId, folderId) {
  if (!selectedProject || selectedProject.id !== projectId) return;
  const pname = encodeURIComponent(selectedProject.name || '');
  try {
    const res = await fetch(
      '/api/projects/' + projectId + '/sheet-previews?folder_id=' + folderId + '&project_name=' + pname,
      { credentials: 'same-origin' }
    );
    if (!res.ok) return;
    const data = await res.json();
    const previews = data.previews || {};
    allPlans.forEach(p => {
      const info = previews[String(p.page_id)];
      if (!info) return;
      p.preview_url = info.preview_url || null;
      p.stackct_url = info.stackct_url;
    });
    if (selectedProject.id === projectId) renderPlans(allPlans);
  } catch (_) {
    /* preview enrichment is optional */
  }
}

function openSheetPreview(url, title) {
  let modal = document.getElementById('sheetPreviewModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'sheetPreviewModal';
    modal.className = 'sheet-preview-modal';
    modal.hidden = true;
    modal.innerHTML =
      '<div class="sheet-preview-dialog" role="dialog" aria-modal="true">' +
        '<button type="button" class="sheet-preview-close" aria-label="Close">×</button>' +
        '<p class="sheet-preview-title"></p>' +
        '<img class="sheet-preview-img" alt="">' +
      '</div>';
    modal.addEventListener('click', (e) => {
      if (e.target === modal || e.target.closest('.sheet-preview-close')) modal.hidden = true;
    });
    document.body.appendChild(modal);
  }
  modal.querySelector('.sheet-preview-title').textContent = title || '';
  modal.querySelector('.sheet-preview-img').src = url;
  modal.hidden = false;
}

function renderPlans(plans) {
  const planList = document.getElementById('planList');
  if (!planList) return;
  const filterEl = document.getElementById('planTypeFilter');
  const filterType = filterEl ? filterEl.value : '';
  const projectId = selectedProject ? selectedProject.id : null;

  const visible = filterType
    ? plans.filter(p => p.sheet_type === filterType)
    : plans;

  if (!visible.length) {
    planList.innerHTML = '<p class="empty">No plans match the selected filter</p>';
    updateRunButtonCount();
    return;
  }

  planList.innerHTML = visible.map(plan => {
    const badgeClass = getSheetTypeBadgeClass(plan.sheet_type);
    const typeName = formatSheetType(plan.sheet_type);
    const inputId = 'plan-' + plan.page_id;
    const preview = projectId ? planPreviewCell(plan, projectId) : '';
    const stackLink = projectId && plan.preview_url
      ? '<a class="plan-stackct-link" href="' + escAttr(plan.stackct_url || stackctSheetUrl(projectId, plan.page_id)) + '" target="_blank" rel="noopener noreferrer" title="Open in StackCT">StackCT ↗</a>'
      : '';
    return '<div class="plan-item" data-type="' + escAttr(plan.sheet_type) + '" data-page-id="' + plan.page_id + '">' +
      '<input type="checkbox" id="' + inputId + '" checked>' +
      (preview ? '<div class="plan-preview-col">' + preview + stackLink + '</div>' : '') +
      '<label for="' + inputId + '" class="plan-label">' +
        '<span class="sheet-name">' + escHtml(plan.sheet_name || 'Unnamed Sheet') + '</span>' +
      '</label>' +
      '<span class="sheet-type-badge ' + badgeClass + '">' + typeName + '</span>' +
    '</div>';
  }).join('');

  planList.querySelectorAll('input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', updateRunButtonCount);
  });
  planList.querySelectorAll('.plan-thumb-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      openSheetPreview(btn.dataset.previewUrl, btn.dataset.title);
    });
  });

  document.getElementById('selectAllPlans').checked = true;
  updateRunButtonCount();
}

function applyPlanTypeFilter() {
  renderPlans(allPlans);
  document.getElementById('selectAllPlans').checked = false;
}

function toggleAllPlans(checked) {
  document.querySelectorAll('.plan-item:not([style*="display: none"]) input[type="checkbox"]').forEach(cb => {
    cb.checked = checked;
  });
  updateRunButtonCount();
}

function selectNonePlans() {
  document.getElementById('selectAllPlans').checked = false;
  toggleAllPlans(false);
}

function updateRunButtonCount() {
  const checked = document.querySelectorAll('.plan-item input[type="checkbox"]:checked').length;
  const btn = document.getElementById('runSelectedBtn');
  if (!btn) return;
  btn.textContent = 'Run Selected Plans (' + checked + ') →';
  btn.disabled = checked === 0;
}

function getSelectedPageIds() {
  return Array.from(document.querySelectorAll('.plan-item input[type="checkbox"]:checked')).map(cb => {
    return parseInt(cb.closest('.plan-item').dataset.pageId, 10);
  });
}

function allPlansSelected() {
  const total = document.querySelectorAll('.plan-item input[type="checkbox"]').length;
  const checked = document.querySelectorAll('.plan-item input[type="checkbox"]:checked').length;
  return total > 0 && total === checked;
}

async function runSelectedPlans() {
  if (!selectedProject) {
    alert('Please select a project first.');
    return;
  }

  const pageIds = getSelectedPageIds();
  if (!pageIds.length) {
    alert('Please select at least one plan to run.');
    return;
  }

  const btn = document.getElementById('runSelectedBtn');
  btn.disabled = true;
  btn.textContent = 'Starting…';

  const body = {
    mode: 'specific',
    project_id: selectedProject.id,
    project_name: selectedProject.name
  };

  if (selectedPlanSet) {
    body.folder_id = selectedPlanSet.folder_id;
  }

  if (!allPlansSelected()) {
    body.page_ids = pageIds;
  }

  try {
    const res = await apiFetch('/api/run/stackct', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await res.json();

    if (data.error) {
      alert('Error: ' + data.error);
      return;
    }

    document.getElementById('planSelectionPanel').style.display = 'none';
    startPolling(data.job_id, selectedProject.name);
  } catch (e) {
    alert('Failed to start job: ' + e.message);
  } finally {
    updateRunButtonCount();
  }
}

function bindPlanSelectionEvents() {
  const projectList = document.getElementById('projectList');
  if (projectList) {
    projectList.addEventListener('click', e => {
      const item = e.target.closest('.project-item');
      if (!item) return;
      onProjectSelect(parseInt(item.dataset.id, 10), item.dataset.name);
    });
  }

  const previewBtn = document.getElementById('previewPlansBtn');
  if (previewBtn) {
    previewBtn.addEventListener('click', async () => {
      if (!selectedProject) return;
      await fetchPlanSets(selectedProject.id, false);
    });
  }

  const refreshPlansBtn = document.getElementById('refreshPlansBtn');
  if (refreshPlansBtn) {
    refreshPlansBtn.addEventListener('click', async () => {
      if (!selectedProject) return;
      const proj = selectedProject;
      resetPlanSelection();
      selectedProject = proj;
      document.getElementById('projectMeta').textContent = 'Project ID: ' + proj.id;
      await fetchPlanSets(proj.id, true);
    });
  }

  const loadSheetsBtn = document.getElementById('loadSheetsBtn');
  if (loadSheetsBtn) {
    loadSheetsBtn.addEventListener('click', async () => {
      if (!selectedProject || !selectedPlanSet) return;
      await fetchPlans(selectedProject.id, selectedPlanSet.folder_id, false);
    });
  }

  const backToPlanSetsBtn = document.getElementById('backToPlanSetsBtn');
  if (backToPlanSetsBtn) {
    backToPlanSetsBtn.addEventListener('click', () => {
      if (!selectedProject) return;
      document.getElementById('planSelectionPanel').style.display = 'none';
      document.getElementById('planSetPanel').style.display = 'block';
      backToPlanSetsBtn.style.display = 'none';
      renderPlanSets(allPlanSets);
    });
  }

  const selectAll = document.getElementById('selectAllPlans');
  if (selectAll) selectAll.addEventListener('change', e => toggleAllPlans(e.target.checked));

  const selectNoneBtn = document.getElementById('selectNoneBtn');
  if (selectNoneBtn) selectNoneBtn.addEventListener('click', selectNonePlans);

  const typeFilter = document.getElementById('planTypeFilter');
  if (typeFilter) typeFilter.addEventListener('change', applyPlanTypeFilter);

  const runBtn = document.getElementById('runSelectedBtn');
  if (runBtn) runBtn.addEventListener('click', runSelectedPlans);

  const search = document.getElementById('projectSearch');
  if (search) search.addEventListener('input', e => filterProjects(e.target.value));
}

// ── Utilities ──────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function escAttr(s) {
  return escHtml(s);
}

function renderTakeoffSummaryTable(rows) {
  if (!rows.length) {
    return '<p class="empty">No consolidated takeoff summary for this run.</p>';
  }
  const headers = ['item', 'quantity', 'unit', 'source_sheets', 'line_count'];
  const labels = { item: 'Item', quantity: 'Qty', unit: 'Unit', source_sheets: 'Sheets', line_count: 'Lines' };
  let html = '<div class="takeoff-summary-wrap"><table class="data-table takeoff-summary-table"><thead><tr>';
  headers.forEach(h => { html += '<th>' + escHtml(labels[h] || h) + '</th>'; });
  html += '</tr></thead><tbody>';
  rows.forEach(row => {
    html += '<tr>';
    headers.forEach(h => {
      const cls = h === 'quantity' ? ' class="num"' : '';
      html += '<td' + cls + '>' + escHtml(row[h] != null ? String(row[h]) : '') + '</td>';
    });
    html += '</tr>';
  });
  html += '</tbody></table>';
  html += '<p class="preview-cap-note">Consolidated across all sheets — matches StackCT summary format. See Calculations tab for per-sheet audit.</p></div>';
  return html;
}

function formatSummaryHtml(text) {
  const lines = String(text).split('\n');
  let html = '<div class="summary-view">';
  lines.forEach(line => {
    const t = line.trim();
    if (!t) return;
    if (t.endsWith(':') && t.length < 80 && !t.includes('=')) {
      html += '<div class="summary-heading">' + escHtml(t) + '</div>';
    } else if (t.startsWith('===') || t.startsWith('---')) {
      html += '<div class="summary-heading">' + escHtml(t.replace(/[=|-]+/g, ' ').trim() || t) + '</div>';
    } else {
      html += '<div class="summary-line">' + escHtml(line) + '</div>';
    }
  });
  html += '</div>';
  return html;
}

function bindReportsAndMonitorEvents() {
  const search = document.getElementById('reportsSearch');
  if (search) search.addEventListener('input', e => filterReports(e.target.value));

  const refresh = document.getElementById('reportsRefreshBtn');
  if (refresh) refresh.addEventListener('click', () => loadReports());

  const cancelBtn = document.getElementById('cancelJobBtn');
  if (cancelBtn) cancelBtn.addEventListener('click', cancelJob);
}

// ── Init ───────────────────────────────────────────────────────────────────
loadProjects();
bindPlanSelectionEvents();
bindReportsAndMonitorEvents();
bindPdfEvents();
startActiveJobPolling();
