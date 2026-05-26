/**
 * Lightweight page transitions (Motion library — vanilla, Framer Motion family)
 */
import { animate, stagger } from 'https://cdn.jsdelivr.net/npm/motion@11.13.5/+esm';

export function pageEnter(el) {
  if (!el) return;
  return animate(
    el,
    { opacity: [0, 1], y: [14, 0] },
    { duration: 0.38, easing: [0.22, 1, 0.36, 1] }
  );
}

export function staggerChildren(container, selector = '.report-card') {
  if (!container) return;
  const items = container.querySelectorAll(selector);
  if (!items.length) return;
  return animate(
    items,
    { opacity: [0, 1], y: [12, 0] },
    { delay: stagger(0.06), duration: 0.32, easing: 'ease-out' }
  );
}

export function pulseButton(el) {
  if (!el) return;
  animate(el, { scale: [1, 0.97, 1] }, { duration: 0.2 });
}

window.uiMotion = { pageEnter, staggerChildren, pulseButton };
