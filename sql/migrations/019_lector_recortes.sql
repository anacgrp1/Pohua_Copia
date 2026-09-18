-- =====================================================================
-- 019 — Los recortes del plano, en la base y no en el disco
--
-- El lector guarda cada recorte ("ver en el plano") como PNG dentro de
-- `vendor/lector/_crops`, en el disco de la máquina. En la planta eso está
-- bien: el disco es el de siempre. En Render NO: el disco es efímero y se
-- vacía en cada despliegue, así que una cotización de la semana pasada se
-- abría con todos sus recortes rotos —el icono de imagen partida— y sin
-- forma de recuperarlos salvo volver a leer el plano.
--
-- La cotización vive en Neon; sus recortes también deben vivir ahí. El PNG
-- se guarda la primera vez que alguien lo pide y se sirve desde aquí cuando
-- el disco ya no lo tiene.
--
-- Idempotente: CREATE TABLE IF NOT EXISTS.
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS lector_recortes (
    cid         text PRIMARY KEY,
    png         bytea NOT NULL,
    bytes       integer NOT NULL,
    creado_en   timestamptz NOT NULL DEFAULT now(),
    ultimo_uso  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE lector_recortes IS
    'PNG de los recortes del plano que enseña la calculadora. El lector los escribe en disco (efímero en Render); aquí sobreviven al despliegue.';

COMMIT;
