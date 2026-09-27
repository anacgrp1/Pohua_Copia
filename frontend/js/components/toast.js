/**
 * Toast notification system.
 */
const Toast = {
    container: null,

    init() {
        this.container = document.getElementById('toastContainer');
    },

    show(message, type = 'info', duration = 4000) {
        if (!this.container) this.init();
        if (!this.container) return;
        const texto = message == null ? '' : String(message);

        // El mismo aviso no se apila: si ya está en pantalla, se alarga el
        // que hay. Un sondeo que falla cada pocos segundos (el teléfono sin
        // red, el servidor despertando) llenaba la pantalla de copias iguales.
        const igual = [...this.container.querySelectorAll('.toast')]
            .find((t) => !t.classList.contains('removing') &&
                         t.dataset.tipo === type && t.dataset.texto === texto);
        if (igual) { this._programar(igual, duration); return; }

        // Y nunca más de tres a la vez: se va el más viejo.
        const vivos = [...this.container.querySelectorAll('.toast:not(.removing)')];
        if (vivos.length >= 3) this._quitar(vivos[0]);

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.dataset.tipo = type;
        toast.dataset.texto = texto;

        const icons = {
            success: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
            error: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
            warning: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
            info: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
        };

        // El texto va como texto: muchos avisos llevan el mensaje de un error
        // del servidor o datos de un correo, y nada de eso entra en innerHTML.
        toast.innerHTML = icons[type] || icons.info;
        const span = document.createElement('span');
        span.textContent = texto;
        toast.appendChild(span);
        this.container.appendChild(toast);
        this._programar(toast, duration);
    },

    _programar(toast, duration) {
        clearTimeout(toast._reloj);
        toast._reloj = setTimeout(() => this._quitar(toast), duration);
    },

    _quitar(toast) {
        clearTimeout(toast._reloj);
        toast.classList.add('removing');
        setTimeout(() => toast.remove(), 200);
    },

    success(msg) { this.show(msg, 'success'); },
    error(msg)   { this.show(msg, 'error', 6000); },
    warning(msg) { this.show(msg, 'warning'); },
    info(msg)    { this.show(msg, 'info'); },
};
