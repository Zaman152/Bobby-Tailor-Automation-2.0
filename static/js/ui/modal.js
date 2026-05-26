/**
 * Modal Component — Bobby Tailor
 * Native <dialog> with focus trap and Motion animations
 * 
 * Usage:
 *   import { openModal, closeModal } from './modal.js';
 *   openModal({ title: 'Confirm', bodyHtml: '<p>Are you sure?</p>', onClose: () => {} });
 */

import { animate } from 'https://cdn.jsdelivr.net/npm/motion@11.13.5/+esm';
import { trapFocus, releaseFocus } from './focus-trap.js';

let activeModal = null;
let previousFocus = null;

/**
 * Open a modal dialog
 * @param {Object} options
 * @param {string} options.title - Modal title
 * @param {string} options.bodyHtml - Modal body HTML
 * @param {string} options.size - 'sm' | 'md' | 'lg' (default: 'md')
 * @param {boolean} options.closeOnBackdrop - Close on backdrop click (default: true)
 * @param {Function} options.onClose - Callback when modal closes
 */
export function openModal({ title, bodyHtml, size = 'md', closeOnBackdrop = true, onClose }) {
  if (activeModal) closeModal();
  
  previousFocus = document.activeElement;
  
  const dialog = document.createElement('dialog');
  dialog.className = `ui-modal ui-modal-${size}`;
  dialog.innerHTML = `
    <div class="modal-content">
      <div class="modal-header">
        <h3 class="modal-title">${title}</h3>
        <button type="button" class="modal-close-btn" aria-label="Close dialog">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
      <div class="modal-body">
        ${bodyHtml}
      </div>
    </div>
  `;
  
  document.body.appendChild(dialog);
  activeModal = dialog;
  
  // Event handlers
  const closeBtn = dialog.querySelector('.modal-close-btn');
  closeBtn.addEventListener('click', () => closeModal(onClose));
  
  if (closeOnBackdrop) {
    dialog.addEventListener('click', (e) => {
      const rect = dialog.getBoundingClientRect();
      const isInDialog = (
        e.clientX >= rect.left &&
        e.clientX <= rect.right &&
        e.clientY >= rect.top &&
        e.clientY <= rect.bottom
      );
      if (!isInDialog) closeModal(onClose);
    });
  }
  
  dialog.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      closeModal(onClose);
    }
  });
  
  // Show dialog
  dialog.showModal();
  
  // Animate entrance
  const content = dialog.querySelector('.modal-content');
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    content.style.opacity = '1';
    content.style.transform = 'none';
  } else {
    animate(
      content,
      { opacity: [0, 1], scale: [0.95, 1], y: [12, 0] },
      { duration: 0.28, easing: [0.22, 1, 0.36, 1] }
    );
    animate(
      dialog,
      { opacity: [0, 1] },
      { duration: 0.2 }
    );
  }
  
  // Focus trap
  trapFocus(dialog);
}

/**
 * Close the active modal
 * @param {Function} callback - Optional callback after close
 */
export function closeModal(callback) {
  if (!activeModal) return;
  
  const dialog = activeModal;
  const content = dialog.querySelector('.modal-content');
  
  releaseFocus();
  
  const cleanup = () => {
    dialog.close();
    dialog.remove();
    activeModal = null;
    if (previousFocus) previousFocus.focus();
    if (callback) callback();
  };
  
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    cleanup();
  } else {
    Promise.all([
      animate(content, { opacity: 0, scale: 0.95, y: -12 }, { duration: 0.2 }),
      animate(dialog, { opacity: 0 }, { duration: 0.15 })
    ]).then(cleanup);
  }
}

// Global exposure
window.ui = window.ui || {};
window.ui.modal = { openModal, closeModal };
