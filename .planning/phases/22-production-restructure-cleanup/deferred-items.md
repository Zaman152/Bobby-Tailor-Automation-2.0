# Phase 22 — Deferred Items

Out-of-scope discoveries logged during execution. Not fixed in this phase.

## From 22-04 (Step 7, dead JS removal)

### D-22-01 — Design system documents a `ui.toast` API with no implementation

- **Found:** 22-04 Task 2, during the pre-deletion grep for external consumers of the dead modules.
- **Where:** `docs/design/bobby-tailor/pages/projects.md:189-191`
- **What:** The design contract specifies toast behavior as
  `ui.toast.success("Plan sets updated")`, `ui.toast.error("Failed to load plan sets. Check connection.")`,
  and `ui.toast.info("Syncing plan sets… (this may take a moment)")`.
- **Why it is not a regression:** the only implementation of `window.ui.toast` was
  `static/js/ui/toast.js`, which had **no `<script>` tag in any template** — it was never
  loaded in a browser session, so `ui.toast` never existed at runtime. Deleting the file
  changed nothing observable. The spec/implementation gap pre-dates Phase 22.
- **Options for a future phase:** either implement a toast primitive that satisfies the
  design contract, or amend `projects.md` to describe the notification mechanism the app
  actually uses. Do not restore `toast.js` from history without also wiring a script tag
  and a consumer — it would re-create dead code.
- **Scope note:** fixing this is a behavior/UI change, which RESTRUCTURE-SPEC §7 places
  outside Phase 22's no-behavior-change contract.
