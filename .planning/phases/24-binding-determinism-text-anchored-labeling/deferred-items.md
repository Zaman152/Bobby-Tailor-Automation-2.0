## Deferred — found during 24-02, NOT fixed (out of scope)

**`_min_confidence(x, None)` collapses every deterministically-named wall row to `low`.**

`_fuse_wall_classes` calls `_min_confidence("medium", vision_conf)` and `vision_conf` is
`None` whenever no vision label exists. `_min_confidence` ranks an unknown/absent value as
`low` ("unknown values count as low"), so a **confident printed-thickness bind** — the most
authoritative naming evidence the system has — publishes with `confidence: "low"`.

- **Pre-existing:** the pre-24-02 `elif cls in library_wall_map` branch passed the same
  `vision_conf=None`, so this is not a regression introduced by the precedence inversion.
- **Why not fixed here:** 24-02's plan fences the emit block ("a precedence change, not a
  rewrite of the emitter"), and changing the confidence of every library-bound wall row is
  a cross-cutting artifact change that belongs with the ledger/flagging work.
- **Pinned, not hidden:** `test_an_agreeing_vision_label_corroborates_the_thickness_bind`
  asserts the corroboration RAISE by rank rather than pinning two strings, so the day this
  is fixed the test still passes and still means what it says.
- **Suggested owner:** 24-04 (unnamed-geometry ledger) or the 24-10 phase gate.

---

## Deferred — found during 24-06, NOT fixed (out of scope)

**The Take-Off and Coverage worksheets still write drawing-derived free text as a
potential formula (the pre-existing half of T-24-24).**

Measured this session, not assumed: `ws.append(["=1+1"])` makes openpyxl infer
`data_type='f'` and emit `<f>1+1</f>` — a live formula cell. Forcing
`data_type='s'` emits `<is><t>=1+1</t></is>` instead, which displays the
characters verbatim and evaluates nothing. A leading `=` is the only trigger
openpyxl itself honours; `@`, `+` and `-` are already written as strings.

- **Fixed here:** the new `Unidentified Geometry` worksheet, whose evidence
  column is literally text harvested off the plan, writes every text cell
  through `_write_text` (`data_type='s'`).
- **Still exposed:** `scripts/export_takeoff_excel.py` — the Coverage sheet's
  `reason` cell (classifier/drawing-derived) and the Take-Off sheet's `name`,
  `formula` and `notes` cells (`ws.append(...)`, type inferred).
- **Why not fixed here:** pre-existing, and 24-06's threat register scopes
  T-24-24 to *"Ledger text is drawing-derived and untrusted"*. Widening the diff
  to re-type every cell on two shipped worksheets is a workbook-wide change that
  should be made and verified as one, not smuggled in beside a new sheet.
- **The fix is one helper call per cell:** `_write_text(ws, row, col, value)`
  already exists in that file and is inert for any value that is not an
  injection (openpyxl's loader returns the same `.value` either way, so no
  existing assertion moves).
- **Suggested owner:** the 24-10 phase gate, or any later plan that touches the
  exporter.
