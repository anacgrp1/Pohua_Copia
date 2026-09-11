/**
 * Avatar: la foto de un usuario, o sus iniciales si no tiene.
 *
 * Las iniciales no son un hueco a la espera de una foto: son una identidad
 * completa. El color sale del propio correo, así que la misma persona sale
 * siempre del mismo color en toda la aplicación y se reconoce de un vistazo
 * en una lista aunque nadie haya subido nunca una foto.
 *
 * Si la foto falla al cargarse (borrada, red caída, sesión caducada) se cae a
 * las iniciales en vez de dejar el icono roto del navegador.
 */
const Avatar = (() => {
    'use strict';

    function esc(valor) {
        const nodo = document.createElement('span');
        nodo.textContent = valor == null ? '' : String(valor);
        return nodo.innerHTML;
    }

    /** Dos letras: iniciales del nombre, o las dos primeras si es una palabra. */
    function iniciales(nombre, correo) {
        const limpio = (nombre || '').trim();
        if (limpio) {
            const partes = limpio.split(/\s+/).filter(Boolean);
            if (partes.length >= 2) return (partes[0][0] + partes[1][0]).toUpperCase();
            return limpio.slice(0, 2).toUpperCase();
        }
        return (correo || '?').slice(0, 2).toUpperCase();
    }

    /**
     * Tono estable a partir del correo.
     *
     * Se fija el tono y se dejan quietas la saturación y la luminosidad: así
     * todos los avatares pesan lo mismo y el texto blanco encima contrasta
     * igual en cualquiera de ellos. Con colores libres, unos saldrían legibles
     * y otros no.
     */
    function tono(semilla) {
        const texto = String(semilla || '');
        let acumulado = 0;
        for (let i = 0; i < texto.length; i++) {
            acumulado = (acumulado * 31 + texto.charCodeAt(i)) % 360;
        }
        return acumulado;
    }

    /**
     * Devuelve el HTML del avatar.
     *
     * @param {object} usuario  { id, nombre, correo, tiene_foto, foto_actualizada }
     * @param {object} opciones { tamano: 'sm'|'md'|'lg' }
     */
    function render(usuario, { tamano = 'md' } = {}) {
        const u = usuario || {};
        const clase = `avatar avatar--${tamano}`;
        const color = `--avatar-tono:${tono(u.correo || u.nombre)}`;
        const letras = esc(iniciales(u.nombre, u.correo));

        if (u.tiene_foto && u.id != null) {
            // Sin `src`: la dirección real de la foto necesita la cabecera de
            // sesión y un <img> no la manda (ver API.descargarFoto). Aquí sólo
            // se deja marcada la imagen; el `src` lo pone `hidratar()` cuando
            // ya ha bajado los bytes. Mientras tanto se ven las iniciales, que
            // es exactamente lo que se quiere ver mientras carga.
            return `<span class="${clase}" style="${color}" aria-hidden="true">
                        <span class="avatar-letras">${letras}</span>
                        <img class="avatar-foto" alt="" data-foto="${esc(u.id)}"
                             data-sello="${esc(u.foto_actualizada || '')}">
                    </span>`;
        }
        return `<span class="${clase}" style="${color}" aria-hidden="true">
                    <span class="avatar-letras">${letras}</span>
                </span>`;
    }

    // ----------------------------------------------------------------- fotos

    /**
     * Las fotos ya bajadas, por usuario y sello.
     *
     * La clave lleva el sello (`foto_actualizada`), así que cambiar la foto
     * cambia la clave y la nueva se baja sola; y la misma cara que sale seis
     * veces en la lista de usuarios se baja UNA. Se guarda la promesa, no la
     * dirección: si seis avatares se pintan a la vez, los seis esperan a la
     * misma petición en lugar de disparar seis.
     */
    const enMemoria = new Map();

    function bajar(id, sello) {
        const clave = `${id}:${sello || ''}`;
        if (enMemoria.has(clave)) return enMemoria.get(clave);

        // Esta persona cambió de foto: la anterior ya no la va a pedir nadie.
        // Se suelta su blob —si no, cada cambio de foto deja uno en memoria
        // hasta recargar— y se quita de la tabla.
        for (const vieja of [...enMemoria.keys()]) {
            if (!vieja.startsWith(`${id}:`)) continue;
            enMemoria.get(vieja)?.then(url => URL.revokeObjectURL(url)).catch(() => {});
            enMemoria.delete(vieja);
        }

        const tarea = API.descargarFoto(id, sello).then(blob => URL.createObjectURL(blob));
        // Si falla no se deja la promesa rota guardada para siempre: la
        // siguiente vez que se pinte ese avatar se vuelve a intentar.
        tarea.catch(() => enMemoria.delete(clave));
        enMemoria.set(clave, tarea);
        return tarea;
    }

    async function unaFoto(img) {
        if (img.dataset.puesta) return;
        img.dataset.puesta = '1';
        try {
            img.src = await bajar(img.dataset.foto, img.dataset.sello);
            // Con foto puesta, las iniciales se apagan. NO basta con que la
            // imagen las tape: una foto con transparencia —un PNG recortado,
            // un logotipo— las dejaba asomar por debajo y se leía el nombre
            // encima de la cara. Debajo queda el color de la persona, que es
            // lo que se quiere ver por los huecos.
            img.closest('.avatar')?.classList.add('avatar--con-foto');
        } catch (err) {
            // Borrada, sesión caducada, red caída: se quita la imagen y
            // quedan las iniciales, que siguen identificando a la persona.
            img.remove();
        }
    }

    /** Pone la foto en todos los avatares que haya bajo `raiz`. */
    function hidratar(raiz = document) {
        if (!raiz || typeof raiz.querySelectorAll !== 'function') return;
        raiz.querySelectorAll('img.avatar-foto[data-foto]').forEach(unaFoto);
    }

    /**
     * Se vigila el documento entero en lugar de llamar a `hidratar()` desde
     * cada pantalla.
     *
     * Los avatares se pintan con innerHTML desde media docena de sitios —el
     * menú de la esquina, el perfil, la lista de usuarios, las decisiones de
     * un RFQ— y algunos se repintan solos al refrescarse. Pedirle a cada uno
     * que se acuerde de llamar aquí es pedir que uno se olvide; y el que se
     * olvide enseñará iniciales sin que nadie entienda por qué.
     */
    function vigilar() {
        hidratar(document);
        if (typeof MutationObserver === 'undefined') return;
        new MutationObserver((cambios) => {
            for (const cambio of cambios) {
                for (const nodo of cambio.addedNodes) {
                    if (nodo.nodeType !== 1) continue;
                    if (nodo.matches?.('img.avatar-foto[data-foto]')) unaFoto(nodo);
                    else hidratar(nodo);
                }
            }
        }).observe(document.documentElement, { childList: true, subtree: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', vigilar, { once: true });
    } else {
        vigilar();
    }

    return { render, iniciales, tono, hidratar };
})();
