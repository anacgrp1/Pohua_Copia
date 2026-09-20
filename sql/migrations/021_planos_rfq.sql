-- 021 · Los planos del RFQ, guardados en la base y no sólo en el disco
-- ---------------------------------------------------------------------------
-- El dibujo llega adjunto al correo y se guardaba SÓLO en el disco de quien
-- leyó el buzón (app/persistence/blueprint_store.py). Eso deja el fichero
-- donde no sirve:
--
--   * Si lee el lector de escritorio, el plano queda en esa computadora, y la
--     web —que corre en Render— no lo tiene: "Abrir cotización completa" no
--     puede ponerlo en la casilla del lector de planos.
--   * Si lee el servidor, queda en un disco que se borra en cada despliegue.
--
-- Con esto el plano viaja con el RFQ: lo guarda quien lo lea y lo ve todo el
-- mundo. Son PDF o imágenes de un dibujo —cientos de KB—, no archivos de
-- vídeo; van en `bytea` para no montar un almacén aparte por esto.

CREATE TABLE IF NOT EXISTS rfq_planos (
    id           SERIAL PRIMARY KEY,
    rfq_id       TEXT NOT NULL,
    nombre       TEXT NOT NULL,
    tipo         TEXT,
    bytes        INTEGER NOT NULL DEFAULT 0,
    contenido    BYTEA NOT NULL,
    guardado_en  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- El mismo correo reprocesado no duplica el plano: se sustituye.
    UNIQUE (rfq_id, nombre)
);

CREATE INDEX IF NOT EXISTS idx_rfq_planos_rfq ON rfq_planos (rfq_id);
