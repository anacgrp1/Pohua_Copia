## 3. Probar el flujo completo con la carpeta TEST

Esta sección es el ensayo general: un correo de verdad en una carpeta de
pruebas, y de ahí hasta la oferta, con los avisos llegando al teléfono. Sin
tocar el correo de ventas y sin que salga nada al cliente.

### 3.1 Antes de empezar: comprobarlo todo de una vez

```
python scripts/comprobar_flujo.py
```

Dice, pieza por pieza, qué está puesto y qué falta: la base y sus migraciones,
qué carpeta se va a leer y cuántos correos sin leer hay ahí, si estamos en
horario, si el envío al cliente está apagado, si hay claves VAPID y cuántos
dispositivos suscritos, quién recibiría el recordatorio y si están el lector y
las calculadoras. No manda nada ni marca nada: sólo mira. Devuelve 1 si falta
algo que impida la prueba.

Se corre donde estén las credenciales: en tu computadora con el `.env`, o en la
consola de Render (*Shell*) para comprobar **lo desplegado**, que es lo que de
verdad va a correr.

Lo que tiene que estar en Render (*Environment*):

```
MAIL_FOLDER=TEST                 la carpeta de pruebas, no la bandeja
ENVIO_AUTOMATICO=false           nada sale al cliente todavía
ANTHROPIC_API_KEY=...            sin ella no hay extracción ni lectura de plano
APP_URL=https://<tu servicio>.onrender.com
VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY      (python scripts/generar_vapid.py)
```

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
   incoterm, validez y observaciones. Con `ENVIO_AUTOMATICO=false` el PDF queda
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
| El RFQ acaba en *Incomplete* sin motivo claro | Falta `ANTHROPIC_API_KEY`, o el plano no se pudo leer. El registro lo dice. |
| No llega nada al teléfono | Faltan las VAPID, o ese aparato no está suscrito. `comprobar_flujo` distingue las dos. |
| El recuadro del plano sale roto | La nota dice por qué (sección 9): sin recorte, no guardado, sesión caducada o de otra máquina. |
| El ciclo automático no corre | Fuera de horario (sección 10). El botón de Correo se lo salta. |

## 4. Lo que hace falta en Neon para que el número sea fiable
