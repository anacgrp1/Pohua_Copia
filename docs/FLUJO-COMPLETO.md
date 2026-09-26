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
   │     (una escalera de cantidades —"10000, 22000, 50000"— ES el volumen:
   │      se toma el escalón mayor como EAU y el RFQ sigue adelante)
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

Lo que sale hacia el comprador pasa por uno de dos interruptores. Lo que
manda el sistema SOLO —petición de datos, declinación, recordatorios— va por
`ENVIO_AUTOMATICO`; lo que manda una persona pulsando un botón —la oferta— va
por `ENVIO_MANUAL`, encendido por defecto. `ENVIO_AUTOMATICO` apagado
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

## 3. Probar el flujo completo con la carpeta TEST

Esta sección es el ensayo general: un correo de verdad en una carpeta de
pruebas, y de ahí hasta la oferta, con los avisos llegando al teléfono. Sin
tocar el correo de ventas y sin que salga nada al cliente.

### 3.1 Antes de empezar: comprobarlo todo de una vez

**Desde la propia aplicación** (es lo que hace falta para probar en el servidor
desplegado): entra en Pohua como administrador y abre **Perfil → Sistema**.
Arriba hay una lista de comprobaciones con su estado, y un botón para volver a
pasarlas. La contesta el servidor que de verdad lee el correo, así que dice lo
que ve RENDER, no lo que hay en la computadora de quien mira.

Dice, pieza por pieza, qué está puesto y qué falta: la base y sus migraciones,
qué carpeta se va a leer y si se puede abrir —con cuántos correos sin leer hay
dentro—, si estamos en horario, si el worker arranca solo, si el envío al
cliente está apagado, si hay claves VAPID y cuántos dispositivos suscritos,
quién recibiría el recordatorio, y si están el lector y las calculadoras. No
manda nada, no marca nada como leído y no escribe en la base: sólo mira.

La misma comprobación, en la consola:

```
python scripts/comprobar_flujo.py              # comprueba también el buzón
python scripts/comprobar_flujo.py --sin-buzon  # sin tocar la red
```

Devuelve 1 si falta algo que impida la prueba. Las dos puertas llaman al mismo
código (`app/core/preflight.py`), así que no pueden decir cosas distintas.

Lo que tiene que estar en Render (*Environment*):

```
MAIL_FOLDER=TEST                 la carpeta de pruebas, no la bandeja
ENVIO_AUTOMATICO=false           el sistema no escribe solo
ENVIO_MANUAL=false               ni siquiera la oferta que se manda a mano
ANTHROPIC_API_KEY=...            sin ella no hay extracción ni lectura de plano
APP_URL=https://<tu servicio>.onrender.com
VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY      (python scripts/generar_vapid.py)
WORKER_AUTOSTART=true            para que el buzón se lea solo, cada INTERVALO_MINUTOS
```

### Quién lee el buzón: el servidor o la aplicación de escritorio

Hay dos formas, y las dos valen. **No hacen falta las dos.**

