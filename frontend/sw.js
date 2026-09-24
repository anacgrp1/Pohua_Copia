// Pohua · RFQ Quoter — Service Worker (PWA)
//
// ============================================================================
// POR QUÉ ESTE FICHERO SE REESCRIBIÓ
// ============================================================================
// La versión anterior servía TODO cache-first, incluido el HTML. Eso rompía la
// aplicación después de cada despliegue, y de una forma difícil de diagnosticar:
//
//   - Quien ya había entrado alguna vez recibía el index.html viejo desde la
//     caché, para siempre. El index.html es el fichero que NOMBRA a todos los
//     demás, así que un index viejo pedía scripts viejos y se saltaba los
//     nuevos: la mitad de la aplicación no llegaba a cargarse y la pantalla se
//     quedaba en el fondo estrellado, sin contenido.
//
//   - `cache.addAll()` es todo o nada: si UN solo fichero de la lista devolvía
//     404 (por ejemplo, uno recién añadido que aún no estaba desplegado), la
//     instalación entera fallaba, el service worker nuevo no llegaba a
//     activarse y el viejo seguía sirviendo ficheros antiguos indefinidamente.
//
// ============================================================================
// LA ESTRATEGIA AHORA
// ============================================================================
//   /api/            la red, siempre. Llevan token y datos vivos.
//   navegación       la red primero; la caché sólo si no hay conexión.
//   .js y .css       la red primero. Junto con el HTML forman un conjunto que
//                    tiene que ser coherente: servir un script viejo con un
//                    HTML nuevo es justo el fallo que se está arreglando.
//   imágenes, fuentes, manifest
//                    la caché primero. Cambian poco y, si una queda vieja, no
//                    rompe nada: se ve un logo de hace un despliegue.
//
// Se pierde algo de velocidad en la primera carga a cambio de que la aplicación
// no pueda quedarse coherentemente rota. Sin conexión sigue abriendo, que es
// para lo que está el service worker.
// ============================================================================

const VERSION = 'v111';
const CACHE = `cgr-quoter-${VERSION}`;

// Lo mínimo para que la aplicación abra sin conexión. No hace falta listarlo
// todo: lo demás se guarda solo según se va usando.
const PRECARGA = [
    '/',
    '/css/style.css',
    '/js/i18n.js',
    '/js/pages/home.js',
    '/js/hero.js',
    '/js/app.js',
    '/js/api.js',
    '/manifest.json',
    '/assets/icon-192.png',
    '/assets/favicon-32.png',
];

// --------------------------------------------------------------------------
// Instalación
// --------------------------------------------------------------------------
self.addEventListener('install', (evento) => {
    evento.waitUntil((async () => {
        const cache = await caches.open(CACHE);

        // Uno a uno y tolerando fallos, NO con addAll: así un fichero que
        // todavía no esté desplegado no impide que el service worker nuevo se
        // instale. Un recurso que falte aquí se pedirá a la red cuando toque.
        await Promise.all(PRECARGA.map(async (ruta) => {
            try {
                await cache.add(new Request(ruta, { cache: 'reload' }));
            } catch (err) {
                console.warn('[sw] no se pudo precargar', ruta, err);
            }
        }));

        await self.skipWaiting();
    })());
});

// --------------------------------------------------------------------------
// Activación
// --------------------------------------------------------------------------
self.addEventListener('activate', (evento) => {
    evento.waitUntil((async () => {
        // Fuera cualquier caché que no sea la de esta versión. Esto es lo que
        // repara de golpe a quien tuviera guardada la mezcla vieja.
        const nombres = await caches.keys();
        await Promise.all(nombres.filter(n => n !== CACHE).map(n => caches.delete(n)));
        await self.clients.claim();
    })());
});

// --------------------------------------------------------------------------
// Peticiones
// --------------------------------------------------------------------------

/** Guarda en caché sólo lo que tiene sentido guardar. */
async function guardar(peticion, respuesta) {
    // `basic` = mismo origen. Las opacas (otro origen, sin CORS) no se pueden
    // inspeccionar: guardarlas es guardar posiblemente un error.
    if (!respuesta || !respuesta.ok || respuesta.type !== 'basic') return;
    const cache = await caches.open(CACHE);
    await cache.put(peticion, respuesta.clone());
}

/** La red primero; la caché es el plan B cuando no hay conexión.
 *
 * `fresco` salta además la caché HTTP del navegador (`cache: 'reload'`), que
 * es OTRA caché distinta de la nuestra y estaba dando el peor fallo posible:
 * media aplicación nueva y media vieja. El HTML y app.js llegaban del
 * despliegue recién hecho mientras un componente seguía viniendo de la caché
 * del navegador, y un método que la versión vieja no tenía cortaba en seco lo
 * que estuviera haciendo —cerrar sesión, sin ir más lejos—.
 *
 * Sólo para el código: las imágenes y las fuentes no se desincronizan.
 */
async function redPrimero(peticion, alternativa, fresco) {
    try {
        const respuesta = await fetch(fresco ? new Request(peticion, { cache: 'reload' }) : peticion);
        guardar(peticion, respuesta);   // sin await: no hace esperar a la página
        return respuesta;
    } catch (err) {
        const guardada = await caches.match(peticion);
        if (guardada) return guardada;
        if (alternativa) {
            const shell = await caches.match(alternativa);
            if (shell) return shell;
        }
        throw err;
    }
}

