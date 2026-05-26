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
    return '<div class="project-item' + (isSelected ? ' selected' : '') + '" data-id="' + p.id + '" data-name="' + escHtml(p.name) + '">' +
      '<input type="radio" name="projectPick" class="project-radio"' + (isSelected ? ' checked' : '') + ' tabindex="-1">' +
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

// ── Init ───────────────────────────────────────────────────────────────────
loadProjects();
bindPlanSelectionEvents();
startActiveJobPolling();
