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
let allProjects = [];
let allPlans = [];
let selectedProject = null;
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
    const res = await fetch(url);
    const data = await res.json();

    if (data.error && !data.projects?.length) {
      listEl.innerHTML = '<p class="empty">Could not load projects</p>';
      if (status) status.textContent = 'Could not load';
      return;
    }

    allProjects = data.projects || [];
    projectsLoaded = true;
    renderProjectList(allProjects);

    if (status) {
      const when = data.fetched_at ? new Date(data.fetched_at).toLocaleString() : '';
      const tag = data.from_cache ? 'Cached' + (data.stale ? ' (stale)' : '') : 'Live';
      status.textContent = tag + ' · ' + allProjects.length + ' projects' + (when ? ' · ' + when : '');
    }
  } catch (e) {
    listEl.innerHTML = '<p class="empty">Network error loading projects</p>';
    if (status) status.textContent = 'Network error';
  } finally {
    if (refreshBtn) refreshBtn.disabled = false;
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
    const count = projectSheetCounts[p.id];
    const countLabel = count != null ? count + ' sheet' + (count !== 1 ? 's' : '') : '— sheets';
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

function onProjectSelect(projectId, projectName) {
  resetPlanSelection();
  selectedProject = { id: projectId, name: projectName };
  document.getElementById('projectMeta').textContent = 'Project ID: ' + projectId;
  renderProjectList(allProjects);
  updatePreviewButton();
}

function updatePreviewButton() {
  const btn = document.getElementById('previewPlansBtn');
  if (btn) btn.disabled = !selectedProject;
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
    const res = await fetch('/api/run/stackct', {
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
    const res = await fetch('/api/pdf/upload', { method: 'POST', body: form });
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
    const res = await fetch('/api/pdf/run', {
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
    const res = await fetch('/api/status/' + jobId);
    const job = await res.json();
    if (job.error) return;

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

  if (cs.name) {
    document.getElementById('monitorCurrentSheet').innerHTML =
      'Currently analyzing: <strong>' + escHtml(cs.name) + '</strong>';
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

  if (job.status === 'done') {
    setTimeout(() => {
      navigateTo('reports');
      loadReports();
    }, 2000);
  }
}

async function cancelJob() {
  if (!currentJobId) return;
  if (!confirm('Cancel this job?')) return;

  try {
    const res = await fetch('/api/cancel/' + currentJobId, { method: 'POST' });
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
    const res = await fetch('/api/reports');
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

  grid.querySelectorAll('.btn-preview').forEach(btn => {
    btn.addEventListener('click', () => togglePreview(btn.dataset.folder));
  });
  grid.querySelectorAll('.btn-download').forEach(btn => {
    btn.addEventListener('click', () => downloadReportFile(btn.dataset.folder, btn.dataset.file));
  });
  grid.querySelectorAll('.preview-tabs .tab').forEach(tab => {
    tab.addEventListener('click', () => switchPreviewTab(tab.dataset.folder, tab.dataset.tab));
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
  const isOpen = openPreviewFolder === folder;
  const activeTab = openPreviewTab[folder] || 'summary';

  const files = r.files || {};
  const dl = (fileKey, label) => {
    const f = files[fileKey];
    if (!f) return '';
    return '<button type="button" class="btn-download" data-folder="' + escHtml(folder) + '" data-file="' + escHtml(f.filename) + '">' + label + '</button>';
  };

  return '<div class="report-card' + (isOpen ? ' expanded' : '') + '" data-folder="' + escHtml(folder) + '">' +
    '<div class="card-header">' +
      '<span class="project-name">' + escHtml(r.project_name) + '</span>' +
      '<span class="report-date">' + escHtml(date) + '</span>' +
    '</div>' +
    '<div class="card-meta">' +
      '<span>' + sheets + '</span>' +
      (raw ? '<span>·</span><span>' + raw + '</span>' : '') +
      (calc ? '<span>·</span><span>' + calc + '</span>' : '') +
      (cost ? '<span>·</span><span class="cost">' + cost + '</span>' : '') +
    '</div>' +
    '<div class="card-actions">' +
      '<button type="button" class="btn-preview' + (isOpen ? ' active' : '') + '" data-folder="' + escHtml(folder) + '">Preview</button>' +
      dl('calculated_csv', 'Calculations') +
      dl('raw_csv', 'Raw CSV') +
      dl('json', '{ } JSON') +
      dl('summary', 'Summary TXT') +
    '</div>' +
    (isOpen ? renderPreviewPanel(folder, activeTab) : '') +
  '</div>';
}

function renderPreviewPanel(folder, activeTab) {
  return '<div class="preview-panel" id="preview-panel-' + escHtml(folder) + '">' +
    '<div class="preview-tabs">' +
      ['summary', 'calculations', 'raw', 'json'].map(t => {
        const labels = { summary: 'Summary', calculations: 'Calculations', raw: 'Raw Items', json: 'JSON' };
        return '<button type="button" class="tab' + (t === activeTab ? ' active' : '') + '" data-folder="' + escHtml(folder) + '" data-tab="' + t + '">' + labels[t] + '</button>';
      }).join('') +
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
  if (!openPreviewTab[folder]) openPreviewTab[folder] = 'summary';
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
    if (tab === 'summary') {
      const res = await fetch('/api/reports/' + enc + '/preview/summary.txt');
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
      const res = await fetch('/api/reports/' + enc + '/preview/takeoff.json');
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
  const res = await fetch('/api/reports/' + encFolder + '/preview/' + filename);
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
  const panel = document.getElementById('planSelectionPanel');
  if (panel) panel.style.display = 'none';
  const planList = document.getElementById('planList');
  if (planList) planList.innerHTML = '';
  const selectAll = document.getElementById('selectAllPlans');
  if (selectAll) selectAll.checked = false;
  const filter = document.getElementById('planTypeFilter');
  if (filter) filter.value = '';
  allPlans = [];
  updateRunButtonCount();
}

async function fetchPlans(projectId) {
  const planList = document.getElementById('planList');
  planList.innerHTML = '<p class="loading"><span class="spinner"></span> Loading plans…</p>';

  try {
    const res = await fetch('/api/projects/' + projectId + '/plans');
    if (res.status === 404) {
      planList.innerHTML = '<p class="error">Project not found</p>';
      return;
    }
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();

    if (data.error) {
      planList.innerHTML = '<p class="error">Error: ' + escHtml(data.error) + '</p>';
      return;
    }

    allPlans = (data.plans || []).map(p => ({
      ...p,
      sheet_type: inferSheetType(p.sheet_name, p.sheet_type)
    }));

    projectSheetCounts[projectId] = allPlans.length;
    renderProjectList(allProjects);

    if (!allPlans.length) {
      planList.innerHTML = '<p class="empty">No drawing pages found for this project.</p>';
      return;
    }

    renderPlans(allPlans);
  } catch (e) {
    planList.innerHTML = '<p class="error">Failed to load plans. Check connection and try Preview again.</p>';
  }
}

function renderPlans(plans) {
  const planList = document.getElementById('planList');
  const filterType = document.getElementById('planTypeFilter').value;

  const visible = filterType
    ? plans.filter(p => p.sheet_type === filterType)
    : plans;

  if (!visible.length) {
    planList.innerHTML = '<p class="empty">No plans match the selected filter</p>';
    updateRunButtonCount();
    return;
  }

  planList.innerHTML = visible.map((plan, idx) => {
    const badgeClass = getSheetTypeBadgeClass(plan.sheet_type);
    const typeName = formatSheetType(plan.sheet_type);
    return '<div class="plan-item" data-type="' + escAttr(plan.sheet_type) + '" data-page-id="' + plan.page_id + '">' +
      '<input type="checkbox" id="plan-' + idx + '" checked>' +
      '<label for="plan-' + idx + '" class="plan-label">' +
        '<span class="sheet-name">' + escHtml(plan.sheet_name || 'Unnamed Sheet') + '</span>' +
      '</label>' +
      '<span class="sheet-type-badge ' + badgeClass + '">' + typeName + '</span>' +
    '</div>';
  }).join('');

  planList.querySelectorAll('input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', updateRunButtonCount);
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

  if (!allPlansSelected()) {
    body.page_ids = pageIds;
  }

  try {
    const res = await fetch('/api/run/stackct', {
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
      document.getElementById('planSelectionPanel').style.display = 'block';
      await fetchPlans(selectedProject.id);
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
