/**
 * Data Grid Wrapper — Bobby Tailor
 * Lightweight sortable/filterable table for calculations and raw data
 * 
 * Phase 15: Simple implementation with native table + JavaScript
 * (Grid.js CDN integration deferred to avoid bundle weight)
 */

/**
 * Mount an enhanced data table
 * @param {HTMLElement} container - Container element
 * @param {Object} options - Grid options
 * @param {Array<string>} options.headers - Column headers
 * @param {Array<Array>} options.rows - Data rows
 * @param {boolean} options.sortable - Enable column sorting (default: true)
 * @param {Function} options.onExport - Export callback (receives filtered rows)
 */
export function mountGrid(container, options) {
  const { headers, rows, sortable = true, onExport } = options;
  
  let filteredRows = [...rows];
  let sortColumn = null;
  let sortAsc = true;
  
  const render = () => {
    container.innerHTML = `
      <div class="grid-toolbar">
        <input type="text" class="grid-search" placeholder="Search all columns..." />
        ${onExport ? '<button type="button" class="grid-export-btn">Export Filtered CSV</button>' : ''}
        <span class="grid-count">${filteredRows.length} of ${rows.length} rows</span>
      </div>
      <div class="data-table-container">
        <table class="data-table enhanced-grid">
          <thead>
            <tr>
              ${headers.map((h, i) => `
                <th data-col="${i}" class="${sortColumn === i ? 'sorted ' + (sortAsc ? 'asc' : 'desc') : ''}">
                  ${h}
                  ${sortable ? '<span class="sort-icon">⇅</span>' : ''}
                </th>
              `).join('')}
            </tr>
          </thead>
          <tbody>
            ${filteredRows.map(row => `
              <tr>
                ${row.map(cell => `<td>${cell !== null && cell !== undefined ? cell : ''}</td>`).join('')}
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
    
    // Search handler
    const searchInput = container.querySelector('.grid-search');
    searchInput.addEventListener('input', (e) => {
      const query = e.target.value.toLowerCase();
      if (!query) {
        filteredRows = [...rows];
      } else {
        filteredRows = rows.filter(row => 
          row.some(cell => String(cell).toLowerCase().includes(query))
        );
      }
      render();
    });
    
    // Sort handlers
    if (sortable) {
      container.querySelectorAll('th[data-col]').forEach(th => {
        th.addEventListener('click', () => {
          const col = parseInt(th.dataset.col);
          if (sortColumn === col) {
            sortAsc = !sortAsc;
          } else {
            sortColumn = col;
            sortAsc = true;
          }
          
          filteredRows.sort((a, b) => {
            const aVal = a[col];
            const bVal = b[col];
            
            // Numeric sort if both are numbers
            const aNum = parseFloat(aVal);
            const bNum = parseFloat(bVal);
            if (!isNaN(aNum) && !isNaN(bNum)) {
              return sortAsc ? aNum - bNum : bNum - aNum;
            }
            
            // String sort
            const aStr = String(aVal).toLowerCase();
            const bStr = String(bVal).toLowerCase();
            return sortAsc ? aStr.localeCompare(bStr) : bStr.localeCompare(aStr);
          });
          
          render();
        });
      });
    }
    
    // Export handler
    if (onExport) {
      const exportBtn = container.querySelector('.grid-export-btn');
      exportBtn.addEventListener('click', () => {
        const csv = [
          headers.join(','),
          ...filteredRows.map(row => row.map(cell => 
            typeof cell === 'string' && cell.includes(',') ? `"${cell}"` : cell
          ).join(','))
        ].join('\n');
        
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `filtered_export_${Date.now()}.csv`;
        a.click();
        URL.revokeObjectURL(url);
        
        if (onExport) onExport(filteredRows);
      });
    }
  };
  
  render();
}

// Global exposure
window.dataGrid = { mountGrid };
