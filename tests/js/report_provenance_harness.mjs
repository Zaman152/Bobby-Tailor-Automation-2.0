/**
 * Behavioural harness for report-provenance.js (see tests/test_report_honesty.py).
 *
 * The module is a real ES module with no browser dependencies, so unlike the
 * pollJobMonitor harness this one needs no DOM stub at all — it imports the
 * shipped file and asks it the same questions the worksheet asks.
 *
 * Usage:  node report_provenance_harness.mjs <module path> '<input JSON>'
 *
 * Input: {"rows": [...], "coverage": {...}|null}
 *   `rows` is a takeoff_summary array (the real saved Crow run is fed in
 *   whole by the python test).
 *
 * Prints a JSON verdict describing what a reader would end up seeing.
 */
import { pathToFileURL } from 'url';
import path from 'path';

const [modulePath, inputJson] = process.argv.slice(2);
const input = JSON.parse(inputJson);
const rows = input.rows || [];

const m = await import(pathToFileURL(path.resolve(modulePath)).href);

const statuses = rows.map((r) => {
  const st = m.rowStatus(r);
  return {
    item: r.item,
    provenance: r.provenance ?? null,
    quantity_fmt: r.quantity_fmt ?? null,
    cls: st.cls,
    label: st.label,
    icon: st.icon,
    third_state: st.thirdState,
    // What the quantity cell actually renders for this row.
    cell: m.rowQtyNum(r) === null ? st.blankText : String(r.quantity_fmt ?? r.quantity),
    needs_verification: m.rowNeedsVerification(r),
    confirmable: m.rowIsConfirmableEstimate(r),
    route: r.quantity_route ?? null,
    route_label: m.routeLabel(r.quantity_route)?.label ?? null,
    route_reproducible: m.routeLabel(r.quantity_route)?.reproducible ?? null,
  };
});

const byLabel = {};
for (const s of statuses) {
  const key = `${s.provenance} -> ${s.label}`;
  byLabel[key] = (byLabel[key] || 0) + 1;
}

const facts = m.coverageFacts(input.coverage ?? null, rows);

process.stdout.write(JSON.stringify({
  total: rows.length,
  by_label: byLabel,
  third_state_count: statuses.filter((s) => s.third_state).length,
  needs_verification_count: statuses.filter((s) => s.needs_verification).length,
  confirmable_count: statuses.filter((s) => s.confirmable).length,
  cells_saying_enter_value: statuses.filter((s) => s.cell === 'enter value')
                                    .map((s) => s.item),
  not_measured_cells: [...new Set(statuses.filter((s) => s.provenance === 'NOT MEASURED')
                                          .map((s) => s.cell))],
  has_provenance: m.hasProvenance(rows),
  has_routes: m.hasQuantityRoutes(rows),
  reproducibility_rows: m.reproducibilityRows(rows).map((r) => r.item),
  coverage: facts,
  statuses,
}));
