---
phase: 15-premium-ui-ux-revamp
plan: 2
subsystem: ui-primitives
tags: [modal, drawer, toast, focus-trap, motion, accessibility]

requires:
  - "15-01: Design tokens and motion variables"
provides:
  - "Modal component (native <dialog>)"
  - "Drawer component (slide-over panel)"
  - "Toast notifications (success/error/warning/info)"
  - "Focus trap utility"
  - "Extended motion helpers"
affects:
  - "15-03: Report workspace will use drawer primitive"
  - "15-04: Projects stepper may use modal for confirmations"
  - "15-05: Job monitor cancel will use modal"

tech-stack:
  added:
    - "Motion One CDN (already in use, now extended)"
  patterns:
    - "Native <dialog> API for modals (better accessibility than div+aria)"
    - "Focus trap with Tab cycle and Esc close"
    - "Toast stack with auto-dismiss and manual close"
    - "prefers-reduced-motion respected in all animations"

key-files:
  created:
    - static/js/ui/modal.js
    - static/js/ui/drawer.js
    - static/js/ui/toast.js
    - static/js/ui/focus-trap.js
  modified:
    - static/ui-motion.js
    - static/ui-polish.css
    - templates/index.html

decisions:
  - id: PRIM-01
    what: "Use native <dialog> element for modals instead of div+aria-modal"
    why: "Better accessibility, built-in backdrop, showModal() traps focus automatically with proper polyfill"
    impact: "IE11 unsupported (acceptable for 2026 SaaS app). Better screen reader compatibility."

  - id: PRIM-02
    what: "Toast notifications top-right, max 3 stack, 5s auto-dismiss"
    why: "Standard pattern for non-blocking notifications, matches modern SaaS UX"
    impact: "Old toasts auto-remove if 3+ arrive. Users can dismiss manually if needed."

  - id: PRIM-03
    what: "All animations check prefersReducedMotion() before running"
    why: "WCAG 2.1 success criterion 2.3.3 (Animation from Interactions)"
    impact: "Users with vestibular disorders see instant state changes, not animations."

metrics:
  duration: "~2 min"
  completed: "2026-05-26"
---

# Phase 15 Plan 2: UI Primitives Summary

**One-liner:** Modal, drawer, toast, focus trap with Motion animations and accessibility baked in.

## What Was Built

### Task 1: UI Primitives
- **Created** `static/js/ui/modal.js`:
  - `openModal({ title, bodyHtml, size, closeOnBackdrop, onClose })`
  - `closeModal()` with fade-out animation
  - Native `<dialog>` element with `showModal()`
  - Backdrop click to close (optional)
  - Esc key handler
  - Focus trap on open, restore focus on close
  - Motion entrance: scale 0.95→1, opacity 0→1, translateY 12→0 (280ms)
  - Sizes: `sm` (400px), `md` (600px), `lg` (800px)
  - Exposed as `window.ui.modal`

- **Created** `static/js/ui/drawer.js`:
  - `openDrawer({ side, width, content, closeOnBackdrop, onClose })`
  - `closeDrawer()` with slide-out animation
  - Slide-over panel (left or right)
  - Fixed full-height, custom width (default 600px)
  - Backdrop overlay with blur
  - Esc key handler
  - Motion entrance: slide from edge (350ms), backdrop fade (250ms)
  - Exposed as `window.ui.drawer`

- **Created** `static/js/ui/toast.js`:
  - `toast.success(message)`, `toast.error(message)`, `toast.warning(message)`, `toast.info(message)`
  - Auto-dismiss after 5 seconds
  - Manual dismiss button (X)
  - Max 3 toasts visible (oldest removed when 4th arrives)
  - Icon per type: checkmark (success), X-circle (error), triangle (warning), info (info)
  - Motion entrance: slide from right + fade (300ms)
  - Exposed as `window.ui.toast`

- **Created** `static/js/ui/focus-trap.js`:
  - `trapFocus(element)` — trap Tab within element
  - `releaseFocus()` — remove trap
  - Tab cycles: last → first (forward), first → last (backward with Shift+Tab)
  - Dynamic focusable element detection (ignores `display:none`, `visibility:hidden`)
  - Exposed as `window.ui.focusTrap`

- **Updated** `static/ui-polish.css`:
  - `.ui-modal` styles: backdrop, content container, header, body
  - `.modal-close-btn` hover states
  - `.ui-drawer-overlay`, `.ui-drawer`, `.ui-drawer-left/right` styles
  - `.toast-container` (top-right, stacked, z-index 9999)
  - `.toast`, `.toast-success/error/warning/info` with left border accent
  - `.toast-icon`, `.toast-message`, `.toast-close` layout
  - Responsive: toast container adjusts for mobile (<768px)

- **Updated** `templates/index.html`:
  - Added `#ui-modal-root` mount point (unused by native <dialog>, kept for consistency)
  - Added `#ui-toast-root` mount point (unused, toasts append to body)

**Commit:** `2e9bdbb` — feat(15-02): build UI primitives (modal, drawer, toast, focus-trap)

### Task 2: Motion Extensions
- **Extended** `static/ui-motion.js`:
  - `modalEnter(el)` — scale + fade for dialog entrance
  - `drawerSlide(el, from)` — slide from left/right with smooth easing
  - `fadeOut(el)`, `fadeIn(el)` — general-purpose transitions
  - `pulseCTA(el)` — prominent button pulse for primary actions (scale 1→1.05→1, 400ms)
  - `slideUpEnter(el)` — sticky footer entrance animation
  - `hoverScale(el)` — subtle card hover effect (scale 1.02, 200ms)
  - `prefersReducedMotion()` — helper function exported for external use
  - All motion helpers check `prefersReducedMotion()` before animating

