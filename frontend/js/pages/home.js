/**
 * Portada — la pantalla de antes de entrar.
 *
 * No es una tarjeta en medio de la pantalla, es una portada a sangre: la
 * escultura de alambre ocupa el fondo y el texto va encima. La tarjeta anterior
 * encerraba el contenido en una caja de 420 px y desperdiciaba el resto del
 * monitor.
 *
 * El fondo NO son dos capas. El campo de estrellas de la aplicación se apaga
 * aquí y lo sustituye el lienzo de js/hero.js, que dibuja las estrellas Y el
 * resorte: son las mismas: se juntan y forman las espiras. Con las dos capas a
 * la vez se verían dos cielos superpuestos, uno quieto y otro formándose.
 *
 * Aquí no hay nada más a propósito: es sólo la vista principal. Todo lo demás
 * está detrás del botón.
 *
 * Los textos llevan data-i18n además de I18N.t(). Los dos hacen falta: t() los
 * pone bien en el primer pintado, y la marca deja que I18N.aplicar() los cambie
 * después sin volver a montar la portada. Volver a montarla reiniciaría la
 * formación del resorte cada vez que alguien toca el selector de idioma.
 */
const HomePage = (() => {
    'use strict';

    function plantilla({ conSesion = false } = {}) {
        // Con sesión abierta la portada es la pantalla de espera (se llega
        // desde el logo de la barra lateral) y el botón devuelve adentro:
        // dice «Continuar», no «Entrar».
        const claveBoton = conSesion ? 'home.continuar' : 'home.entrar';
        return `
            <div class="portada">
                <!-- El lienzo va en su propia capa, sin eventos: los clics
                     tienen que llegar al botón que está encima. -->
                <div class="portada-lienzo" aria-hidden="true">
                    <canvas id="heroCanvas"></canvas>
                </div>

                <!-- Tres bloques, no una lista de elementos sueltos. En el
                     teléfono se apilan centrados, como siempre; en la
                     computadora cada uno se va a su sitio (logos arriba a la
                     izquierda, nombre arriba al centro, lema y botón abajo) y
                     el resorte se queda con el centro de la pantalla para él
                     solo. Es el mismo HTML en los dos casos: el sitio lo decide
                     el CSS, así que no hay dos portadas que mantener. -->
                <div class="portada-contenido">
                    <span class="logo-lockup portada-logos">
                        <img src="/assets/isc-logo.png" alt="ISC" class="logo-lockup__isc">
                        <img src="/assets/logo.png" alt="CGR" class="logo-lockup__cgr">
                    </span>

                    <div class="portada-nombre">
                        <h1 class="portada-titulo">Pohua</h1>
                        <p class="portada-marca">RFQ Quoter</p>
                    </div>

                    <div class="portada-pie">
                        <p class="portada-lema" data-i18n="home.subtitulo">${I18N.t('home.subtitulo')}</p>

                        <!-- El texto va en su propio <span> con data-i18n. Marcar el
                             botón entero borraría la flecha: data-i18n escribe
                             textContent y se llevaría por delante el <svg>. -->
                        <button class="btn btn-primary portada-cta" id="btnGoLogin">
                            <span data-i18n="${claveBoton}">${I18N.t(claveBoton)}</span>
                            <svg viewBox="0 0 24 24" width="18" height="18" fill="none"
                                 stroke="currentColor" stroke-width="2" stroke-linecap="round"
                                 stroke-linejoin="round" aria-hidden="true">
                                <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
                            </svg>
                        </button>
                        <nav class="portada-legal" id="portadaLegal"></nav>
                    </div>
                </div>
            </div>`;
    }

    function render(contenedor, { onLogin, conSesion = false } = {}) {
        contenedor.innerHTML = plantilla({ conSesion });

        // El cielo de la aplicación se apaga: aquí las estrellas las pinta el
        // lienzo de la portada, que además las convierte en el resorte.
        //
        // Se oculta Y se para. Sólo ocultarlo dejaría un segundo lienzo a
        // pantalla completa repintándose 60 veces por segundo sin que se vea.
        document.documentElement.classList.add('portada-activa');
        if (typeof Starfield !== 'undefined') Starfield.pausar();

        // El lienzo se mide con el contenedor ya en pantalla: si se midiera
        // antes, tendría ancho 0 y no se dibujaría nada.
        requestAnimationFrame(() => Hero.init(document.getElementById('heroCanvas')));

        if (typeof Legal !== 'undefined') Legal.enlaces(contenedor.querySelector('#portadaLegal'));

        const boton = contenedor.querySelector('#btnGoLogin');
        if (boton && typeof onLogin === 'function') {
            boton.addEventListener('click', onLogin);
        }
        contenedor.tabIndex = -1;
        if (boton) boton.focus({ preventScroll: true });
    }

    /** Corta la animación al salir de la portada. La llama el router. */
    function detener() {
        Hero.parar();
        document.documentElement.classList.remove('portada-activa');
        if (typeof Starfield !== 'undefined') Starfield.reanudar();
    }

    return { render, detener };
})();