**El servidor lee.** Con un buzón de Microsoft 365 ya no valen usuario y
contraseña: Microsoft retiró la autenticación básica de IMAP y POP en Exchange
Online y no se puede volver a activar. El camino es Graph, que el sistema ya
habla (`AUTH_METHOD=token`): se registra una aplicación en Entra ID, se le dan
permisos de aplicación `Mail.ReadWrite` y `Mail.Send` con consentimiento del
administrador, y de ahí salen `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
`AZURE_CLIENT_SECRET` y `GRAPH_USER`. Conviene limitar la aplicación a ESE
buzón con una *ApplicationAccessPolicy*; si no, podría leer todos los del
dominio.

**La aplicación de escritorio lee.** Es el respaldo cuando no hay credenciales
de Azure: corre en una computadora que ya tiene acceso al buzón y manda su
latido a `POST /api/worker/heartbeat` con `WORKER_SECRET_KEY`. Mientras ese
latido llegue, el worker del servidor **se aparta a propósito** —si no, los dos
leerían el mismo buzón y se pisarían—, y el servidor no necesita ninguna
credencial de correo. Para esto hacen falta dos cosas, y sólo dos: el mismo
`WORKER_SECRET_KEY` en los dos lados, y que la aplicación apunte a la dirección
de Render.

Lo que hace especial a este camino es **por dónde entra al buzón**: por el
Outlook que ya está abierto en esa computadora, con automatización COM —la
misma que usan las macros de toda la vida—. Outlook ya está autenticado contra
Microsoft 365, así que aquí no hay contraseña que caducar, ni aplicación que
registrar, ni administrador a quien pedirle nada. Se enciende con
`MAIL_MODE=outlook`, y lo que sale del buzón entra al mismo ciclo que en la
nube: se clasifica, se extrae, se lee el plano, se da de alta el RFQ y se
avisa.

```
MAIL_MODE=outlook                             por el Outlook de escritorio
OUTLOOK_BUZON=sales.isc@cgr-international.com el buzón, tal como se ve en Outlook
MAIL_FOLDER=TEST                              la carpeta que se lee
APP_URL=https://<tu servicio>.onrender.com    a dónde manda el latido
WORKER_SECRET_KEY=...                         el mismo que en Render
DATABASE_URL=...                              la MISMA base que el servidor
ANTHROPIC_API_KEY=...
```

En la computadora de la planta, una vez:

```
pip install -r requirements.txt -r requirements-desktop.txt
python desktop_app/main.py
```

Y tres cosas que conviene saber antes de que fallen:

* Tiene que ser el **Outlook clásico de escritorio**, abierto y con el buzón
  cargado. El "nuevo Outlook" —el que se parece a la versión web— no tiene COM
  y la aplicación lo dirá así de claro al arrancar.
* `OUTLOOK_BUZON` es el nombre con el que ese buzón aparece en la columna de
  carpetas de Outlook: vale la dirección (`sales.isc@…`) o el nombre para
  mostrar. Si sólo hay un buzón abierto se usa ése sin preguntar.
* La carpeta se busca por su nombre en todo el árbol, así que da igual si
  **TEST** cuelga de la bandeja de entrada o del buzón.

Las respuestas al cliente también salen por ahí —`SentOnBehalfOfName` con el
buzón de ventas—, así que el correo sale del mismo sitio del que saldría si
alguien lo escribiera a mano, sin SMTP ni tokens.

La ventana enseña siempre, arriba, de dónde está leyendo
(`sales.isc@cgr-international.com · carpeta TEST · por el Outlook de
escritorio`), respeta el **horario de atención** igual que el servidor, y trae
la misma comprobación de Perfil → Sistema: al abrirla revisa lo que le falta
antes de leer nada.

La comprobación de **Perfil → Sistema** distingue los dos casos: si el latido
está llegando dice quién lee y desde cuándo, y entonces las credenciales que le
falten al servidor son un aviso, no un fallo. Si deja de latir más de un
intervalo, vuelven a ser un fallo: el buzón se habría quedado sin nadie.

> Para una pasada entera con el freno de mano puesto —dos vueltas, primero
> leyendo la aplicación de escritorio y después comprobando el relevo al
> servidor, sin que salga un solo correo—, el paso a paso está en
> [PRUEBA-CONTROLADA.md](PRUEBA-CONTROLADA.md).

### 3.2 Los avisos, en cada aparato

Una vez por dispositivo, y antes de lanzar el ciclo: abre Pohua, entra en la
campana y acepta los avisos. En iPhone hay que **añadir Pohua a la pantalla de
inicio** antes; Safari no deja suscribirse desde la pestaña. `comprobar_flujo`
cuenta los dispositivos suscritos, así que se ve si quedó hecho.

### 3.3 El correo de prueba

En Outlook, en la carpeta **TEST**, un correo con lo que trae un RFQ de verdad:
asunto con "quote"/"cotización", el PDF del plano adjunto, las cantidades en el
cuerpo y el número de parte. Tiene que estar **SIN LEER**: el ciclo sólo mira
los no leídos, y al terminar lo marca como leído.

Para repetir la prueba con el mismo correo: márcalo como no leído otra vez y
borra su fila en `correos_procesados` (si no, el ciclo lo salta por duplicado).

### 3.4 Lanzar el ciclo

En **Correo**, el botón **Ejecutar ciclo**. Ese botón se salta el horario de
atención a propósito, así que sirve a cualquier hora; el ciclo automático sólo
corre de lunes a viernes de 6:00 a 18:00 (sección 10).

En el Monitor, el registro cuenta la historia: `PARSING [RFQ_NUEVO]`, la
extracción del cuerpo, la lectura del plano, la factibilidad y el alta. Arriba
del registro, la insignia dice de qué buzón se está leyendo: **IMAP · TEST**.

### 3.5 Lo que tiene que pasar, en orden

1. **Llega el aviso.** En la campana y en el teléfono, con el texto del
   machote: *Quote validation required – Cliente* si el RFQ pasó las
   directrices, *Feasibility review required – Cliente* si necesita dictamen.
   Al tocarlo se abre la ventana de revisión con los tramos costeados.
2. **Si faltan datos**, el RFQ queda en *Incomplete* y se construye el correo
   que se los pide al comprador — con la descripción del machote, no con el
   nombre del campo. Con `ENVIO_AUTOMATICO=false` no sale: queda en el log.
3. **Send back** pide la nota y devuelve el caso; **Approve** lo aprueba y abre
   la pantalla Quote con la cotización cargada.
4. **En Quote**: la fecha del RFQ ya viene puesta, los desplegables son los de
   Pohua, y **Spring Calc** es la otra pestaña — se pasa el plano leído, y
   *Usar el peso en la cotización* lo devuelve y vuelve solo a Quote.
5. **Ver PDF** abre la oferta. **Send offer** pide destinatario, plazo,
   incoterm, validez y observaciones. Con `ENVIO_MANUAL=false` el PDF queda
   en `vendor/Quotes/` (o `QUOTES_DIR`) y el log dice "oferta LISTA pero no
   enviada".
6. **Si nadie entra a revisar**, a las `RECORDATORIO_HORAS` (4 por defecto)
   sale el correo de respaldo a quien puede dictaminar, con el enlace al caso
   (sección 11). Para verlo sin esperar: baja el número, o mira la tabla
   `recordatorios_revision` después.

### 3.6 Cuando el resultado sea el esperado

`ENVIO_AUTOMATICO=true`, repite con un correo cuyo remitente seas tú y
comprueba que te llega el PDF. Después, `MAIL_FOLDER=INBOX`.

### 3.7 Si algo no pasa

| Lo que ves | Suele ser |
|---|---|
| El ciclo no encuentra nada | El correo está leído, o está en otra carpeta. La insignia del Monitor dice cuál se lee. |
| "Duplicado omitido" | Ya se procesó: borra su fila en `correos_procesados`. |
| El RFQ acaba en *Incomplete* sin motivo claro | Falta la clave de IA (`ANTHROPIC_API_KEY`), o el plano no se pudo leer. El registro lo dice. |
| No llega nada al teléfono | Faltan las VAPID, o ese aparato no está suscrito. `comprobar_flujo` distingue las dos. |
| El recuadro del plano sale roto | La nota dice por qué (sección 9): sin recorte, no guardado, sesión caducada o de otra máquina. |
| El ciclo automático no corre | Fuera de horario (sección 10). El botón de Correo se lo salta. |

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

### Salir de Cotización y volver no recarga nada

Las demás pantallas se repintan al entrar, y está bien: vuelven a pedir sus
datos. Ésta no. Aquí dentro hay una calculadora con una cotización a medio
escribir, y repintarla significaba tirar los marcos y cargarla otra vez desde
cero —varios segundos, el borrador recuperándose solo y el sitio por donde ibas
perdido—: ir al Monitor un momento costaba más que el trabajo.

Los marcos se quedan montados en su contenedor, que sigue en el documento
aunque esté escondido, y al volver se enseña la pestaña que estaba abierta
(`QuotingPage.montado`). Lo que sí se vacía es al **cerrar sesión**
(`APP.vaciarVistas()`): lo que quedara dentro es trabajo de quien acaba de
salir.

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

4. **Y el marco deja pasar el cielo.** La calculadora declaraba
   `color-scheme:dark` para que los controles del sistema salieran oscuros. El
   efecto secundario es que el navegador deja de dejar ver lo que hay detrás
   del marco y pinta su lienzo del gris casi negro que usa por defecto
   (#121212) —o blanco en claro—, así que el rectángulo de la calculadora salía
   tapado mientras alrededor se veía el resplandor y las estrellas. Dentro de
   Pohua ya no se declara (`js/isc-tema.js`): los desplegables, el campo de
   archivos y la fecha son nuestros, las barras de desplazar se pintan a mano y
   los campos llevan su color puesto, así que no se pierde nada. Suelta, la
   calculadora lo sigue declarando.

En el teléfono, además: la barra de acciones cabe en dos filas (el aviso y el
número arriba, los cuatro botones abajo), el buscador de los desplegables no se
enfoca solo —enfocarlo abre el teclado justo encima de la lista— y la hoja de
resortes se lee en vertical.

Y la barra NO se persigue con JavaScript en el teléfono. Colocarla en cada
scroll de la página de fuera se ve: el dedo desplaza por el compositor y el
`transform` llega un fotograma tarde, así que la barra nadaba sobre el
contenido y parpadeaba, peor todavía con el impulso del scroll táctil. Sin la
regla de anclaje —que ahora es sólo de 821 px para arriba— vuelve a su
`position:fixed` de siempre, que dentro de un marco tan alto como su contenido
la deja quieta al final de la calculadora. El aviso de la calculadora sí haría
falta verlo desde cualquier sitio, así que en el teléfono se esconde ahí y su
texto se le pasa a Pohua, que lo enseña con los suyos.

## 9. Los recortes del plano

"Ver en el plano" abre el recuadro que el lector recortó del PDF. El lector los
escribe en `vendor/lector/_crops`, en disco, y el disco de Render se vacía en
cada despliegue: una cotización de la semana pasada se abría con todos sus
recortes rotos.

Ahora el servidor los conserva: al servir un recorte por primera vez lo copia a
`lector_recortes` (migración 019, Neon), y si el disco ya no lo tiene, lo sirve
desde ahí. La cotización vive en la base; sus recortes también.

Los recortes anteriores a este cambio no están en ninguna parte: la pantalla lo
dice en su sitio en vez de enseñar el icono de imagen partida.

Y lo dice CON EL MOTIVO, porque "no se ve la imagen" son cuatro cosas distintas
y cada una se arregla de otra forma (`js/isc-nube.js`):

- *El lector no guardó ningún recorte para este punto.* La lista de
  factibilidad de la hoja de resortes abre la ventana del plano en CUALQUIER
  fila, y hay filas —una norma, una nota— que no tienen recuadro.
- *Ya no está guardado en el servidor: vuelve a leer el plano.* El 404 de
  siempre, el de los recortes anteriores a la migración 019.
- *La sesión del lector caducó: recarga Pohua.* Un 401 o un 403.
- *Apunta a otra máquina.* La cotización guarda la dirección del lector con la
  que se leyó el plano; si se leyó con el lector corriendo en la computadora de
  quien cotiza, esa dirección es un `127.0.0.1` que desde la nube no existe.
  Antes de decirlo, se vuelve a pedir el mismo recorte a ESTE servidor —el
  identificador es el mismo—, así que si el servidor lo tiene, se ve y no hace
  falta enterarse de nada.

La imagen no se saca del documento, se esconde y la nota se pone a su lado: la
hoja de resortes reusa siempre el mismo `<img>` y sacarlo dejaba la ventana del
plano rota para el resto de la sesión.

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

## 11. Qué dice cada correo y cada aviso

El texto no se inventa aquí: sale de `docs/Cotizador - texto email &
notificaciones.pdf`, el machote de la empresa. Vive todo junto en
`app/email/templates.py`, y `tests/correo/test_machote.py` comprueba frase por
frase que no se pierda ninguna al tocar el módulo.

**Al cliente** (los tres llevan la firma de la planta: INDUSTRIAL SPRING
CORPORATION, 1801 Bedford Ave, North Kansas City, MO 64116, y los dos sitios):

| Cuándo | Qué dice |
|---|---|
| Falta información para cotizar | Agradece, dice que ya se está revisando y pide **sólo lo que falta**, con la descripción del machote ("Volume / EAU: Target batch quantity or Estimated Annual Usage"), no el nombre interno del campo. |
| No se puede cotizar | Declina sin adornos: los parámetros quedan fuera de la capacidad de fabricación, y deja la puerta abierta a otros proyectos. |
| Se manda la oferta | Cuerpo corto del machote, el PDF adjunto y las tres condiciones que se contestan sin abrir el adjunto: plazo, incoterm y validez. |

**A quien dictamina** — y esto es lo importante: el aviso principal **no es el
correo**, es la campana de Pohua y la notificación del teléfono, con los textos
del machote ("Feasibility review required – Cliente", "Quote validation
required – Cliente"). El correo es el respaldo.

### El recordatorio

Si un RFQ lleva más de `RECORDATORIO_HORAS` (4 por defecto) esperando a una
persona, sale **un** correo a quien puede dictaminar, con el enlace al caso:

- en `RequiresReview` → *Feasibility review required*, con la línea que evita
  malentendidos: al cliente todavía no se le ha escrito nada;
- en `New` → *Quote validation required*.

Quién lo recibe no es una lista escrita a mano: son los usuarios de Pohua, de
alta, con permiso `rfq:dictaminar`. Dar de alta a alguien con rol de PM basta
para que empiece a recibirlos.

Que sea un respaldo y no una lluvia lo garantizan tres cosas: la tabla
`recordatorios_revision` (migración 020) apunta cada caso ya recordado y no se
repite; la revisión corre al final del ciclo de detección, que **sólo corre en
horario de atención** (sección 10), así que lo del viernes por la tarde se
recuerda el lunes por la mañana y no de madrugada; y sin `APP_URL` no se manda
nada, porque un enlace a `localhost` en un correo no sirve para nada.

Para apagarlo: `RECORDATORIO_HORAS=0`.
