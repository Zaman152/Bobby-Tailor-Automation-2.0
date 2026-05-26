/**
 * Lucide Icons — SVG Icon Helper
 * Bobby Tailor Estimation Automation
 * 
 * Usage: lucideIcon('file-text', 18) returns SVG element
 * Icons loaded from: https://unpkg.com/lucide-static@latest/icons/
 */

const LUCIDE_CDN = 'https://unpkg.com/lucide-static@latest/icons';
const iconCache = new Map();

/**
 * Create an SVG icon element from Lucide library
 * @param {string} name - Icon name (e.g., 'file-text', 'check', 'x')
 * @param {number} size - Icon size in pixels (default: 18)
 * @param {string} className - Optional CSS class
 * @returns {SVGElement} SVG element ready to insert
 */
export async function lucideIcon(name, size = 18, className = '') {
  const cacheKey = `${name}-${size}`;
  
  if (iconCache.has(cacheKey)) {
    return iconCache.get(cacheKey).cloneNode(true);
  }
  
  try {
    const response = await fetch(`${LUCIDE_CDN}/${name}.svg`);
    if (!response.ok) throw new Error(`Icon ${name} not found`);
    
    const svgText = await response.text();
    const parser = new DOMParser();
    const doc = parser.parseFromString(svgText, 'image/svg+xml');
    const svg = doc.querySelector('svg');
    
    if (!svg) throw new Error('Invalid SVG');
    
    svg.setAttribute('width', size);
    svg.setAttribute('height', size);
    svg.setAttribute('class', `lucide-icon ${className}`.trim());
    svg.setAttribute('aria-hidden', 'true');
    
    iconCache.set(cacheKey, svg);
    return svg.cloneNode(true);
  } catch (error) {
    console.warn(`Failed to load Lucide icon "${name}":`, error);
    // Fallback: empty SVG
    const fallback = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    fallback.setAttribute('width', size);
    fallback.setAttribute('height', size);
    fallback.setAttribute('class', `lucide-icon lucide-missing ${className}`.trim());
    return fallback;
  }
}

/**
 * Synchronously create icon placeholder (loads actual icon async)
 * @param {string} name - Icon name
 * @param {number} size - Icon size
 * @param {string} className - Optional CSS class
 * @returns {HTMLSpanElement} Span that will contain the icon
 */
export function lucideIconPlaceholder(name, size = 18, className = '') {
  const span = document.createElement('span');
  span.className = `lucide-placeholder ${className}`.trim();
  span.style.display = 'inline-flex';
  span.style.alignItems = 'center';
  span.style.justifyContent = 'center';
  span.style.width = `${size}px`;
  span.style.height = `${size}px`;
  
  lucideIcon(name, size, className).then(svg => {
    span.innerHTML = '';
    span.appendChild(svg);
  });
  
  return span;
}

/**
 * Common icon shortcuts for Bobby Tailor
 */
export const icons = {
  preview: (size) => lucideIconPlaceholder('maximize-2', size),
  download: (size) => lucideIconPlaceholder('download', size),
  file: (size) => lucideIconPlaceholder('file-text', size),
  check: (size) => lucideIconPlaceholder('check', size),
  x: (size) => lucideIconPlaceholder('x', size),
  loading: (size) => lucideIconPlaceholder('loader-circle', size),
  folder: (size) => lucideIconPlaceholder('folder', size),
  layers: (size) => lucideIconPlaceholder('layers', size),
  play: (size) => lucideIconPlaceholder('play', size),
  chevronRight: (size) => lucideIconPlaceholder('chevron-right', size),
  chevronDown: (size) => lucideIconPlaceholder('chevron-down', size),
  alertCircle: (size) => lucideIconPlaceholder('alert-circle', size),
  info: (size) => lucideIconPlaceholder('info', size),
};

// Export to global for easy access from app.js
window.lucideIcon = lucideIcon;
window.lucideIconPlaceholder = lucideIconPlaceholder;
window.icons = icons;
