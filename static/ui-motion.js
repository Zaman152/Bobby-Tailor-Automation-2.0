/**
 * Lightweight page transitions (Motion library — vanilla, Framer Motion family)
 * Phase 15 extensions: modal, drawer, button pulse
 */
import { animate, stagger } from 'https://cdn.jsdelivr.net/npm/motion@11.13.5/+esm';

const prefersReducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export function pageEnter(el) {
  if (!el || prefersReducedMotion()) return;
  return animate(
    el,
    { opacity: [0, 1], y: [14, 0] },
    { duration: 0.38, easing: [0.22, 1, 0.36, 1] }
  );
}

export function staggerChildren(container, selector = '.report-card') {
  if (!container || prefersReducedMotion()) return;
  const items = container.querySelectorAll(selector);
  if (!items.length) return;
  return animate(
    items,
    { opacity: [0, 1], y: [12, 0] },
    { delay: stagger(0.06), duration: 0.32, easing: 'ease-out' }
  );
}

export function pulseButton(el) {
  if (!el || prefersReducedMotion()) return;
  animate(el, { scale: [1, 0.97, 1] }, { duration: 0.2 });
}

// ── Phase 15 Extensions ──

/**
 * Modal entrance animation
 * @param {HTMLElement} el - Modal content element
 */
export function modalEnter(el) {
  if (!el || prefersReducedMotion()) return;
  return animate(
    el,
    { opacity: [0, 1], scale: [0.95, 1], y: [12, 0] },
    { duration: 0.28, easing: [0.22, 1, 0.36, 1] }
  );
}

/**
 * Drawer slide animation
 * @param {HTMLElement} el - Drawer element
 * @param {string} from - 'left' | 'right' (default: 'right')
 */
export function drawerSlide(el, from = 'right') {
  if (!el || prefersReducedMotion()) return;
  const fromX = from === 'right' ? '100%' : '-100%';
  return animate(
    el,
    { x: [fromX, '0%'] },
    { duration: 0.35, easing: [0.22, 1, 0.36, 1] }
  );
}

/**
 * Fade out animation
 * @param {HTMLElement} el - Element to fade
 */
export function fadeOut(el) {
  if (!el || prefersReducedMotion()) return;
  return animate(
    el,
    { opacity: [1, 0] },
    { duration: 0.2, easing: 'ease-out' }
  );
}

/**
 * Fade in animation
 * @param {HTMLElement} el - Element to fade
 */
export function fadeIn(el) {
  if (!el || prefersReducedMotion()) return;
  return animate(
    el,
    { opacity: [0, 1] },
    { duration: 0.25, easing: 'ease-in' }
  );
}

/**
 * Button pulse for primary CTAs (e.g., preview open, run start)
 * More prominent than pulseButton
 * @param {HTMLElement} el - Button element
 */
export function pulseCTA(el) {
  if (!el || prefersReducedMotion()) return;
  return animate(
    el,
    { scale: [1, 1.05, 1] },
    { duration: 0.4, easing: 'ease-in-out' }
  );
}

/**
 * Slide up from bottom (e.g., sticky run footer)
 * @param {HTMLElement} el - Element to slide
 */
export function slideUpEnter(el) {
  if (!el || prefersReducedMotion()) return;
  return animate(
    el,
    { opacity: [0, 1], y: [20, 0] },
    { duration: 0.3, easing: [0.22, 1, 0.36, 1] }
  );
}

/**
 * Scale hover effect (subtle, for cards)
 * @param {HTMLElement} el - Element to scale
 */
export function hoverScale(el) {
  if (!el || prefersReducedMotion()) return;
  return animate(
    el,
    { scale: 1.02 },
    { duration: 0.2, easing: 'ease-out' }
  );
}

window.uiMotion = {
  pageEnter,
  staggerChildren,
  pulseButton,
  // Phase 15 additions
  modalEnter,
  drawerSlide,
  fadeOut,
  fadeIn,
  pulseCTA,
  slideUpEnter,
  hoverScale,
  prefersReducedMotion,
};
