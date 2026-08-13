/**
 * Behavioural harness for pollJobMonitor (see tests/test_deployment_contract.py).
 *
 * app.js is browser code with no module system, so it is evaluated inside a
 * vm context whose globals are hand-stubbed. Only what app.js actually touches
 * is stubbed — deliberately thin, so this harness fails loudly if the file
 * grows a new environmental dependency rather than silently papering over it.
 *
 * Usage:  node poll_job_monitor_harness.js <app.js path> '<scenario JSON>'
 *
 * Scenario: {"responses": [{"status": 404}, ...]} — one entry consumed per
 * poll. `null` means the fetch itself rejects (offline / server down).
 *
 * Prints a JSON verdict: what the user would see, and whether polling stopped.
 */
const fs = require('fs');
const vm = require('vm');

const [appPath, scenarioJson] = process.argv.slice(2);
const scenario = JSON.parse(scenarioJson);

// ── DOM stub ────────────────────────────────────────────────────────────────
const elements = new Map();

function makeEl(id) {
  const node = {
    id,
    style: {},
    dataset: {},
    className: '',
    textContent: '',
    innerHTML: '',
    value: '',
    files: [],
    children: [],
    parentNode: null,
    nextSibling: null,
    classList: { add() {}, remove() {}, contains() { return false; } },
    appendChild(child) { this.children.push(child); child.parentNode = this; },
    insertBefore(child) { this.children.push(child); child.parentNode = this; },
    addEventListener() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
    click() {},
  };
  return node;
}

// Elements the code creates itself, tracked so "did it build a banner" is
// observable. createElement() returns a node with no id; the code assigns one
// afterwards, so the lookup has to search by the id the code set.
const created = [];

function findCreated(id) {
  return created.find((node) => node.id === id) || null;
}

function getEl(id) {
  const own = findCreated(id);
  if (own) return own;
  if (!elements.has(id)) {
    // A node the page never declared and the code has not built yet.
    if (id === 'monitorPollError') return null;
    elements.set(id, makeEl(id));
  }
  return elements.get(id);
}

// monitorStatus needs a parent for insertBefore to reach.
const container = makeEl('container');

const documentStub = {
  getElementById: getEl,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: (tag) => {
    const node = makeEl('');
    node.tagName = tag.toUpperCase();
    created.push(node);
    return node;
  },
  body: makeEl('body'),
  addEventListener() {},
};

// ── fetch stub: replays the scenario, one response per STATUS poll ──────────
//
// Scoped to /api/status/ on purpose. app.js runs its own bootstrap on load
// (project list, active jobs, sheet counts); letting those consume scenario
// entries would silently shift the sequence under test and make the harness
// depend on unrelated startup traffic.
let pollCount = 0;
const requested = [];

async function fetchStub(url) {
  requested.push(url);

  if (!String(url).startsWith('/api/status/')) {
    return { ok: true, status: 200, json: async () => ({}) };
  }

  const spec = pollCount < scenario.responses.length
    ? scenario.responses[pollCount]
    : scenario.responses[scenario.responses.length - 1];
  pollCount += 1;
  if (spec === null) {
    throw new Error('simulated network failure');
  }
  return {
    ok: spec.status >= 200 && spec.status < 300,
    status: spec.status,
    json: async () => spec.body ?? { status: 'running', progress: 0 },
  };
}

// ── timers: recorded, never run. "Did polling stop" is read straight off the
//    module's own monitorPollInterval binding after the fact. ───────────────
const ctx = {
  document: documentStub,
  window: {
    location: { href: 'http://localhost:5050/', search: '' },
    history: { replaceState() {} },
    addEventListener() {},
  },
  fetch: fetchStub,
  console,
  setInterval: () => 1,
  clearInterval: () => {},
  setTimeout: () => 1,
  clearTimeout: () => {},
  URL,
  URLSearchParams,
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  navigator: { clipboard: {} },
  alert() {},
  Date,
  JSON,
  Math,
  encodeURIComponent,
  decodeURIComponent,
};
ctx.globalThis = ctx;

vm.createContext(ctx);
vm.runInContext(fs.readFileSync(appPath, 'utf8'), ctx);

// The banner is inserted next to monitorStatus, so give that node a parent.
const statusEl = getEl('monitorStatus');
statusEl.parentNode = container;

// Stand in for resumeJobMonitor() having armed the interval. Top-level `let`
// bindings live in the context's shared lexical scope, so this assigns the
// module's own variable — which means stopJobPolling() nulling it is a direct,
// unfaked observation that polling really stopped.
vm.runInContext('monitorPollInterval = 1;', ctx);
const pollingLive = () => vm.runInContext('monitorPollInterval', ctx) !== null;

(async () => {
  // Simulate the interval firing: one call per scenario entry, stopping when
  // the code stops itself — exactly what the browser would do.
  for (let i = 0; i < scenario.responses.length; i += 1) {
    if (!pollingLive()) break;
    await ctx.pollJobMonitor('job-under-test');
  }

  const banner = findCreated('monitorPollError');
  process.stdout.write(JSON.stringify({
    polls_made: pollCount,
    polling_still_live: pollingLive(),
    banner_shown: Boolean(banner && banner.style.display !== 'none' && banner.textContent),
    banner_text: banner ? banner.textContent : '',
    status_text: statusEl.textContent,
    requested,
  }));
})();
