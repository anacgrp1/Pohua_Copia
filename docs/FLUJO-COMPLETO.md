# El flujo completo: del correo a la oferta

Lo que pasa desde que un RFQ entra por el buzón hasta que el comprador
recibe la cotización, y cómo probarlo con la carpeta **TEST** sin tocar la
bandeja de ventas.

## 1. Las etapas

```
correo en el buzón (MAIL_FOLDER)
   │  POST /api/pipeline/run  (o el worker cada INTERVALO_MINUTOS)
   ▼
clasificar ──── trash ──▶ se ignora
   │ RFQ
   ▼
leer el cuerpo (modelo)  →  customer, PN, volumen, escalones, material…
   │
   ├─ falta plano o volumen ──▶ Incomplete + correo "datos faltantes" al comprador
   ▼
leer el plano (visión)   →  resorte: Ø alambre, OD, L0, espiras…
   │
   ├─ faltan datos ──────────▶ Incomplete + correo "datos faltantes"
   ├─ confianza baja ────────▶ RequiresReview + aviso al PM (campana)
   ▼
factibilidad (reglas de planta)
   ├─ no pasa ──────────────▶ RequiresReview + aviso al PM
   └─ pasa ─────────────────▶ New + aviso al PM "listo para aprobar y ofertar"
   ▼
VENTANA DE REVISIÓN DEL PM  (campana → #/rfq/<id>, o Resumen, o RFQ detail → Review)
   tramos costeados con el catálogo de Neon: $/pc, margen, cascada, material, ruta
   ├─ Send back ──▶ nota obligatoria; sigue en revisión; aviso a quien cotiza. No sale correo.
   ├─ Decline ────▶ Declined + correo de rechazo al comprador
   └─ Approve ────▶ Approved → pantalla Quote (la oferta)
   ▼
OFERTA  (Quote → Send offer)
   PDF con el formato de cotización de ISC (vendor/lector/quote_pdf.py)
   + correo "oferta_cliente" con el PDF adjunto → al remitente del RFQ
   constancia en el RFQ: datos_json.oferta y una nota "OFERTA ENVIADA/GENERADA"
```

Todo lo que sale hacia el comprador pasa por `ENVIO_AUTOMATICO`: apagado
(el valor por defecto), el correo se construye y se registra en el log, pero
no sale. Los avisos al PM y los cambios de estado ocurren igual.

## 2. Qué endpoints lo mueven

| Paso | Endpoint | Permiso |
|---|---|---|
| Leer el buzón una vez | `POST /api/pipeline/run` | `worker:operar` |
| Lo que ve la ventana del PM | `GET /api/rfqs/{id}/revision` | `rfq:leer` |
| Devolver con nota | `POST /api/rfqs/{id}/send-back` `{nota}` | `rfq:dictaminar` |
| Aprobar / declinar | `POST /api/rfqs/{id}/approve` · `/decline` | `rfq:dictaminar` |
| Vista previa de la oferta | `GET /api/rfqs/{id}/oferta` | `rfq:leer` |
| El PDF | `GET /api/rfqs/{id}/oferta/pdf` | `rfq:leer` |
| Mandar la oferta | `POST /api/rfqs/{id}/oferta` `{destinatario?, lead_time?, incoterm?, validez_dias?, comentarios?, forzar}` | `rfq:dictaminar` |
| La campana | `GET /api/notificaciones?sin_leer=true` | `notificaciones:ver` |

`forzar=true` hace falta cuando el costeo es *orientativo* (al catálogo le
falta el precio del alambre o la tarifa de una máquina): la ventana y la
pantalla Quote lo dicen, y la pantalla pregunta antes de forzar.

## 3. Probarlo con la carpeta TEST

1. En Outlook, crea la carpeta **TEST** y mueve ahí el correo de prueba
   (asunto con "quote"/"cotización", el PDF del plano adjunto, y las
   cantidades en el cuerpo).
2. En el `.env` del servidor: `MAIL_FOLDER=TEST` y deja
   `ENVIO_AUTOMATICO=False` la primera vez. En Render, las mismas dos
   variables en *Environment*.
3. Arranca y lanza un ciclo: botón **Run cycle** en Mail, o
   `POST /api/pipeline/run`. El correo tiene que estar **sin leer**: el
   ciclo lo marca leído al terminar; para repetir, márcalo sin leer y borra
   su fila en `correos_procesados`.
