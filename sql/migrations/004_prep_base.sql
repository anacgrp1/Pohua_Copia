-- =====================================================================
-- PASO 0 — Poner la base del repositorio al día con el DER
-- =====================================================================
-- Escrito contra el DDL real de Programación/sql/schema.sql
-- (commit 22e10b9 «feat: COT-86/87 modelo clientes + cliente_dominios»).
--
-- Estado del que parte:
--   correos_procesados   existe — no se toca
--   rfq_historial        existe — no se toca
--   clientes             existe — se le agregan 10 columnas
--   cliente_dominios     existe — no se toca
--   resortes_cotizacion  existe con 24 columnas — se le agregan 2
--   rfqs                 existe — conserva su nombre, + 6 columnas
--   resortes             NO existe — se crea
--
-- Lo que este script NO hace:
--   * no renombra ninguna tabla ni columna
--   * no quita nada
--   * no toca correos_procesados ni rfq_historial
--   * no carga datos
--
-- ⚠️ COORDINACIÓN: `resortes` y `resortes_cotizacion` son de Ana.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. Maestro de piezas  (no existía)
-- ---------------------------------------------------------------------
-- Las medidas usan el mismo vocabulario que `resortes_cotizacion`
-- (`diametro_*`, `numero_espiras_*`, `constante_resorte_n_mm`), para que
-- la ficha canónica y lo que extrae la IA se puedan comparar sin traducir
-- nombres. El DER usaba la forma corta `diam_*`; se actualizó el diagrama.
CREATE TABLE IF NOT EXISTS resortes (
    resorte_id        bigserial PRIMARY KEY,
    num_parte               text NOT NULL UNIQUE,
    tipo                    text,
    diametro_alambre_mm     numeric(10,4),
    diametro_exterior_mm    numeric(10,4),
    longitud_libre_mm       numeric(10,4),
    material                text,
    carga_n                 numeric(12,4),
    estatus                 text NOT NULL DEFAULT 'Activo'
                      CHECK (estatus IN ('Activo','Inactivo')),
    -- ficha de ingeniería
    material_id             bigint,
    diametro_interior_mm    numeric(10,4),
    diametro_medio_mm       numeric(10,4),
    altura_solida_mm        numeric(10,4),
    paso_mm                 numeric(10,4),
    numero_espiras_totales  numeric(8,2),
    numero_espiras_activas  numeric(8,2),
    tipo_extremos           text,
    sentido_enrollado       text,
    constante_resorte_n_mm  numeric(12,4),
    carga1_n                numeric(12,4),
    carga1_altura_mm        numeric(10,4),
    carga2_n                numeric(12,4),
    carga2_altura_mm        numeric(10,4),
    tolerancias             text,
    norma                   text,
    requiere_cert           boolean NOT NULL DEFAULT false,
    descripcion             text,
    creado_en               timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 2. clientes: columnas nuevas
-- ---------------------------------------------------------------------
-- `payment_terms` ya existe y se conserva tal cual: guarda la etiqueta
-- ('Net 30 Days'). `condicion_pago_id` la normaliza contra el catálogo.
ALTER TABLE clientes
    ADD COLUMN IF NOT EXISTS codigo_legado     text,
    ADD COLUMN IF NOT EXISTS nombre_legado     text,
    ADD COLUMN IF NOT EXISTS origen            text,
    ADD COLUMN IF NOT EXISTS condicion_pago_id bigint,
    ADD COLUMN IF NOT EXISTS moneda            char(3) NOT NULL DEFAULT 'USD',
    ADD COLUMN IF NOT EXISTS incoterm          text,
    ADD COLUMN IF NOT EXISTS rep_usuario_id    bigint,
    ADD COLUMN IF NOT EXISTS industria         text,
    ADD COLUMN IF NOT EXISTS notas             text,
    ADD COLUMN IF NOT EXISTS actualizado_en    timestamptz NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS ix_clientes_razon  ON clientes (lower(razon_social));
CREATE INDEX IF NOT EXISTS ix_clientes_legado ON clientes (codigo_legado);

-- ---------------------------------------------------------------------
-- 3. rfqs: columnas nuevas
-- ---------------------------------------------------------------------
-- La tabla CONSERVA su nombre. `rfq_historial`, `rfq_id` y
-- repositorio_rfq.py ya usan ese vocabulario; renombrarla habría roto
-- código sin mejorar el modelo.
--
-- Solo se le agrega lo que le falta. `datos_json` cubre lo que el DER
-- llamaba variables_json, y `fecha_registro` lo que llamaba
-- fecha_solicitud: no se duplican.
ALTER TABLE rfqs
    ADD COLUMN IF NOT EXISTS resorte_id        bigint,
    ADD COLUMN IF NOT EXISTS cantidad          numeric(14,2),
    ADD COLUMN IF NOT EXISTS veredicto_sistema text,
    ADD COLUMN IF NOT EXISTS veredicto_final   text,
    ADD COLUMN IF NOT EXISTS score             numeric(6,2),
    ADD COLUMN IF NOT EXISTS notas             text;

CREATE INDEX IF NOT EXISTS ix_rfqs_cliente
    ON rfqs (cliente_id, fecha_registro DESC);

-- ---------------------------------------------------------------------
-- 4. resortes_cotizacion: la FK que le falta  (tabla de Ana)
-- ---------------------------------------------------------------------
ALTER TABLE resortes_cotizacion
    ADD COLUMN IF NOT EXISTS resorte_id     bigint,
    ADD COLUMN IF NOT EXISTS modelo_version text;

-- ---------------------------------------------------------------------
-- 5. Llaves foráneas
-- ---------------------------------------------------------------------
-- `rfqs.cliente_id` no tenía FK. Si hay filas cuyo cliente no
-- existe en `clientes`, la restricción se salta y quedan listadas para
-- que las corrijan a mano.
DO $fks$
DECLARE huerfanos bigint;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_rfqs_resorte') THEN
        ALTER TABLE rfqs ADD CONSTRAINT fk_rfqs_resorte
            FOREIGN KEY (resorte_id) REFERENCES resortes(resorte_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_resortes_cotizacion_resorte') THEN
        ALTER TABLE resortes_cotizacion ADD CONSTRAINT fk_resortes_cotizacion_resorte
            FOREIGN KEY (resorte_id) REFERENCES resortes(resorte_id);
        RAISE NOTICE 'Cerrada la FK resortes_cotizacion.resorte_id -> resortes.';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_rfqs_cliente') THEN
        SELECT count(*) INTO huerfanos
        FROM   rfqs r
        WHERE  r.cliente_id IS NOT NULL
          AND  NOT EXISTS (SELECT 1 FROM clientes c WHERE c.cliente_id = r.cliente_id);
        IF huerfanos > 0 THEN
            RAISE WARNING 'rfqs tiene % filas con un cliente_id inexistente. '
                          'NO se creó la FK; corrígelas y vuelve a correr este script.', huerfanos;
        ELSE
            ALTER TABLE rfqs ADD CONSTRAINT fk_rfqs_cliente
                FOREIGN KEY (cliente_id) REFERENCES clientes(cliente_id);
            RAISE NOTICE 'Cerrada la FK rfqs.cliente_id -> clientes.';
        END IF;
    END IF;
END $fks$;

-- ---------------------------------------------------------------------
-- 6. Resultado
-- ---------------------------------------------------------------------
DO $resumen$
DECLARE faltante text;
BEGIN
    SELECT string_agg(t, ', ') INTO faltante
    FROM unnest(ARRAY['clientes','cliente_dominios','resortes',
                      'rfqs','resortes_cotizacion']) AS t
    WHERE to_regclass(t) IS NULL;
    IF faltante IS NOT NULL THEN
        RAISE EXCEPTION 'Siguen faltando: %', faltante;
    END IF;
    RAISE NOTICE 'Las 5 tablas del DER existen. Ya puedes correr 05_migracion_repo.sql.';
END $resumen$;

COMMIT;

-- =====================================================================
-- Para revertir:
--   ALTER TABLE rfqs DROP COLUMN resorte_id, DROP COLUMN cantidad,
--     DROP COLUMN veredicto_sistema, DROP COLUMN veredicto_final,
--     DROP COLUMN score, DROP COLUMN notas;
--   ALTER TABLE resortes_cotizacion DROP COLUMN resorte_id, DROP COLUMN modelo_version;
--   ALTER TABLE clientes DROP COLUMN codigo_legado, DROP COLUMN nombre_legado,
--     DROP COLUMN origen, DROP COLUMN condicion_pago_id, DROP COLUMN moneda,
--     DROP COLUMN incoterm, DROP COLUMN rep_usuario_id, DROP COLUMN industria,
--     DROP COLUMN notas, DROP COLUMN actualizado_en;
--   DROP TABLE resortes;
-- =====================================================================
