/**
 * Quoting — vacío a propósito, por ahora.
 *
 * La lista de RFQs y las calculadoras que había aquí se retiran mientras se
 * rehace la pantalla. El endpoint (`GET /api/rfqs`) y el cliente
 * (`API.listRFQs`) siguen en su sitio intactos: lo único que falta es esta
 * vista, así que recuperarla no depende de nada del servidor.
 */
const RFQListPage = {
    async render(contenedor) {
        contenedor.innerHTML = `
            <div class="pantalla-vacia">
                <svg viewBox="0 0 24 24" width="40" height="40" fill="none"
                     stroke="currentColor" stroke-width="1.5"
                     stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                </svg>
                <p>${I18N.t('quoting.enObras')}</p>
            </div>`;
    }
};