/** La caché primero, y se actualiza por detrás para la próxima vez. */
async function cachePrimero(peticion) {
    const guardada = await caches.match(peticion);
    if (guardada) {
        // Refresco en segundo plano: la próxima carga ya tendrá la nueva.
        fetch(peticion).then(r => guardar(peticion, r)).catch(() => {});
        return guardada;
    }
    const respuesta = await fetch(peticion);
    guardar(peticion, respuesta);
    return respuesta;
}

self.addEventListener('fetch', (evento) => {
    const peticion = evento.request;

    // Sólo GET: un POST no se puede guardar en caché y cache.put lanzaría.
    if (peticion.method !== 'GET') return;

    const url = new URL(peticion.url);

    // Otro origen: que lo resuelva el navegador a su manera.
    if (url.origin !== self.location.origin) return;

    // La API nunca se cachea: lleva token y datos que cambian.
    if (url.pathname.startsWith('/api/')) return;

    // Navegación: SIEMPRE la red primero. El HTML nombra al resto de ficheros,
    // así que servirlo viejo desincroniza la aplicación entera.
    if (peticion.mode === 'navigate') {
        evento.respondWith(redPrimero(peticion, '/', true));
        return;
    }

    // Código: la red primero, por la misma razón: HTML y scripts tienen que
    // venir del mismo despliegue.
    if (/\.(?:js|css)$/.test(url.pathname)) {
        evento.respondWith(redPrimero(peticion, null, true));
        return;
    }

    // Lo demás (imágenes, fuentes, manifest): la caché primero.
    evento.respondWith(cachePrimero(peticion));
});


// ============================================================================
// AVISOS PUSH: la campana, en el centro de notificaciones del teléfono
// ============================================================================
// El servidor (app/notifications/push.py) manda cada aviso de la campana a
// los dispositivos suscritos. Aquí se recibe, se pinta, y al tocarlo se abre
// Pohua directo en la ventana de revisión del RFQ (#/rfq/<id>). Si la app ya
// estaba abierta, se trae al frente y se le cambia la dirección en vez de
// abrir otra pestaña.
// ============================================================================

self.addEventListener('push', (evento) => {
    let datos = {};
    try {
        datos = evento.data ? evento.data.json() : {};
    } catch (_) {
        datos = { titulo: 'Pohua', cuerpo: evento.data ? evento.data.text() : '' };
    }
    const titulo = datos.titulo || 'Pohua';
    const opciones = {
        body: datos.cuerpo || '',
        icon: '/assets/icon-192.png',
        badge: '/assets/favicon-32.png',
        // Mismo RFQ = misma notificación: un segundo aviso del mismo RFQ
        // sustituye al primero en vez de apilarse.
        tag: datos.tag || 'pohua',
        renotify: true,
        // Un RFQ que espera dictamen no se descarta solo al rato.
        requireInteraction: datos.nivel === 'crit' || datos.nivel === 'warn',
        // Que suene y que vibre.
        //
        // Con Pohua abierta el tono lo pone js/sonido.js, que es nuestro. Aquí
        // no se puede: la Notifications API nunca llegó a tener `sound`, así
        // que un aviso del sistema suena con el sonido del sistema o no suena.
        // Lo único que se decide desde aquí es eso —`silent: false`— y el
        // patrón de vibración, que en el teléfono es lo que de verdad se nota.
        // Si en Windows no se oye nada, el interruptor está en Configuración →
        // Sistema → Notificaciones, en la fila del navegador.
        silent: false,
        vibrate: datos.nivel === 'crit' ? [90, 60, 90, 60, 160] : [70, 50, 110],
        data: { url: datos.url || '/', rfq_id: datos.rfq_id || null },
        actions: datos.rfq_id ? [{ action: 'abrir', title: 'Revisar' }] : [],
    };
    evento.waitUntil(self.registration.showNotification(titulo, opciones));
});

self.addEventListener('notificationclick', (evento) => {
    evento.notification.close();
    const destino = new URL((evento.notification.data && evento.notification.data.url) || '/',
                            self.location.origin).href;
    evento.waitUntil((async () => {
        const ventanas = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
        for (const v of ventanas) {
            if (new URL(v.url).origin === self.location.origin) {
                // La app ya está abierta: al frente, y a la ventana del RFQ.
                // Se le manda la dirección en vez de navegar: cambiar el hash
                // abre la ventana sin recargar la página (js/components/push.js).
                v.postMessage({ tipo: 'abrir', url: destino });
                return v.focus();
            }
        }
        return self.clients.openWindow(destino);
    })());
});

// El navegador renueva la suscripción de vez en cuando: hay que avisarle al
// servidor de la nueva, si no los avisos dejan de llegar sin que nadie lo note.
self.addEventListener('pushsubscriptionchange', (evento) => {
    evento.waitUntil((async () => {
        const vieja = evento.oldSubscription;
        const opciones = vieja ? { userVisibleOnly: true, applicationServerKey: vieja.options.applicationServerKey } : null;
        if (!opciones) return;
        const nueva = await self.registration.pushManager.subscribe(opciones);
        // Sin token aquí (vive en sessionStorage de la página): se le deja a
        // la página, que al abrirse vuelve a registrar lo que tenga.
        const ventanas = await self.clients.matchAll({ type: 'window' });
        for (const v of ventanas) v.postMessage({ tipo: 'push-renovada', suscripcion: nueva.toJSON() });
    })());
});
