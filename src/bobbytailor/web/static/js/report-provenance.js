/**
 * Row provenance for the browser — the screen's half of the honesty contract.
 *
 * The pipeline records, for every published row, WHERE its number came from
 * (`provenance`, src/bobbytailor/pipeline/provenance.py) and HOW it was
 * produced (`quantity_route`, plan 28-06). `takeoff_summary.csv` carries both.
 * Until this module existed the browser worksheet carried neither: it
 * classified rows from `source`/`needs_review`/`quantity` alone, which
 * collapsed the pipeline's four-value vocabulary into two states and rendered
 * every one of the Crow run's 31 NOT MEASURED rows as "Needs review · enter
 * value" — i.e. as a value the estimator had forgotten to type.
 *
 * That is the exact inversion the phase-23 work exists to prevent. A row the
 * app could not measure and a row the app measured but wants confirmed are
 * different claims about the drawing, and only one of them is the estimator's
 * to resolve by typing.
 *
 * This file is deliberately PURE and dependency-free — no DOM, no fetch, no
 * imports. reports-workspace.js imports it for rendering; tests/js runs it
 * under node against the real saved Crow run. A classification rule that can
 * only be exercised through a 1,400-line DOM module does not get tested, and
 * this one is load-bearing for what a bidder believes.
 */

// The pipeline's item statuses, verbatim from pipeline/coverage.py. Copied
// rather than imported because this is browser code; test_report_honesty.py
// asserts the two copies have not drifted.
export const PROV_MEASURED = 'MEASURED';
export const PROV_HUMAN_INPUT = 'HUMAN INPUT';
export const PROV_NEEDS_REVIEW = 'NEEDS REVIEW';
export const PROV_NOT_MEASURED = 'NOT MEASURED';
export const PROV_NOT_APPLICABLE = 'NOT APPLICABLE';
export const PROV_STANDARD = 'STANDARD ITEM';

// Quantity routes, verbatim from pipeline/aggregator.py (28-06).
export const ROUTE_MEASURED = 'measured_from_drawing';
export const ROUTE_PRINTED_SCHEDULE = 'printed_schedule';
export const ROUTE_SHEET_READING = 'sheet_reading';

/** Normalised provenance of a row, or '' when the row does not carry one. */
export function rowProvenance(row) {
  return String((row && row.provenance) || '').trim().toUpperCase();
}

/** Numeric quantity, or null when absent / non-numeric. Mirrors verify.py. */
export function rowQtyNum(row) {
  const q = row ? row.quantity : null;
  if (q === null || q === undefined || q === '—' || q === '') return null;
  const n = parseFloat(String(q).replace(/,/g, ''));
  return Number.isFinite(n) ? n : null;
}

/**
 * Classify one row for display.
 *
 * Returns `{ cls, label, icon, title, blankText, thirdState }`.
 * `blankText` is what the quantity cell says when there is no number —
 * NEVER "enter value" for a row the app had no measurement path for.
 *
 * Order is record-first, the same precedence provenance_of_row uses: the
 * pipeline's recorded verdict wins over anything inferred from the value.
 *
 * A row with NO `provenance` key falls through to the pre-28 classification,
 * unchanged. That is the same empty-contract the reporter's coverage and
 * reproducibility sections keep: a report written before this vocabulary
 * existed must render exactly as it did, because "this row has no measurement
 * path" is a claim only a run that recorded one is entitled to make.
 */