4. Mira el Monitor: `PARSING [RFQ_NUEVO] RFQ=INT-…`, la extracción del
   cuerpo, el plano, la factibilidad y el alta. Si el modelo no contesta
   (sin `ANTHROPIC_API_KEY`), el RFQ acaba en Incomplete y lo dice.
5. La campana debe tener un aviso nuevo. Ábrelo: es la ventana de revisión,
   con los tramos costeados. En el teléfono es pantalla completa.
6. Prueba **Send back** (pide la nota), y luego **Approve**. Al aprobar se
   abre la pantalla Quote.
7. **View PDF** abre la cotización en otra pestaña. **Send offer** pide
   destinatario, plazo, incoterm, validez y observaciones; con
   `ENVIO_AUTOMATICO=False` el PDF queda en `vendor/Quotes/` (o
   `QUOTES_DIR`) y el log dice "oferta LISTA pero no enviada".
8. Cuando el resultado sea el esperado: `ENVIO_AUTOMATICO=True`, repite con
   un correo cuyo remitente seas tú, y comprueba que llega el PDF. Después,
   `MAIL_FOLDER=INBOX`.

## 4. Lo que hace falta en Neon para que el número sea fiable

El costeo usa el catálogo de `material_precios`, `maquinas` y
`parametros`. Si al material del RFQ le falta precio, la ventana lo marca
("costeo orientativo") y la oferta exige forzarse. Carga el catálogo con
`scripts/cargar_catalogo.py` desde los CSV (que **no** van al repositorio).

## 5. Los avisos en el teléfono (Web Push)

La campana avisa a quien tiene Pohua abierta. Con Web Push el mismo aviso
llega al centro de notificaciones del teléfono con la app cerrada, y tocarlo
abre la ventana de revisión del RFQ.

**Configurar una vez (servidor):**

```bash
python scripts/generar_vapid.py      # imprime VAPID_PUBLIC_KEY y VAPID_PRIVATE_KEY
```

Pega las dos líneas en el `.env` y en Render → Environment. La privada es un
secreto. Sin ellas la campana funciona igual dentro de la app; sólo no sale
nada al teléfono (`GET /api/push/clave` contesta `habilitado:false`).

**Activar en cada dispositivo:** campana → al pie del panel, **Activar**. El
navegador pide permiso, el dispositivo queda registrado
(`push_suscripciones`, una fila por aparato) y llega una notificación de
prueba al momento. **Quitar** en la misma fila lo deshace.

- Android (Chrome/Edge): con Pohua instalada o en el navegador, con la app
  cerrada también.
- iPhone: iOS 16.4+ y Pohua **añadida a la pantalla de inicio** (Safari →
  Compartir → Añadir a inicio); en Safari a secas no hay push y la fila lo
  dice.
- En `localhost` no funciona (la app da de baja el service worker ahí a
  propósito); se prueba en Render.

Qué llega: los mismos cuatro avisos de la campana —factibilidad a revisión,
extracción con confianza baja, listo para aprobar y ofertar, devuelto por el
PM— a todos los dispositivos de quienes tengan `notificaciones:ver`. Un
dispositivo que el servicio de push da por muerto (404/410) se borra solo.

## 6. Usuarios y contraseñas

Las contraseñas nunca se ven: el servidor sólo guarda el hash. Lo que sí
existe, y sólo una vez, es la **temporal** que genera el propio servidor
(`Kf7m-Qw3p-Zt9h`: catorce caracteres sin 0/O ni 1/l).

**Alta** (Perfil → Usuarios → Añadir usuario): correo, nombre, apellido y rol.
Sin contraseña: al crear, sale un diálogo con la temporal y un botón
**Copiar**. Se le da a la persona en mano, o **Mandar a su teléfono** si ya
tenía Pohua con los avisos activados (Web Push, cifrado de punta a punta).

**Primer acceso**: la persona entra con la temporal y Pohua le pide la suya
antes de nada (temporal + nueva + repetir; la nueva cumple la política). Puede
dejarlo para **Luego**: queda una franja arriba y el diálogo vuelve al
siguiente arranque. Si tiene push activado, también le llega el recordatorio
al teléfono. Mientras no la cambie, en la lista de usuarios sale la marca
**Temporal**.

**Olvido**: sólo el administrador. Fila del usuario → **⋯ → Restablecer
contraseña**: se genera otra temporal, se enseña, y con la casilla marcada se
manda al teléfono en el mismo paso (`POST /api/users/{id}/password/reset`).
Si la persona no tiene ningún dispositivo con avisos, el diálogo lo dice y hay
que dársela en persona. `POST /api/users/{id}/password/notificar` sólo manda
la temporal vigente: no sirve para empujar otro texto.

