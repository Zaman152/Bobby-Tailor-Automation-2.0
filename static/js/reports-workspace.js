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

const TAB_IDS = ['summary', 'calculations', 'raw', 'json'];

/**
 * Open the report preview workspace
 * @param {string} runFolder - Report folder ID
 */
export async function openReportWorkspace(runFolder) {
  currentRun = runFolder;
  currentTab = 'summary';
  
  // Parse URL params if present
  const params = new URLSearchParams(window.location.search);
  if (params.get('tab') && TAB_IDS.includes(params.get('tab'))) {
    currentTab = params.get('tab');
  }
  
  // Fetch report metadata
  const response = await fetch(`/api/reports/${runFolder}`);
  if (!response.ok) {
    window.ui.toast.error('Failed to load report');
    return;
  }
  const report = await response.json();
  
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
            <button type="button" class="tab-btn ${currentTab === 'summary' ? 'active' : ''}" 
                    data-tab="summary" role="tab" aria-selected="${currentTab === 'summary'}">
              Summary
            </button>
            <button type="button" class="tab-btn ${currentTab === 'calculations' ? 'active' : ''}" 
                    data-tab="calculations" role="tab" aria-selected="${currentTab === 'calculations'}">
              Calculations
            </button>
            <button type="button" class="tab-btn ${currentTab === 'raw' ? 'active' : ''}" 
                    data-tab="raw" role="tab" aria-selected="${currentTab === 'raw'}">
              Raw Data
            </button>
            <button type="button" class="tab-btn ${currentTab === 'json' ? 'active' : ''}" 
                    data-tab="json" role="tab" aria-selected="${currentTab === 'json'}">
              JSON
            </button>
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
    container.innerHTML = `<div class="tab-error">Failed to load ${tabId} content</div>`;
    console.error(`Tab load error (${tabId}):`, error);
  }
}

async function loadSummaryTab(container) {
  const response = await fetch(`/api/reports/${currentRun}/preview/summary`);
  if (!response.ok) throw new Error('Failed to load summary');
  
  const html = await response.text();
  container.innerHTML = `<div class="summary-view">${html}</div>`;
}

async function loadCalculationsTab(container) {
  const response = await fetch(`/api/reports/${currentRun}/preview/calculations`);
  if (!response.ok) throw new Error('Failed to load calculations');
  
  const data = await response.json();
  
  // Cap banner if needed
  if (data.capped) {
    const banner = document.createElement('div');
    banner.className = 'cap-banner';
    banner.innerHTML = `
      Showing ${data.rows.length} of ${data.total || 'many'} rows. 
      <a href="/api/reports/${currentRun}/download/calculations.csv" class="download-full-link">Download full CSV</a> to analyze all rows.
    `;
    container.appendChild(banner);
  }
  
  // Enhanced grid with sort/filter/export
  const gridContainer = document.createElement('div');
  container.appendChild(gridContainer);
  
  if (window.dataGrid) {
    window.dataGrid.mountGrid(gridContainer, {
      headers: data.headers,
      rows: data.rows,
      sortable: true,
      onExport: (filtered) => {
        window.ui.toast.success(`Exported ${filtered.length} filtered rows`);
      }
    });
  } else {
    // Fallback: basic table
    gridContainer.innerHTML = renderDataTable(data.headers, data.rows);
  }
}

async function loadRawTab(container) {
  const response = await fetch(`/api/reports/${currentRun}/preview/raw`);
  if (!response.ok) throw new Error('Failed to load raw data');
  
  const data = await response.json();
  container.innerHTML = renderDataTable(data.headers, data.rows);
}

async function loadJsonTab(container) {
  const response = await fetch(`/api/reports/${currentRun}/preview/json`);
  if (!response.ok) throw new Error('Failed to load JSON');
  
  const json = await response.json();
  container.innerHTML = `
    <div class="json-search">
      <input type="text" placeholder="Search JSON..." class="json-search-input" />
    </div>
    <pre class="json-view">${JSON.stringify(json, null, 2)}</pre>
  `;
}

function renderDataTable(headers, rows) {
  return `
    <div class="data-table-container">
      <table class="data-table">
        <thead>
          <tr>
            ${headers.map(h => `<th>${h}</th>`).join('')}
          </tr>
        </thead>
        <tbody>
          ${rows.map(row => `
            <tr>
              ${row.map(cell => `<td>${cell !== null && cell !== undefined ? cell : ''}</td>`).join('')}
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function handleWorkspaceKeyboard(e) {
  if (e.key === 'Escape') {
    e.preventDefault();
    closeReportWorkspace();
  }
  
  if (e.key >= '1' && e.key <= '4') {
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
  const endpoint = type === 'summary' ? 'summary.txt' : 
                   type === 'json' ? 'report.json' :
                   type === 'calculations' ? 'calculations.csv' : 'raw_items.csv';
  
  const link = document.createElement('a');
  link.href = `/api/reports/${runFolder}/download/${endpoint}`;
  link.download = `${runFolder}_${type}.${type === 'summary' ? 'txt' : type === 'json' ? 'json' : 'csv'}`;
  link.click();
}

function formatDate(timestamp) {
  return new Date(timestamp).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  });
}

function renderCachePill(report) {
  if (report.from_cache) {
    return '<span class="pill pill-success">Cached</span>';
  }
  return '';
}

// Global exposure
window.reportWorkspace = { openReportWorkspace, closeReportWorkspace, switchTab };
