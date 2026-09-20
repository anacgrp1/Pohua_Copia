# Prueba controlada del flujo completo

Una pasada entera, de punta a punta, con el freno de mano puesto: **no sale ni
un correo al cliente**. El sistema lee el buzón, clasifica, extrae, lee el
plano, da de alta el RFQ, calcula y deja la respuesta preparada — y ahí se
para. Lo que se comprueba es que cada eslabón hace su parte y que se ve dónde
está cada cosa.

Se hace en dos vueltas, en este orden:

| Vuelta | Quién abre el buzón | Qué se comprueba |
|---|---|---|
| **A** | La aplicación de escritorio, por el Outlook de la computadora | El flujo completo: correo → RFQ → oferta preparada → avisos |
| **B** | El servidor de Render | Que el relevo funciona: mientras la aplicación late, el servidor se aparta; cuando deja de latir, el servidor vuelve a hacerse cargo |

Todo pasa en la carpeta **TEST** del buzón `sales.isc@cgr-international.com`,
sobre la base de Neon y la aplicación desplegada en Render. Nada de esto toca
la bandeja de entrada de verdad.

---

## Paso 0 · El `.env`, que es de donde sale todo

La configuración se lee del `.env` **de la carpeta desde la que se lanza el
programa**. Si abres la aplicación desde otro sitio, no lo encuentra y arranca
con los valores de fábrica: bandeja de entrada, IMAP y base de datos en
`localhost`. La comprobación de arranque entonces dice que falta todo aunque no
falte nada — es lo que pasó en la primera prueba. Ya está corregido: la
aplicación se cambia sola a la carpeta del proyecto antes de leer nada, así que
da igual desde dónde la abras.

Tu `.env` tiene ya lo de siempre (base, buzón, JWT, la llave de extracción).
Para esta prueba le faltan estas líneas — añádelas al final, sin borrar nada:

```
# Quién abre el buzón y cuál
MAIL_MODE=outlook
OUTLOOK_BUZON=sales.isc@cgr-international.com
MAIL_FOLDER=TEST

# El freno de mano: nada sale solo
ENVIO_AUTOMATICO=false

# Para el latido y para los enlaces de los correos internos
APP_URL=https://isc-by-cgr.onrender.com
WORKER_SECRET_KEY=<inventa una cadena larga; la misma que pongas en Render>

# Avisos al teléfono (python scripts/generar_vapid.py)
VAPID_PUBLIC_KEY=<la pública>
VAPID_PRIVATE_KEY=<la privada>
```

Las claves VAPID hacen falta **aquí también**, no sólo en Render: mientras lee
la aplicación de escritorio, es ella la que manda los avisos.

Y en **Render**, en Environment, las mismas cuatro que mandan en el servidor:

```
APP_URL=https://isc-by-cgr.onrender.com
MAIL_FOLDER=TEST
ENVIO_AUTOMATICO=false
WORKER_SECRET_KEY=<la misma de arriba>
VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY=<las mismas dos>
```

En el log del despliegue, comprueba que pasaron las migraciones **019** y
**020**: sin la 020 no hay tabla de recordatorios.

Una vez, en la computadora de la planta:

```
pip install -r requirements.txt -r requirements-desktop.txt
```

---

## Paso 1 · La comprobación previa

**En Pohua**, en Render: entra como administradora, ve a **Perfil** y busca el
panel *¿Listo para el flujo?* → **Comprobar**. Mira la lista entera: lo rojo
impide probar, lo amarillo sólo hay que saberlo. Con el escritorio leyendo, las
credenciales de correo que le falten al servidor salen en amarillo, no en rojo:
es lo correcto, porque no las necesita.

**En la aplicación de escritorio**: al abrirla hace esa misma comprobación
sobre tu máquina y la escribe en el registro. Lo que quieres leer arriba, en el
encabezado, es exactamente esto:

```
sales.isc@cgr-international.com · carpeta TEST · por el Outlook de escritorio
```

