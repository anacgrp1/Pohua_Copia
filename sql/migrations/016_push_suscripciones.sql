-- =====================================================================
-- 016 — Suscripciones Web Push: los avisos en el teléfono
--
-- La campana avisa a quien tiene Pohua abierta. Para que el aviso llegue al
-- centro de notificaciones del teléfono con la aplicación cerrada hace falta
-- Web Push: el navegador entrega una suscripción (una URL del servicio de
-- push del navegador más dos claves) y el servidor le manda ahí cada aviso.
--
-- Una fila por DISPOSITIVO, no por persona: la misma persona puede tener el
-- teléfono y la compu, y cada uno tiene su suscripción. `endpoint` es único
-- porque el navegador la renueva de vez en cuando; la nueva sustituye a la
-- vieja por su URL, no por usuario.
--
-- Una suscripción muerta (el servicio contesta 404/410) se borra al primer
-- rechazo; `fallos` cuenta los errores transitorios (red, 5xx) para poder
-- limpiar las que llevan tiempo sin funcionar.
--
-- Idempotente.
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS push_suscripciones (
    id              bigserial   PRIMARY KEY,
    usuario_id      bigint      NOT NULL,
    usuario_correo  text,
    endpoint        text        NOT NULL UNIQUE,
    p256dh          text        NOT NULL,
    auth            text        NOT NULL,
    navegador       text,                       -- user-agent recortado, para reconocer el aparato
    creada_en       timestamptz NOT NULL DEFAULT now(),
    ultimo_envio    timestamptz,
    fallos          integer     NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_push_suscripciones_usuario
    ON push_suscripciones (usuario_id);

COMMIT;
