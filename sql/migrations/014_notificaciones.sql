-- =====================================================================
-- 014 — Notificaciones al Plant Manager (COT-77)
--
-- Hasta ahora, cuando un RFQ salía a revisión, el sistema lo dejaba anotado
-- en el log del servidor y devolvía `{"notificado": false}`. El PM se
-- enteraba si miraba la cola. Esta tabla es lo que faltaba para que "notificar
-- al PM vía la aplicación" sea cierto.
--
-- Por qué una tabla de EVENTOS y no una consulta más sobre `rfqs`
-- --------------------------------------------------------------
-- La cola de revisión (`/api/assistant/attention`) ya dice qué está esperando
-- AHORA, y se deduce del estado del RFQ. Eso sirve para trabajar, pero no
-- guarda que el aviso ocurrió: en cuanto el PM dictamina, el RFQ sale de la
-- cola y no queda rastro de que se le avisó, ni de cuándo, ni de por qué.
--
-- Un aviso es un hecho con fecha, y hay preguntas que sólo se pueden
-- responder si se guarda: cuánto tardamos en atender lo que sale a revisión,
-- qué motivo aparece más, si algo se avisó dos veces. Y COT-76 quiere el
-- histórico entero para entrenar; los avisos son parte de ese histórico.
--
-- Por qué `usuario_id` y `leida_por` NO tienen clave ajena a `usuarios`
-- --------------------------------------------------------------------
-- Un acuse de lectura es un hecho de auditoría: dice que alguien leyó esto
-- aquel día. Si mañana esa persona deja ISC y se borra su fila, el hecho
-- siguió ocurriendo, y con `ON DELETE SET NULL` se perdería justo el dato que
-- lo hace útil. Con FK, además, marcar como leído falla entero en cuanto el id
-- del token no existe en la tabla —una cuenta recién borrada, un token de otro
-- entorno—: la campana devolvía 503 y no se podía vaciar el buzón. Se guarda
-- también el correo para que la fila se explique sola sin ir a buscar a nadie.
--
-- Es el mismo criterio que `rfq_id`, y por la misma razón.
--
-- Idempotente: se puede aplicar tantas veces como haga falta.
-- =====================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS notificaciones (
    id           bigserial PRIMARY KEY,

    -- Qué clase de aviso es. Texto y no enum: los avisos nuevos no deberían
    -- necesitar una migración, y el CHECK de abajo ya impide inventárselos.
    tipo         text        NOT NULL,

    -- A qué RFQ se refiere. Es el `rfq_id` de negocio (el del asunto), no el
    -- `id` de la fila: un RFQ tiene varias versiones y el aviso es del RFQ.
    -- Sin FK a propósito — si un día se purga `rfqs`, el aviso sigue contando
    -- lo que pasó.
    rfq_id       text        NOT NULL,

    titulo       text        NOT NULL,
    detalle      text,

    -- Lo que hizo saltar el aviso, tal cual lo vio el motor: motivos, score,
    -- campos en revisión. Se guarda entero para no tener que volver a
    -- deducirlo y para poder entrenar con ello.
    datos_json   jsonb       NOT NULL DEFAULT '{}'::jsonb,

    -- Gravedad, con el mismo vocabulario que `rfq_banderas.nivel` (migración
    -- 005): un aviso y una bandera hablan de lo mismo y deben poder ordenarse
    -- juntos sin traducir nada.
    nivel        text        NOT NULL DEFAULT 'warn',

    -- A quién va dirigido. NULL = a quien tenga el permiso, que es el caso
    -- normal: el aviso es para el puesto de Plant Manager, no para una
    -- persona concreta. Se deja la columna para poder dirigirlo el día que
    -- haya varios PM y se reparta el trabajo.
    usuario_id   bigint,

    creada_en    timestamptz NOT NULL DEFAULT now(),

    -- Cuándo se leyó y quién. NULL = sin leer. Dos columnas y no un booleano
    -- porque "cuándo" es la mitad interesante: el tiempo entre `creada_en` y
    -- `leida_en` es lo que mide si el buzón de avisos se está atendiendo.
    leida_en     timestamptz,
    leida_por    bigint,
    leida_por_correo text,

    CONSTRAINT notificaciones_nivel_chk
        CHECK (nivel IN ('ok', 'info', 'warn', 'crit')),
    CONSTRAINT notificaciones_tipo_chk
        CHECK (tipo IN ('factibilidad_revision', 'extraccion_revision',
                        'dictamen_pm'))
);

-- El índice que sirve a la consulta real de la campana: las sin leer, las más
-- nuevas primero. Parcial, porque las leídas no se consultan así y no tiene
-- sentido pagar por indexarlas.
CREATE INDEX IF NOT EXISTS idx_notificaciones_sin_leer
    ON notificaciones (creada_en DESC)
    WHERE leida_en IS NULL;

CREATE INDEX IF NOT EXISTS idx_notificaciones_rfq
    ON notificaciones (rfq_id);

COMMIT;
