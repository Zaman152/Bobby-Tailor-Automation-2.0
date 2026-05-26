/**
 * Drawer Component — Bobby Tailor
 * Slide-over panel for large content (report workspace, settings)
 * 
 * Usage:
 *   import { openDrawer, closeDrawer } from './drawer.js';
 *   openDrawer({ side: 'right', width: '80%', content: '<div>...</div>' });
 */

import { animate } from 'https://cdn.jsdelivr.net/npm/motion@11.13.5/+esm';
import { trapFocus, releaseFocus } from './focus-trap.js';

let activeDrawer = null;
let previousFocus = null;

/**
 * Open a drawer panel
 * @param {Object} options
 * @param {string} options.side - 'left' | 'right' (default: 'right')
 * @param {string} options.width - CSS width (default: '600px')
 * @param {string} options.content - Drawer content HTML
 * @param {boolean} options.closeOnBackdrop - Close on backdrop click (default: true)
 * @param {Function} options.onClose - Callback when drawer closes
 */
export function openDrawer({ side = 'right', width = '600px', content, closeOnBackdrop = true, onClose }) {
  if (activeDrawer) closeDrawer();
  
  previousFocus = document.activeElement;
  
  const overlay = document.createElement('div');
  overlay.className = 'ui-drawer-overlay';
  overlay.innerHTML = `
    <div class="ui-drawer ui-drawer-${side}" style="width: ${width};">
      <div class="drawer-content">
        ${content}
      </div>
    </div>
  `;
  
  document.body.appendChild(overlay);
  const drawer = overlay.querySelector('.ui-drawer');
  activeDrawer = { overlay, drawer, onClose };
  
  // Event handlers
  if (closeOnBackdrop) {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeDrawer();
    });
  }
  
  document.addEventListener('keydown', handleDrawerEscape);
  
  // Animate entrance
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reducedMotion) {
    overlay.style.opacity = '1';
    drawer.style.transform = 'none';
  } else {
    const fromX = side === 'right' ? '100%' : '-100%';
    animate(overlay, { opacity: [0, 1] }, { duration: 0.25 });
    animate(drawer, { x: [fromX, '0%'] }, { duration: 0.35, easing: [0.22, 1, 0.36, 1] });
  }
  
  // Focus trap
  trapFocus(drawer);
}

function handleDrawerEscape(e) {
  if (e.key === 'Escape' && activeDrawer) {
    e.preventDefault();
    closeDrawer();
  }
}

/**
 * Close the active drawer
 */
export function closeDrawer() {
  if (!activeDrawer) return;
  
  const { overlay, drawer, onClose } = activeDrawer;
  
  releaseFocus();
  document.removeEventListener('keydown', handleDrawerEscape);
  
  const cleanup = () => {
    overlay.remove();
    activeDrawer = null;
    if (previousFocus) previousFocus.focus();
    if (onClose) onClose();
  };
  
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reducedMotion) {
    cleanup();
  } else {
    const side = drawer.classList.contains('ui-drawer-right') ? 'right' : 'left';
    const toX = side === 'right' ? '100%' : '-100%';
    Promise.all([
      animate(overlay, { opacity: 0 }, { duration: 0.2 }),
      animate(drawer, { x: toX }, { duration: 0.3, easing: [0.22, 1, 0.36, 1] })
    ]).then(cleanup);
  }
}

// Global exposure
window.ui = window.ui || {};
window.ui.drawer = { openDrawer, closeDrawer };