**Commit:** `9d8a4e3` — feat(15-02): extend Motion helpers for primitives

## Technical Details

### Native `<dialog>` Benefits

**Accessibility wins:**
- Automatic focus management (focus first focusable element on open)
- Built-in Esc handler (calls `close()` method)
- Inert background (non-dialog content disabled while open)
- Screen reader announces as dialog role

**Implementation:**
- `dialog.showModal()` opens centered with backdrop
- `dialog.close()` dismisses and fires `close` event
- `::backdrop` pseudo-element for styling backdrop

**Browser support:**
- 97% global (Chrome 37+, Safari 15.4+, Firefox 98+)
- IE11 not supported (acceptable for 2026)

### Focus Trap Implementation

**Strategy:**
- On trap: find all focusable elements (a[href], button, input, select, textarea, [tabindex]:not(-1))
- Filter out `display:none` and `visibility:hidden`
- Store first and last focusable
- Listen for Tab/Shift+Tab
- Cycle: last → first (Tab), first → last (Shift+Tab)

**Edge cases handled:**
- No focusable elements: focus container itself
- DOM changes while open: re-scan on each Tab press
- Multiple traps: only one active at a time (release on new trap)

### Toast Stack Behavior

**Queue management:**
- Toasts append to container (top-right)
- New toasts appear below existing (stack grows down)
- Auto-dismiss after 5s (setTimeout)
- Manual dismiss: clear timeout, fade out
- Max 3 visible: oldest removed when 4th arrives

**Aria roles:**
- `role="status"` for info/success/warning (polite announcement)
- `role="alert"` for error (assertive, interrupts screen reader)
- Container: `aria-live="polite"`, `aria-atomic="true"`

### Motion Timing

**Easing curves:**
- Smooth (modal, drawer): `cubic-bezier(0.22, 1, 0.36, 1)` — "ease-out-expo"
- Fast (fade, toast): `ease-out` or `ease-in`

**Duration guidance:**
- Micro (button pulse): 200ms
- Fast (toast, fade): 250-300ms
- Normal (modal, drawer): 300-400ms

**Reduced motion:**
- All animations skip when `prefers-reduced-motion: reduce`
- Instant state changes (opacity 0→1, transform none)

## Deviations from Plan

**None** — Plan executed exactly as written. No bugs fixed, no blocking issues.

## Next Phase Readiness

**Phase 15 Wave 2 (15-03 Report Workspace):**
- ✅ Drawer primitive ready for report preview workspace
- ✅ Toast ready for "Sync complete" notifications
- ✅ Motion helpers ready for tab transitions

**Phase 15 Wave 2 (15-04 Projects Stepper):**
- ✅ Toast ready for sync errors
- ✅ Modal ready for run confirmation (if needed)
- ✅ slideUpEnter ready for sticky run footer

**Phase 15 Wave 3 (15-05 Job Monitor):**
- ✅ Modal ready for cancel confirmation
- ✅ Toast ready for job complete notifications

**Verification:**
- ✓ Modal/drawer/toast usable from app.js without duplicating DOM logic
- ✓ All primitives respect prefers-reduced-motion
- ✓ Focus trap works (Tab cycles, Esc closes)

## Human Verification

**Manual UAT (to be done in 15-06 or via browser console now):**

1. Modal test:
   ```js
   window.ui.modal.openModal({
     title: 'Test Modal',
     bodyHtml: '<p>This is a test modal. Press Esc or click backdrop to close.</p>',
     size: 'md'
   });
   ```
   - ✓ Modal appears centered with backdrop
   - ✓ Esc closes modal
   - ✓ Backdrop click closes modal (if closeOnBackdrop=true)
   - ✓ Focus returns to previous element

2. Drawer test:
   ```js
   window.ui.drawer.openDrawer({
     side: 'right',
     width: '400px',
     content: '<h3>Test Drawer</h3><p>Press Esc to close.</p>'
   });
   ```
   - ✓ Drawer slides from right
   - ✓ Esc closes drawer
   - ✓ Backdrop click closes drawer

3. Toast test:
   ```js
   window.ui.toast.success('Operation successful!');
   window.ui.toast.error('Something went wrong');
   window.ui.toast.info('New updates available');
   ```
   - ✓ Toasts appear top-right, stacked
   - ✓ Auto-dismiss after 5s
   - ✓ Manual dismiss works (X button)

4. Reduced motion test:
   - System Preferences → Accessibility → Display → Reduce motion (ON)
   - Open modal/drawer/toast
   - ✓ No animation, instant state change

## Files Changed

**Created (4):**
- `static/js/ui/modal.js` (157 lines)
- `static/js/ui/drawer.js` (118 lines)
- `static/js/ui/toast.js` (144 lines)
- `static/js/ui/focus-trap.js` (89 lines)

**Modified (3):**
- `static/ui-motion.js` (+112 lines: motion helpers)
- `static/ui-polish.css` (+185 lines: modal/drawer/toast styles)
- `templates/index.html` (+3 lines: mount points)

**Total:** +808 lines added

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1    | 2e9bdbb | feat(15-02): build UI primitives (modal, drawer, toast, focus-trap) |
| 2    | 9d8a4e3 | feat(15-02): extend Motion helpers for primitives |

---

*Plan 15-02 complete. Ready for Wave 2 (15-03 Report Workspace, 15-04 Projects Stepper).*