Si ahí pone `(buzón por defecto) · carpeta INBOX · por IMAP`, el `.env` no se
cargó o le faltan las líneas del paso 0. No sigas hasta que diga lo de arriba:
leería la bandeja de entrada de verdad.

Por consola hay lo mismo, si lo prefieres: `python scripts/comprobar_flujo.py`.

---

## Paso 2 · Los avisos, aparato por aparato

Una vez en cada aparato, y antes de leer nada: abre Pohua, toca la campana y
acepta los avisos. En el iPhone hay que **añadir Pohua a la pantalla de inicio**
primero; Safari no deja suscribirse desde una pestaña normal. Hazlo en el
teléfono y en la computadora, que son los dos que quieres ver sonar.

La comprobación del paso 1 cuenta los aparatos suscritos: ahí se ve si quedó
hecho.

---

## Paso 3 · El correo de prueba

Desde **una cuenta tuya** (no desde `sales.isc`), manda un correo al buzón de
ventas con lo que trae un RFQ de verdad:

* Asunto con "quote" o "cotización" y, si quieres, un número de parte.
* El **PDF del plano** adjunto.
* En el cuerpo, las cantidades (EAU) y el material.

Después, en Outlook, **muévelo a la carpeta TEST** y déjalo **sin leer**: el
ciclo sólo mira los no leídos, y al terminar lo marca como leído. Apunta el
asunto y la hora; es como lo vas a reconocer en las pantallas.

> Un correo sólo se procesa una vez: se apunta su `Message-ID` y el siguiente
> ciclo lo salta ("duplicado omitido"). Para repetir la prueba, manda uno
> **nuevo**; volver a marcarlo como no leído no sirve.

---

## Paso 4 · Vuelta A: lee la aplicación de escritorio

Con el Outlook clásico abierto y el buzón cargado:

```
python desktop_app/main.py
```

**Iniciar lector** deja el ciclo corriendo cada 5 minutos; **Leer ahora** hace
uno inmediatamente y se salta el horario de atención, que es lo que quieres si
estás probando fuera de 6–18 o en fin de semana.

Lo que tiene que ir apareciendo en el registro, en este orden:

1. Conectado a la carpeta TEST del buzón de ventas.
2. Un correo sin leer encontrado.
3. Clasificado como RFQ y extraído el cuerpo.
4. Leído el plano del PDF.
5. RFQ dado de alta, con su número.
6. Ciclo terminado: `1 sin leer · 1 procesado · 1 RFQ · 0 con error`.

Y a la vez, fuera de la aplicación:

* El correo queda **marcado como leído** en la carpeta TEST.
* Suena el aviso en el teléfono y en la computadora.
* En Pohua (Render), **Resumen** mueve sus contadores y el último ciclo cambia
  de hora; **Correo** enseña el correo; **Detalle de RFQ** enseña los datos
  extraídos y el veredicto de factibilidad; **Cotización** enseña la oferta
  preparada, esperando aprobación. Nada se ha enviado.
* En **Perfil → ¿Listo para el flujo?**, el punto de *quién lee el correo* debe
  decir que lee la aplicación de escritorio, y desde cuándo.

Si algo se queda a medias, el registro dice en qué paso: eso es lo que hay que
contar, no "no funcionó".

---

## Paso 5 · Vuelta B: el relevo al servidor

Pulsa **Detener** y cierra la aplicación. El servidor tarda en darse cuenta un
poco más de un intervalo — con `INTERVALO_MINUTOS=5`, unos **seis minutos**—,
que es a propósito: un latido perdido por una mala conexión no debe hacer que
los dos se pongan a leer a la vez.

Pasados esos minutos:

* **Perfil → ¿Listo para el flujo?** deja de decir que lee el escritorio, y lo
  que antes era amarillo pasa a rojo: ahora sí hace falta que el servidor sepa
  entrar al buzón, porque no hay nadie más.
* En **Monitor**, el registro del servicio enseña al worker volviendo a
  intentarlo.

A partir de aquí depende de si tienes credenciales de Azure:

**Si las tienes** (Graph configurado en Render): manda un **segundo** correo de
prueba a TEST, sin leer, y en **Resumen** pulsa **Ejecutar ciclo**. Tiene que
pasar exactamente lo mismo que en la vuelta A, pero leyendo Render.

