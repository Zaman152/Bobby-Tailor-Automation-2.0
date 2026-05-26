/**
 * Toast Notifications — Bobby Tailor
 * Auto-dismissing notifications (success, error, info)
 * 
 * Usage:
 *   import { toast } from './toast.js';
 *   toast.success('Report exported successfully');
 *   toast.error('Failed to load plan sets');
 */

import { animate } from 'https://cdn.jsdelivr.net/npm/motion@11.13.5/+esm';

const TOAST_DURATION = 5000; // 5 seconds
const MAX_TOASTS = 3;
let toastContainer = null;
let toastCount = 0;

function ensureContainer() {
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = 'ui-toast-container';
    toastContainer.className = 'toast-container';
    toastContainer.setAttribute('aria-live', 'polite');
    toastContainer.setAttribute('aria-atomic', 'true');
    document.body.appendChild(toastContainer);
  }
  return toastContainer;
}

function createToast(message, type = 'info') {
  const container = ensureContainer();
  
  // Remove oldest if at max
  if (toastCount >= MAX_TOASTS) {
    const oldest = container.firstElementChild;
    if (oldest) removeToast(oldest);
  }
  
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
  
  const icon = getIcon(type);
  toast.innerHTML = `
    <div class="toast-icon">${icon}</div>
    <div class="toast-message">${message}</div>
    <button type="button" class="toast-close" aria-label="Dismiss">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
      </svg>
    </button>
  `;
  
  container.appendChild(toast);
  toastCount++;
  
  // Animate entrance
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!reducedMotion) {
    animate(toast, { opacity: [0, 1], x: [20, 0] }, { duration: 0.3, easing: 'ease-out' });
  }
  
  // Auto-dismiss
  const timeoutId = setTimeout(() => removeToast(toast), TOAST_DURATION);
  
  // Manual dismiss
  const closeBtn = toast.querySelector('.toast-close');
  closeBtn.addEventListener('click', () => {
    clearTimeout(timeoutId);
    removeToast(toast);
  });
  
  return toast;
}

function removeToast(toast) {
  if (!toast || !toast.parentElement) return;
  
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const cleanup = () => {
    toast.remove();
    toastCount--;
  };
  
  if (reducedMotion) {
    cleanup();
  } else {
    animate(toast, { opacity: 0, x: 20 }, { duration: 0.2 }).then(cleanup);
  }
}

function getIcon(type) {
  switch (type) {
    case 'success':
      return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="20 6 9 17 4 12"/>
      </svg>`;
    case 'error':
      return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
      </svg>`;
    case 'warning':
      return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>`;
    default:
      return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
      </svg>`;
  }
}

export const toast = {
  success: (message) => createToast(message, 'success'),
  error: (message) => createToast(message, 'error'),
  warning: (message) => createToast(message, 'warning'),
  info: (message) => createToast(message, 'info'),
};

// Global exposure
window.ui = window.ui || {};
window.ui.toast = toast;
