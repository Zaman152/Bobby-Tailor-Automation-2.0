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