**Arranque con el equipo actual**: para poner a todos la misma provisional
(`password123`, que la API rechaza por política) y obligarles a cambiarla:

```bash
python scripts/contrasena_temporal.py --todos          # pregunta antes
python scripts/contrasena_temporal.py john@... sales@... --password "Otra-2026"
```

Se ejecuta desde la carpeta del proyecto con el `.env` (usa `DATABASE_URL`),
DESPUÉS de que el servidor haya aplicado la migración 018 (arranca una vez).

## 7. Aprobar desde la calculadora de precios

**Approve** en la barra de abajo de la calculadora ya no aprueba en seco: abre
la ventana de aprobación (`frontend/js/isc-aprobacion.js`), igual que la de
revisión de RFQs: tramos, cascada de margen del tramo elegido (precio, AV,
C/CV, C/CD, resultado contra el objetivo), material, ruta y totales, más las
banderas del cálculo y lo que falte para aprobar.

- **Preview PDF**: el mismo `previewPdf()` de la barra; no guarda ni archiva.
- **Send back**: pide una nota; la cotización sigue en DRAFT con la nota a la
  vista en la barra y en el diario (`q.sentBack`).
- **Approve**: el flujo original de la calculadora (permiso, banderas
  abiertas, bloqueo y PDF archivado).
- **Open full quote**: cierra la ventana.

En el teléfono va a pantalla completa con los botones fijos abajo. Los
textos siguen el idioma de Pohua (diccionario en
`scripts/isc_idioma_diccionario.py`).

## 8. Cotización: dos apartados, no una ventana dentro de otra

La pantalla de Cotización tiene arriba dos pestañas de Pohua —**Quote** y
**Spring Calc**— y cada una enseña su calculadora a pantalla completa. Los dos
marcos son hijos directos de Pohua: el de resortes ya no se abre anidado
dentro del de precios.

Por qué se cambió: anidado se veía como una ventanita con dos barras de
título, y a dos marcos de profundidad el tema de Pohua no siempre llegaba —el
resorte salía en claro dentro de Pohua oscuro—. Como apartado propio hereda el
tema igual que la calculadora de precios, en claro y en oscuro, y en el
teléfono la hoja se lee en vertical (`js/isc-tema.js`, reglas ≤820 px).

El traspaso entre las dos sigue igual de automático; lo hace Pohua de
centralita (`js/pages/quoting.js`):

- El botón **Spring Calc** —el de Pohua o el de la propia calculadora— abre el
  apartado y le entrega el plano leído (cotas, tipo de resorte, lista de
  fabricabilidad, número de parte).
- **→ Usar el peso en la cotización** manda el peso y el dictamen a la
  calculadora de precios y vuelve solo a Quote, que es donde se ve el efecto.

La calculadora del núcleo no se tocó para esto: `js/isc-nube.js` intercepta su
apertura anidada y la convierte en un mensaje a Pohua, así que
`scripts/vendorizar_nucleo.py` se puede volver a pasar sin perder nada.

### El alto de los marcos: una sola barra de desplazar

Los dos marcos miden lo que mide su contenido y quien se desplaza es la página
de Pohua. Eso hay que sostenerlo en tres sitios, y los tres estaban flojos:

1. **El marco mide lo suyo** (`js/isc-nube.js`). Antes esa medida sólo
   arrancaba después de esperar a `SFS` y `shared`, que son globales de la
   calculadora de PRECIOS: en la hoja de resortes no existen, así que su marco
   se quedaba en el mínimo del CSS —320 px— con la ficha cortada dentro y media
   pantalla vacía debajo. En la compu igual que en el teléfono. Ahora medir el
   marco arranca solo, en cualquier documento; lo que es de la calculadora de
   precios sigue esperándola.

2. **La hoja fluye** (`js/isc-tema.js`). La calculadora de resortes está
   escrita para ocupar una pantalla: `html,body{height:100%}` y
   `.sheet{height:calc(100vh - 60px)}`. Dentro de un marco que mide lo que su
   contenido, el alto de la hoja depende del marco y el del marco de la hoja.
   Dentro de Pohua —clase `nube-marco`— la hoja se estira hasta lo que ocupe y
   ningún panel se desplaza por dentro. Suelta, su HTML se sigue viendo como se
   escribió.

