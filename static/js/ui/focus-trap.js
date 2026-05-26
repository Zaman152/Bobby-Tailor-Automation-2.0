/**
 * Focus Trap — Bobby Tailor
 * Trap keyboard focus within modal/drawer for accessibility
 * 
 * Usage:
 *   import { trapFocus, releaseFocus } from './focus-trap.js';
 *   trapFocus(dialogElement);
 *   // ... later
 *   releaseFocus();
 */

let trappedElement = null;
let focusableElements = [];
let firstFocusable = null;
let lastFocusable = null;

const FOCUSABLE_SELECTORS = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

/**
 * Trap focus within an element
 * @param {HTMLElement} element - Container to trap focus within
 */
export function trapFocus(element) {
  if (!element) return;
  
  trappedElement = element;
  updateFocusableElements();
  
  element.addEventListener('keydown', handleTabKey);
  
  // Focus first element
  if (firstFocusable) {
    firstFocusable.focus();
  } else {
    element.focus();
  }
}

/**
 * Release focus trap
 */
export function releaseFocus() {
  if (!trappedElement) return;
  
  trappedElement.removeEventListener('keydown', handleTabKey);
  trappedElement = null;
  focusableElements = [];
  firstFocusable = null;
  lastFocusable = null;
}

function updateFocusableElements() {
  if (!trappedElement) return;
  
  focusableElements = Array.from(
    trappedElement.querySelectorAll(FOCUSABLE_SELECTORS)
  ).filter(el => {
    // Exclude elements with display:none or visibility:hidden
    const style = window.getComputedStyle(el);
    return style.display !== 'none' && style.visibility !== 'hidden';
  });
  
  firstFocusable = focusableElements[0];
  lastFocusable = focusableElements[focusableElements.length - 1];
}

function handleTabKey(e) {
  if (e.key !== 'Tab') return;
  if (!focusableElements.length) return;
  
  // Update in case DOM changed
  updateFocusableElements();
  
  if (e.shiftKey) {
    // Shift+Tab: moving backward
    if (document.activeElement === firstFocusable) {
      e.preventDefault();
      lastFocusable.focus();
    }
  } else {
    // Tab: moving forward
    if (document.activeElement === lastFocusable) {
      e.preventDefault();
      firstFocusable.focus();
    }
  }
}

// Global exposure
window.ui = window.ui || {};
window.ui.focusTrap = { trapFocus, releaseFocus };