export function rowStatus(row) {
  const r = row || {};
  const prov = rowProvenance(r);
  const src = String(r.source || '').toLowerCase();
  const qtyMissing = rowQtyNum(r) === null;

  if (prov) {
    // A human's own number always wins the badge — they typed it, whatever
    // the run recorded before they did.
    if (src === 'user_verified' || prov === PROV_HUMAN_INPUT) {
      return {
        cls: 'verified', label: 'Verified', icon: '✓', thirdState: false,
        title: 'a human entered or confirmed this number',
        blankText: 'enter value',
      };
    }

    if (prov === PROV_NOT_MEASURED) {
      return {
        cls: 'notmeasured', label: 'Not measured', icon: '∅', thirdState: true,
        title: 'the app has NO measurement path for this item on these ' +
               'drawings. The blank is a blank, not a zero, and not a value ' +
               'anyone forgot to type.',
        blankText: 'no measurement path',
      };
    }

    if (prov === PROV_NOT_APPLICABLE) {
      return {
        cls: 'notapplicable', label: 'Not applicable', icon: '–',
        thirdState: true,
        title: 'the drawing set genuinely contains none of these',
        blankText: 'none in this set',
      };
    }

    if (prov === PROV_STANDARD) {
      return {
        cls: 'standard', label: 'Standard item', icon: '≡', thirdState: false,
        title: 'an estimating convention the app injects. Nobody measured it ' +
               'off a drawing and nobody supplied it.',
        blankText: 'enter value',
      };
    }

    if (prov === PROV_NEEDS_REVIEW || r.needs_review) {
      return {
        cls: 'review', label: 'Needs review', icon: '!', thirdState: false,
        title: 'measured, but flagged — confirm it before you bid it',
        blankText: 'enter value',
      };
    }

    if (prov === PROV_MEASURED) {
      // `measured_verified` / `measured_auto` are the Scale & Verify module's
      // own sources and keep their existing badges. Everything else measured
      // keeps the green ✓ it has always had — these are the rows the engine
      // earned, and the badge on them is correct (see DAY1-SUMMARY §5). Only
      // the WORD changes: "Confirmed" claimed a human had signed off on a
      // number no human had seen.
      if (src === 'measured_verified') {
        return {
          cls: 'measured', label: 'Measured', icon: '▣', thirdState: false,
          title: 'measured against a human-verified drawing scale',
          blankText: 'enter value',
        };
      }
      if (!qtyMissing && (r.auto_verified || src === 'measured_auto')) {
        return {
          cls: 'auto', label: 'Auto', icon: '⚡', thirdState: false,
          title: 'measured at a cleanly-read scale and auto-accepted',
          blankText: 'enter value',
        };
      }
      return {
        cls: 'ok', label: 'Measured', icon: '✓', thirdState: false,
        title: 'the app measured this off the drawings (MEASURED). No human ' +
               'has confirmed it.',
        blankText: 'enter value',
      };
    }
  }

  // ── Pre-28 report: classify exactly as this worksheet always has. ─────────
  if (src === 'user_verified')
    return { cls: 'verified', label: 'Verified', icon: '✓', thirdState: false,
             title: 'a human entered or confirmed this number',
             blankText: 'enter value' };
  if (!qtyMissing && !r.needs_review && (r.auto_verified || src === 'measured_auto'))
    return { cls: 'auto', label: 'Auto', icon: '⚡', thirdState: false,
             title: 'measured at a cleanly-read scale and auto-accepted',
             blankText: 'enter value' };
  if (src === 'measured_verified')
    return { cls: 'measured', label: 'Measured', icon: '▣', thirdState: false,
             title: 'measured against a human-verified drawing scale',
             blankText: 'enter value' };
  if (r.needs_review || qtyMissing)
    return { cls: 'review', label: 'Needs review', icon: '!', thirdState: false,
             title: 'flagged, or carrying no quantity',
             blankText: 'enter value' };
  return { cls: 'ok', label: 'Confirmed', icon: '✓', thirdState: false,
           title: '', blankText: 'enter value' };
}

/** True when the run itself said it had no measurement path for this row. */
export function rowIsNotMeasured(row) {
  return rowStatus(row).thirdState;
}

/**
 * A line the estimator can still act on: flagged, or missing a number the app
 * believes it should have had.
 *
 * NOT MEASURED and NOT APPLICABLE rows are excluded ON PURPOSE. They are not
 * work items in the "you forgot to type this" sense, and counting them as such
 * is what produced "42 still need review" on a run whose own ledger said 11.
 */
export function rowNeedsVerification(row) {
  return rowStatus(row).cls === 'review';
}

