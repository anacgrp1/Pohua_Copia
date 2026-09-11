/**
 * RFQTable component — renders an RFQ data table with estado badges.
 *
 * RFQTable.render(container, rfqs, onRowClick)
 */
const RFQTable = {
    badgeClass(estado) {
        const map = {
            'New': 'badge-new',
            'ValidatedOK': 'badge-approved',
            'RequiresReview': 'badge-review',
            'Approved': 'badge-approved',
            'Declined': 'badge-declined',
            'Declinado': 'badge-declined',
            'Quoted': 'badge-approved',
        };
        return map[estado] || 'badge-new';
    },

    render(container, rfqs, onRowClick) {
        if (!rfqs || rfqs.length === 0) {
            container.innerHTML = `
                <div class="data-table-wrap">
                    <div class="table-empty">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                            <polyline points="14 2 14 8 20 8"/>
                        </svg>
                        <p>No RFQs to show.</p>
                    </div>
                </div>`;
            return;
        }

        const rows = rfqs.map(r => `
            <tr data-rfq="${r.rfq_id}" style="cursor:pointer">
                <td style="color:var(--text-primary);font-weight:600">${r.rfq_id}</td>
                <td>${r.cliente_id || '—'}</td>
                <td>${r.part_number || '—'}</td>
                <td>${r.material || '—'}</td>
                <td>${r.volumen || '—'}</td>
                <td><span class="badge ${this.badgeClass(r.estado)}"><span class="badge-dot"></span>${r.estado}</span></td>
                <td style="color:var(--text-muted);font-size:12px">${this.formatDate(r.fecha_registro)}</td>
            </tr>
        `).join('');

        container.innerHTML = `
            <div class="data-table-wrap">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>RFQ ID</th>
                            <th>Customer</th>
                            <th>Part Number</th>
                            <th>Material</th>
                            <th>Volume</th>
                            <th>Status</th>
                            <th>Date</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>`;

        // Click handler
        if (onRowClick) {
            container.querySelectorAll('tr[data-rfq]').forEach(tr => {
                tr.addEventListener('click', () => onRowClick(tr.dataset.rfq));
            });
        }
    },

    formatDate(dateStr) {
        if (!dateStr) return '—';
        try {
            const d = new Date(dateStr);
            return d.toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: 'numeric' });
        } catch {
            return dateStr;
        }
    }
};
