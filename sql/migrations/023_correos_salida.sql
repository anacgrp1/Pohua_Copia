-- 023 · La bandeja de salida: quien arma el correo no es quien lo manda
-- ---------------------------------------------------------------------------
-- La oferta la arma el proceso web (Render) cuando el plant manager pulsa
-- «Enviar oferta». Pero el buzón de ISC se abre por el Outlook de escritorio
-- de una computadora concreta: Render no tiene cuenta emisora, y mientras no
-- haya una aplicación registrada en Entra ID, no la va a tener.
--
-- Leer ya estaba repartido así —lee la aplicación de escritorio y el worker
-- del servidor se aparta— y funcionaba porque los dos lados hablan con la
-- MISMA base en Neon. Mandar no estaba repartido: el PDF se generaba, se
-- archivaba, y el correo al cliente moría con «No hay cuenta emisora
-- configurada».
--
-- Esta tabla es el punto de encuentro. Render deja aquí el correo ya redactado
-- y la aplicación de escritorio, que sí tiene Outlook, lo despacha en su
-- siguiente ciclo y escribe el desenlace en la misma fila.
--
-- Por qué los adjuntos van en `bytea` y no como ruta: el PDF de la oferta lo
-- escribe Render en SU disco, y esa ruta no existe en la computadora que va a
-- mandar el correo. Guardar la ruta sería guardar una promesa que el otro lado
-- no puede cumplir. Son decenas de KB por oferta.
--
-- Las imágenes de la firma NO se guardan: son del repositorio y cada lado
-- resuelve las suyas al mandar, así que viajan como no-viajan las cosas que ya
-- están en los dos sitios.

CREATE TABLE IF NOT EXISTS correos_salida (
    id            SERIAL PRIMARY KEY,
    rfq_id        TEXT,
    -- Para qué es este correo. Hoy sólo 'oferta'; el día que la declinación o
    -- la petición de datos también necesiten salir por aquí, se distinguen.
    clase         TEXT NOT NULL DEFAULT 'oferta',
    destinatario  TEXT NOT NULL,
    asunto        TEXT NOT NULL,
    cuerpo_html   TEXT,
    cuerpo_texto  TEXT,
    -- pendiente → lo tiene que recoger el escritorio
    -- enviado   → salió; `enviado_en` dice cuándo
    -- fallo     → se intentó y no salió; `ultimo_error` dice por qué
    estado        TEXT NOT NULL DEFAULT 'pendiente'
                  CHECK (estado IN ('pendiente', 'enviado', 'fallo')),
    intentos      INTEGER NOT NULL DEFAULT 0,
    ultimo_error  TEXT,
    creado_en     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    creado_por    TEXT,
    enviado_en    TIMESTAMPTZ
);

-- El lector pregunta siempre lo mismo: «¿qué hay pendiente?», lo más viejo
-- primero, para que una oferta no se adelante a otra que lleva esperando.
CREATE INDEX IF NOT EXISTS idx_correos_salida_pendientes
    ON correos_salida (estado, id);

CREATE INDEX IF NOT EXISTS idx_correos_salida_rfq
    ON correos_salida (rfq_id);

CREATE TABLE IF NOT EXISTS correos_salida_adjuntos (
    id          SERIAL PRIMARY KEY,
    -- Si el correo se borra, sus adjuntos se van con él: un PDF suelto sin
    -- correo al que pertenecer no le sirve a nadie y ocupa.
    salida_id   INTEGER NOT NULL REFERENCES correos_salida (id) ON DELETE CASCADE,
    nombre      TEXT NOT NULL,
    tipo        TEXT,
    bytes       INTEGER NOT NULL DEFAULT 0,
    contenido   BYTEA NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_correos_salida_adjuntos_correo
    ON correos_salida_adjuntos (salida_id);
