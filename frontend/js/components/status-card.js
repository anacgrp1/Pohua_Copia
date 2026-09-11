/**
 * StatusCard — la fila de cifras del Monitor.
 *
 * StatusCard.render(contenedor, tarjetas)
 *   tarjetas: [{ id, icono, valor, etiqueta, color }]
 *
 * Cada tarjeta lleva su color de marca en `color`, y ese color baña la tarjeta
 * entera: la pastilla del icono, el tinte del fondo y la mancha de la esquina.
 * El CSS lo lee de una sola variable, `--kpi`, así que aquí basta con
 * escribirla una vez por tarjeta.
 *
 * El icono va PRIMERO en el marcado, no al final: ahora es lo primero que se
 * ve arriba a la izquierda, y el orden del DOM y el de la vista deberían
 * contarse la misma historia.
 *
 * El icono es decorativo y va marcado como tal: lo que dice la tarjeta ya está
 * escrito al lado en texto, y un lector de pantalla que además leyera el dibujo
 * repetiría lo mismo dos veces.
 *
 * `id` no es cosmético: `update(id, valor)` refresca sólo la cifra sin volver a
 * montar la fila, que es lo que hace el sondeo cada pocos segundos.
 */
const StatusCard = {
    /** Los valores pueden venir de la base: nunca a innerHTML en crudo. */
    esc(valor) {
        const nodo = document.createElement('span');
        nodo.textContent = valor == null ? '' : String(valor);
        return nodo.innerHTML;
    },

    render(contenedor, tarjetas) {
        // `add`, no `className =`. Asignar la clase entera borraba las que ya
        // llevara el contenedor, y con ellas el ajuste de la pantalla que lo
        // usa: en el Resumen la fila se quedaba con las cuatro columnas del
        // Monitor dentro de media pantalla, y las etiquetas salían partidas en
        // tres renglones.
        contenedor.classList.add('kpi-fila');
        contenedor.innerHTML = tarjetas.map(t => `
            <article class="kpi" id="card-${this.esc(t.id)}"
                     style="--kpi:${t.color || 'var(--cgr-gris)'}">
                <div class="kpi-icono" aria-hidden="true">${t.icono}</div>
                <div class="kpi-texto">
                    <div class="kpi-valor" id="val-${this.esc(t.id)}">${this.esc(t.valor)}</div>
                    <div class="kpi-etiqueta">${this.esc(t.etiqueta)}</div>
                </div>
            </article>
        `).join('');
    },

    update(id, valor) {
        const el = document.getElementById(`val-${id}`);
        if (!el) return;
        el.textContent = valor;
        el.style.animation = 'none';
        el.offsetHeight;                       // fuerza el reflujo
        el.style.animation = 'fadeIn 0.3s ease-out';
    },
};