**Si no las tienes**: lo que se prueba aquí es el relevo, no la lectura. El
registro del servidor dirá que no puede autenticarse contra el buzón, y eso es
el resultado correcto de esta vuelta. El correo de prueba se queda sin leer en
TEST: **no se pierde nada**. Vuelve a abrir la aplicación de escritorio, pulsa
**Leer ahora**, y compruébalo — lo recoge ella. Ese es el respaldo entero, visto
funcionar.

---

## Paso 6 · El horario de atención

De lunes a viernes, de 6:00 a 18:00 hora de Kansas City. Fuera de eso el ciclo
automático **ni abre el buzón**: el correo espera a la apertura, y tanto la
barra de Pohua como el registro de la aplicación dicen hasta cuándo.

Para verlo sin esperar al fin de semana: con la aplicación en marcha, mira el
registro fuera de hora y compara — el ciclo automático dice "cerrado", y
**Leer ahora** lo salta a propósito, porque quien pulsa un botón quiere leer.

---

## Paso 7 · El recordatorio de dictamen

Si un caso lleva más de `RECORDATORIO_HORAS` (4 por defecto) esperando
dictamen, sale un correo **interno** a quien tiene permiso para dictaminar. En
esta prueba **no va a salir**, y con razón: `ENVIO_AUTOMATICO` está apagado, y
eso vale para todo lo que manda la máquina sola, no sólo para lo que va al
cliente. El registro lo dice, y el caso **no** queda apuntado como avisado, así
que el día que enciendas el envío saldrá igual.

Cuando quieras verlo salir de verdad, en otra pasada: `ENVIO_AUTOMATICO=true`,
`RECORDATORIO_HORAS=1`, y vuelve a correr el ciclo una hora después del alta.

---

## Paso 8 · Cerrar la prueba

* Devuelve a su sitio lo que hayas tocado para probar
  (`RECORDATORIO_HORAS`, `ENVIO_AUTOMATICO`).
* Deja `MAIL_FOLDER=TEST` hasta que el flujo esté validado del todo.
* Los RFQ de prueba se quedan en la base con su número. Si estorban, se borran
  en Neon por su `rfq_id` — y hay que borrar también su fila en
  `correos_procesados`, o el correo seguirá contando como ya procesado.

---

## Si algo no sale

| Lo que ves | Lo que suele ser | Qué hacer |
|---|---|---|
| El encabezado dice `(buzón por defecto) · INBOX · por IMAP` | No se cargó el `.env` o le faltan las líneas del paso 0 | Añádelas y vuelve a abrir la aplicación |
| "No encuentro el buzón … Buzones abiertos: …" | El nombre de `OUTLOOK_BUZON` no es el que Outlook enseña en la columna de carpetas | Copia el nombre tal cual sale ahí; vale la dirección o el nombre para mostrar |
| "El buzón no tiene una carpeta TEST" | La carpeta se llama distinto | El nombre exacto, sin importar de dónde cuelgue |
| No habla con Outlook | Es el "nuevo Outlook", o está cerrado | Outlook clásico, abierto, con el buzón cargado |
| `0 sin leer` y el correo está ahí | Está marcado como leído, o no está en TEST | Márcalo como no leído y muévelo |
| "Duplicado omitido" | Ese `Message-ID` ya se procesó | Manda un correo nuevo |
| El RFQ queda *Incomplete* | Falta `ANTHROPIC_API_KEY` | Ponla en el `.env` (y en Render) |
| No llega nada al teléfono | Falta la suscripción de ese aparato, o las claves VAPID donde corre el ciclo | Campana → aceptar; en iPhone, primero a la pantalla de inicio |
| El servidor lee aunque la aplicación esté abierta | `WORKER_SECRET_KEY` distinto en los dos lados, o `APP_URL` mal | El pie de la aplicación dice si el latido llegó |
| No se mueve nada y no hay error | Está fuera del horario | **Leer ahora**, o espera a la apertura |