/** Rows a bulk confirm may touch: flagged AND already carrying a number. */
export function rowIsConfirmableEstimate(row) {
  return rowNeedsVerification(row) && rowQtyNum(row) !== null;
}

const _ROUTE_LABELS = {
  [ROUTE_MEASURED]: {
    label: 'measured off drawing',
    title: 'measured off the drawing’s own geometry — a repeat run reproduces it',
    reproducible: true,
  },
  [ROUTE_PRINTED_SCHEDULE]: {
    label: 'printed schedule',
    title: 'copied out of a table printed on the plans — a repeat run reproduces it',
    reproducible: true,
  },
  [ROUTE_SHEET_READING]: {
    label: 'model read the sheet',
    title: 'produced by a model reading a sheet image. A repeat run may answer ' +
           'this differently. That is not a claim the number is wrong.',
    reproducible: false,
  },
};

/** Display form of a `quantity_route`, or null when the row carries none. */
export function routeLabel(route) {
  const key = String(route || '').trim();
  if (!key) return null;
  return _ROUTE_LABELS[key] || {
    // An unrecognised route ranks with the reading route, exactly as
    // aggregator._less_reproducible_route does: a string this code has never
    // seen must never be presented as reproducible.
    label: key, title: 'unrecognised route — treated as not reproducible',
    reproducible: false,
  };
}

/** True when ANY row carries a route, i.e. the run is 28-06 or later. */
export function hasQuantityRoutes(rows) {
  return (rows || []).some(r => r && 'quantity_route' in r);
}

/** The published rows a repeat run may answer differently. */
export function reproducibilityRows(rows) {
  return (rows || []).filter(r => r && r.quantity_route === ROUTE_SHEET_READING);
}

/**
 * The coverage facts for the banner.
 *
 * `coverage` is coverage.json's `summary` block (or takeoff.json's `coverage`,
 * which is the same object). When one is present its numbers are used
 * VERBATIM — the pipeline computed them against the expected-item ledger and
 * the screen has no business recomputing a headline percentage from the rows
 * it happens to be holding.
 *
 * When neither is present the counts are derived from the rows and
 * `pct` is returned as null with `derived: true`. A percentage this module
 * invented would be a different quantity wearing the ledger's name.
 */
export function coverageFacts(coverage, rows) {
  const list = rows || [];
  const c = coverage && typeof coverage === 'object' ? coverage : null;

  const counted = { measured: 0, needsReview: 0, notMeasured: 0,
                    humanInput: 0, standard: 0, notApplicable: 0 };
  for (const r of list) {
    const prov = rowProvenance(r);
    if (prov === PROV_MEASURED) counted.measured += 1;
    else if (prov === PROV_NEEDS_REVIEW) counted.needsReview += 1;
    else if (prov === PROV_NOT_MEASURED) counted.notMeasured += 1;
    else if (prov === PROV_HUMAN_INPUT) counted.humanInput += 1;
    else if (prov === PROV_STANDARD) counted.standard += 1;
    else if (prov === PROV_NOT_APPLICABLE) counted.notApplicable += 1;
  }

  const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

  if (c) {
    return {
      derived: false,
      pct: num(c.coverage_pct_items),
      pctPages: num(c.coverage_pct_pages),
      measured: num(c.items_measured) ?? counted.measured,
      needsReview: num(c.items_needs_review) ?? counted.needsReview,
      notMeasured: num(c.items_not_measured) ?? counted.notMeasured,
      humanInput: num(c.items_human_input) ?? counted.humanInput,
      standard: num(c.items_standard) ?? counted.standard,
      notApplicable: counted.notApplicable,
      total: list.length,
    };
  }

  return {
    derived: true,
    pct: null,
    pctPages: null,
    ...counted,
    total: list.length,
  };
}

/**
 * Does this run carry the provenance vocabulary at all?
 *
 * Used to keep a pre-23 report rendering as it always did instead of
 * announcing "0 measured" about a run that never classified anything.
 */
export function hasProvenance(rows) {
  return (rows || []).some(r => r && rowProvenance(r));
}
