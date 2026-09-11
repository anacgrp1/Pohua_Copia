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