3. **Lo que flota se coloca contra la ventana de verdad.** Dentro de un marco
   de seis mil píxeles, `position:fixed` no es "la pantalla" y `60vh` no son
   dos tercios de pantalla. La barra de acciones se ancla con un `transform`
   (`js/isc-nube.js`) y publica su alto en `--nube-barra`, que es el hueco que
   el contenido se reserva al final; los desplegables y el calendario
   (`js/isc-selects.js`) miden el hueco real —`window.parent.innerHeight` y
   dónde empieza el marco— para abrirse hacia arriba o hacia abajo, con tope en
   píxeles.

En el teléfono, además: la barra de acciones cabe en dos filas (el aviso y el
número arriba, los cuatro botones abajo), el buscador de los desplegables no se
enfoca solo —enfocarlo abre el teclado justo encima de la lista— y la hoja de
resortes se lee en vertical.

## 9. Los recortes del plano

"Ver en el plano" abre el recuadro que el lector recortó del PDF. El lector los
escribe en `vendor/lector/_crops`, en disco, y el disco de Render se vacía en
cada despliegue: una cotización de la semana pasada se abría con todos sus
recortes rotos.

Ahora el servidor los conserva: al servir un recorte por primera vez lo copia a
`lector_recortes` (migración 019, Neon), y si el disco ya no lo tiene, lo sirve
desde ahí. La cotización vive en la base; sus recortes también.

Los recortes anteriores a este cambio no están en ninguna parte: la pantalla lo
dice en su sitio —"ya no está guardado, vuelve a leer el plano"— en vez de
enseñar el icono de imagen partida.

## 10. El horario de atención

El sistema contesta de lunes a viernes, de 6:00 a 18:00. Fuera de esa ventana
el ciclo **ni abre el buzón**: el correo se queda sin leer donde está y entra
en el primer ciclo de la apertura siguiente. Nada se pierde —el buzón es la
cola—, no se gasta el modelo de madrugada y no sale una oferta a las 2 a.m.,
que es algo que un cliente nota y no para bien.

La ventana vive en un solo reloj, el de la planta (Kansas City), porque el
ciclo es un proceso y no puede tener tres horarios a la vez. Se configura con
cinco variables (`app/core/config.py`):

| Variable | Por defecto | Qué es |
|---|---|---|
| `HORARIO_ACTIVO` | `true` | A `false` se quita la restricción: se lee a cualquier hora. |
| `HORARIO_ZONA` | `America/Chicago` | El reloj que manda. |
| `HORARIO_DESDE` | `6` | Hora de apertura. |
| `HORARIO_HASTA` | `18` | Hora de cierre (a las 18:00 en punto, cerrado). |
| `HORARIO_DIAS` | `1-5` | Días laborables (1 = lunes, 7 = domingo). |

Lo que sí cambia de una persona a otra es cómo se **lee** ese horario. La
pantalla lo dice en la casa que tenga puesta el reloj de arriba —Kansas City
en inglés, Querétaro en español, Sevran en francés— y con el formato de ese
sitio: 12 horas en América, 24 en Francia. Las 6:00 de Kansas son las 5:00 de
Querétaro y las 13:00 de Sevran; una sola ventana, dicha en tres husos. Para
eso `GET /api/status` devuelve los instantes con su desfase
(`2026-09-21T06:00:00-05:00`) y `js/horario.js` los pinta; rotar el reloj mueve
las horas con él.

Dónde se ve:

- **Tablero (Correo)**: una pastilla junto a "Ejecutar ciclo" — "En marcha ·
  contestando hasta las 5:00 p. m." o, en ámbar, "En espera · abre lun 5:00
  a. m.".
- **Barra lateral**: el punto de estado tiene ahora tres colores, no dos —
  verde en marcha, ámbar en espera, rojo parado.
- **Monitor**: la primera tarjeta dice lo mismo, con un reloj por icono.

Un ciclo omitido por horario no cuenta como ciclo: no mueve "último ciclo" ni
los totales (`api/routes/status.py`), porque apuntarlo haría creer que se miró
el buzón y no llegó nada.

**"Ejecutar ciclo" se salta el horario a propósito.** Lo pulsa una persona con
permiso: si le hace falta leer el buzón un domingo, la respuesta correcta es
leerlo. Queda dicho en el registro quién lo pidió y cuándo.

Pruebas: `tests/rfq/test_horario.py` (la ventana, el paso de viernes a lunes,
los tres husos, el ciclo que no toca el buzón y el que se fuerza a mano).
