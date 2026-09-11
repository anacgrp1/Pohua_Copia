-- =====================================================================
-- Migración incremental sobre la base que YA existe en el repositorio
-- COT-86 / COT-87  ->  + extensión de costeo
-- =====================================================================
-- Este script NO crea clientes, cliente_dominios, resortes, rfqs ni
-- resortes_cotizacion: da por hecho que ya existen (paso 0).
-- Solo les AGREGA columnas (todas nullable o con DEFAULT) y crea las
-- tablas nuevas.
--
-- No se quita ni se renombra ninguna columna existente, así que el
-- código que hoy consulta esas tablas sigue funcionando igual.
--
-- Es idempotente: se puede correr dos veces sin error.
--
-- Antes de correrlo:
--   pg_dump -Fc -f respaldo_pre_costeo.dump <tu_base>
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 0. Verificación previa: las cinco tablas base deben existir
-- ---------------------------------------------------------------------
DO $verifica$
DECLARE faltante text;
BEGIN
    SELECT string_agg(t, ', ') INTO faltante
    FROM unnest(ARRAY['clientes','cliente_dominios','resortes',
                      'rfqs','resortes_cotizacion']) AS t
    WHERE to_regclass(t) IS NULL;
    IF faltante IS NOT NULL THEN
        RAISE EXCEPTION 'Faltan tablas base: %. Corre primero las migraciones de COT-86/87.', faltante;
    END IF;
END $verifica$;

-- ---------------------------------------------------------------------
-- 1. Catálogos que otras tablas necesitan primero
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS condiciones_pago (
    id             bigserial PRIMARY KEY,
    codigo         text NOT NULL UNIQUE,
    nombre         text NOT NULL,
    dias           integer,
    descuento_pct  numeric(5,2),
    descuento_dias integer,
    descripcion    text
);

CREATE TABLE IF NOT EXISTS roles (
    id          bigserial PRIMARY KEY,
    codigo      text NOT NULL UNIQUE,
    nombre      text NOT NULL,
    descripcion text
);

CREATE TABLE IF NOT EXISTS permisos (
    id          bigserial PRIMARY KEY,
    codigo      text NOT NULL UNIQUE,
    descripcion text
);

CREATE TABLE IF NOT EXISTS rol_permisos (
    rol_id     bigint NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permiso_id bigint NOT NULL REFERENCES permisos(id) ON DELETE CASCADE,
    PRIMARY KEY (rol_id, permiso_id)
);

CREATE TABLE IF NOT EXISTS usuarios (
    id            bigserial PRIMARY KEY,
    correo        text NOT NULL UNIQUE,
    nombre        text NOT NULL,
    rol_id        bigint NOT NULL REFERENCES roles(id),
    password_hash text,
    activo        boolean NOT NULL DEFAULT true,
    ultimo_acceso timestamptz,
    creado_en     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS proveedores (
    id           bigserial PRIMARY KEY,
    codigo       text NOT NULL UNIQUE,
    nombre       text NOT NULL,
    tipo         text NOT NULL DEFAULT 'OTRO'
                 CHECK (tipo IN ('ALAMBRE','EMPAQUE','RECUBRIMIENTO','OTRO')),
    contacto     text,
    correo       text,
    telefono     text,
    dias_entrega integer,
    activo       boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS materiales (
    id              bigserial PRIMARY KEY,
    codigo          text NOT NULL UNIQUE,
    nombre          text NOT NULL,
    astm            text,
    densidad_kg_m3  integer,
    d_min_mm        numeric(8,3),
    d_max_mm        numeric(8,3),
    temp_max_c      integer,
    factor_costo    numeric(8,3),
    fatiga          text,
    lleva_surcharge boolean NOT NULL DEFAULT false,
    nota            text,
    activo          boolean NOT NULL DEFAULT true
);

-- ---------------------------------------------------------------------
-- 2. Columnas nuevas en las tablas base  (nada se quita ni se renombra)
-- ---------------------------------------------------------------------
ALTER TABLE clientes
    ADD COLUMN IF NOT EXISTS codigo_legado         text,
    ADD COLUMN IF NOT EXISTS nombre_legado         text,
    ADD COLUMN IF NOT EXISTS origen                text,
    ADD COLUMN IF NOT EXISTS condicion_pago_id     bigint,
    ADD COLUMN IF NOT EXISTS moneda                char(3) NOT NULL DEFAULT 'USD',
    ADD COLUMN IF NOT EXISTS incoterm              text,
    ADD COLUMN IF NOT EXISTS rep_usuario_id        bigint,
    ADD COLUMN IF NOT EXISTS industria             text,
    ADD COLUMN IF NOT EXISTS notas                 text,
    ADD COLUMN IF NOT EXISTS actualizado_en        timestamptz NOT NULL DEFAULT now();

ALTER TABLE resortes
    ADD COLUMN IF NOT EXISTS material_id           bigint,
    ADD COLUMN IF NOT EXISTS diametro_interior_mm  numeric(10,4),
    ADD COLUMN IF NOT EXISTS diametro_medio_mm     numeric(10,4),
    ADD COLUMN IF NOT EXISTS altura_solida_mm      numeric(10,4),
    ADD COLUMN IF NOT EXISTS paso_mm               numeric(10,4),
    ADD COLUMN IF NOT EXISTS numero_espiras_totales numeric(8,2),
    ADD COLUMN IF NOT EXISTS numero_espiras_activas numeric(8,2),
    ADD COLUMN IF NOT EXISTS tipo_extremos         text,
    ADD COLUMN IF NOT EXISTS sentido_enrollado     text,
    ADD COLUMN IF NOT EXISTS constante_resorte_n_mm numeric(12,4),
    ADD COLUMN IF NOT EXISTS carga1_n              numeric(12,4),
    ADD COLUMN IF NOT EXISTS carga1_altura_mm      numeric(10,4),
    ADD COLUMN IF NOT EXISTS carga2_n              numeric(12,4),
    ADD COLUMN IF NOT EXISTS carga2_altura_mm      numeric(10,4),
    ADD COLUMN IF NOT EXISTS tolerancias           text,
    ADD COLUMN IF NOT EXISTS norma                 text,
    ADD COLUMN IF NOT EXISTS requiere_cert         boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS descripcion           text,
    ADD COLUMN IF NOT EXISTS creado_en             timestamptz NOT NULL DEFAULT now();

-- `origen_archivo` ya existe en el repositorio; solo falta esto:
ALTER TABLE resortes_cotizacion
    ADD COLUMN IF NOT EXISTS resorte_id            bigint,
    ADD COLUMN IF NOT EXISTS modelo_version        text;

-- FKs de las columnas recién agregadas
DO $fks$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_clientes_condicion') THEN
        ALTER TABLE clientes ADD CONSTRAINT fk_clientes_condicion
            FOREIGN KEY (condicion_pago_id) REFERENCES condiciones_pago(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_clientes_rep') THEN
        ALTER TABLE clientes ADD CONSTRAINT fk_clientes_rep
            FOREIGN KEY (rep_usuario_id) REFERENCES usuarios(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_resortes_material') THEN
        ALTER TABLE resortes ADD CONSTRAINT fk_resortes_material
            FOREIGN KEY (material_id) REFERENCES materiales(id);
    END IF;
END $fks$;

-- cotizaciones apunta a (rfq_id, version): esa pareja debe ser única.
-- Si COT-86 ya la declaró, este bloque no hace nada.
DO $uq$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = 'rfqs' AND c.contype = 'u'
          AND c.conkey @> ARRAY[
              (SELECT attnum FROM pg_attribute WHERE attrelid = t.oid AND attname = 'rfq_id'),
              (SELECT attnum FROM pg_attribute WHERE attrelid = t.oid AND attname = 'version')]
    ) THEN
        ALTER TABLE rfqs ADD CONSTRAINT uq_rfqs_rfq_version
            UNIQUE (rfq_id, version);
    END IF;
END $uq$;

-- ---------------------------------------------------------------------
-- 3. Maestro comercial
-- ---------------------------------------------------------------------
-- cliente_contactos y cliente_direcciones NO se definen aquí.
--
-- Las crea sql/schema.sql, y con otras columnas: `nombre_completo`,
-- `es_cuenta_rol`, `es_activo` en contactos; `es_principal` y
-- `direccion_bruta` en direcciones.  Esta migración las volvía a declarar con
-- un CREATE TABLE IF NOT EXISTS y su propia lista de columnas: como la tabla ya
-- existía, el CREATE no hacía nada, pero la línea siguiente creaba un índice
-- sobre una columna (`principal`) que en la tabla real no existe.  Resultado:
-- la migración 005 abortaba justo aquí contra cualquier base creada desde
-- schema.sql, y todo lo que viene después — el catálogo de costeo entero:
-- maquinas, materiales, empaques, cotizaciones — no llegaba a crearse nunca.
--
-- La fuente de verdad de estas dos tablas es sql/schema.sql.

-- ---------------------------------------------------------------------
-- 4. Máquinas
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS familias_maquina (
    id            bigserial PRIMARY KEY,
    codigo        text NOT NULL UNIQUE,
    nombre        text NOT NULL,
    multiplicador numeric(8,4) NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS maquinas (
    id           bigserial PRIMARY KEY,
    codigo       text NOT NULL UNIQUE,
    nombre       text NOT NULL UNIQUE,
    familia_id   bigint NOT NULL REFERENCES familias_maquina(id),
    costo_compra numeric(14,2),
    anios_amort  integer,
    horas_anio   integer,
    carga_pct    numeric(6,4),
    oee          numeric(6,4),
    horas_labor  numeric(8,2),
    horas_setup  numeric(8,2),
    clase_setup  text,
    pph_default  integer,
    activo       boolean NOT NULL DEFAULT true,
    creada_en    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS maquina_capacidades (
    maquina_id      bigint PRIMARY KEY REFERENCES maquinas(id) ON DELETE CASCADE,
    alambre_min_mm  numeric(8,3),
    alambre_max_mm  numeric(8,3),
    od_max_mm       numeric(8,3),
    hace_compresion boolean,
    hace_extension  boolean,
    hace_torsion    boolean,
    usos            text,
    riesgos         text
);

CREATE TABLE IF NOT EXISTS maquina_tarifas (
    id             bigserial PRIMARY KEY,
    maquina_id     bigint NOT NULL REFERENCES maquinas(id) ON DELETE CASCADE,
    costo_hora     numeric(12,4),
    ccv_objetivo_h numeric(12,4),
    vigente_desde  date NOT NULL,
    vigente_hasta  date,
    creada_por     bigint REFERENCES usuarios(id),
    CONSTRAINT ck_tarifa_rango CHECK (vigente_hasta IS NULL OR vigente_hasta > vigente_desde)
);
CREATE INDEX IF NOT EXISTS ix_maquina_tarifas ON maquina_tarifas (maquina_id, vigente_desde DESC);

-- ---------------------------------------------------------------------
-- 5. Precios de material
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS material_precios (
    id             bigserial PRIMARY KEY,
    material_id    bigint NOT NULL REFERENCES materiales(id),
    diam_pulg      numeric(8,4) NOT NULL,
    precio_lb      numeric(12,4) NOT NULL,
    cantidad_lb    numeric(12,2),
    fecha_cotizado date NOT NULL,
    proveedor_id   bigint REFERENCES proveedores(id),
    origen         text,
    pos_legado     integer,
    creado_en      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (material_id, diam_pulg, fecha_cotizado, proveedor_id)
);
CREATE INDEX IF NOT EXISTS ix_material_precios
    ON material_precios (material_id, diam_pulg, fecha_cotizado DESC);

CREATE TABLE IF NOT EXISTS material_precio_proveedores (
    material_precio_id bigint NOT NULL REFERENCES material_precios(id) ON DELETE CASCADE,
    proveedor_id       bigint NOT NULL REFERENCES proveedores(id),
    PRIMARY KEY (material_precio_id, proveedor_id)
);

CREATE TABLE IF NOT EXISTS aleacion_surcharges (
    id              bigserial PRIMARY KEY,
    material_id     bigint REFERENCES materiales(id),
    codigo_aleacion text NOT NULL,
    etiqueta        text NOT NULL,
    precio_lb       numeric(12,4) NOT NULL,
    vigente_desde   date NOT NULL,
    vigente_hasta   date,
    publicado_en    date,
    nota            text,
    UNIQUE (codigo_aleacion, vigente_desde)
);

CREATE OR REPLACE VIEW v_material_precio_vigente AS
SELECT DISTINCT ON (material_id, diam_pulg)
       material_id, diam_pulg, precio_lb, fecha_cotizado, proveedor_id
FROM   material_precios
ORDER  BY material_id, diam_pulg, fecha_cotizado DESC, id DESC;

CREATE OR REPLACE VIEW v_material_precio_stats AS
SELECT material_id,
       diam_pulg,
       min(precio_lb) AS precio_min,
       max(precio_lb) AS precio_max,
       sum(precio_lb * coalesce(cantidad_lb,0))
         / nullif(sum(coalesce(cantidad_lb,0)),0) AS precio_promedio_pond,
       count(*)            AS num_cotizaciones,
       max(fecha_cotizado) AS ultima_fecha
FROM   material_precios
GROUP  BY material_id, diam_pulg;

-- ---------------------------------------------------------------------
-- 6. Acabados, subcontratación y empaque
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS acabados (
    id          bigserial PRIMARY KEY,
    codigo      text NOT NULL UNIQUE,
    nombre      text NOT NULL,
    descripcion text,
    activo      boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS acabado_alias (
    id         bigserial PRIMARY KEY,
    acabado_id bigint NOT NULL REFERENCES acabados(id) ON DELETE CASCADE,
    alias      text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS subcontratistas (
    id             bigserial PRIMARY KEY,
    proveedor_id   bigint NOT NULL UNIQUE REFERENCES proveedores(id),
    viaje_usd      numeric(12,2),
    tarima_max_lb  numeric(12,2),
    certs_usd      numeric(12,2),
    strip_lb       numeric(12,4),
    fecha_cotizado date
);

CREATE TABLE IF NOT EXISTS subcontratista_servicios (
    id                bigserial PRIMARY KEY,
    subcontratista_id bigint NOT NULL REFERENCES subcontratistas(id) ON DELETE CASCADE,
    acabado_id        bigint REFERENCES acabados(id),
    etiqueta          text NOT NULL,
    minimo_usd        numeric(12,2),
    precio_lb         numeric(12,4),
    precio_pieza      numeric(12,4),
    vigente_desde     date NOT NULL,
    vigente_hasta     date,
    UNIQUE (subcontratista_id, etiqueta, vigente_desde)
);

CREATE TABLE IF NOT EXISTS empaques (
    id              bigserial PRIMARY KEY,
    codigo          text NOT NULL UNIQUE,
    descripcion     text NOT NULL,
    proveedor_id    bigint REFERENCES proveedores(id),
    precio          numeric(12,4),
    unidad          text,
    piezas_por_caja integer,
    vigente_desde   date,
    activo          boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS historial_plating (
    id                bigserial PRIMARY KEY,
    num_parte         text,
    cliente_id        text REFERENCES clientes(cliente_id),
    cliente_texto     text,
    acabado_id        bigint REFERENCES acabados(id),
    acabado_texto     text,
    precio_lb         numeric(12,4),
    minimo_usd        numeric(12,2),
    fecha_cotizado    date,
    nota_origen       text,
    requiere_revision boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS ix_historial_plating_parte ON historial_plating (num_parte);

-- ---------------------------------------------------------------------
-- 7. Parámetros versionados
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS param_juegos (
    id            bigserial PRIMARY KEY,
    nombre        text NOT NULL,
    vigente_desde date NOT NULL,
    vigente_hasta date,
    creado_por    bigint REFERENCES usuarios(id),
    creado_en     timestamptz NOT NULL DEFAULT now(),
    nota          text
);

CREATE TABLE IF NOT EXISTS param_valores (
    param_juego_id bigint NOT NULL REFERENCES param_juegos(id) ON DELETE CASCADE,
    clave          text   NOT NULL,
    valor          jsonb  NOT NULL,
    PRIMARY KEY (param_juego_id, clave)
);

-- ---------------------------------------------------------------------
-- 8. Costeo
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cotizaciones (
    id                bigserial PRIMARY KEY,
    rfq_id            text NOT NULL,
    version           integer NOT NULL,
    numero            text NOT NULL,
    cliente_id        text NOT NULL REFERENCES clientes(cliente_id),
    estado            text NOT NULL DEFAULT 'BORRADOR'
                      CHECK (estado IN ('BORRADOR','APROBADA','SUSTITUIDA','CANCELADA')),
    resultado         text NOT NULL DEFAULT 'PENDIENTE'
                      CHECK (resultado IN ('PENDIENTE','PO_RECIBIDA','SIN_RESPUESTA','PERDIDA')),
    intencion_compra  text NOT NULL DEFAULT 'PENDIENTE'
                      CHECK (intencion_compra IN ('PENDIENTE','SI','NO')),
    rep_usuario_id    bigint REFERENCES usuarios(id),
    rep_nombre        text,
    condicion_pago_id bigint REFERENCES condiciones_pago(id),
    fecha_rfq         date,
    valida_hasta      date,
    dias_entrega      integer,
    descripcion       text,
    revision          text,
    moneda            char(3) NOT NULL DEFAULT 'USD',
    contribucion_pct  numeric(6,2),
    param_juego_id    bigint REFERENCES param_juegos(id),
    sustituida_por    bigint REFERENCES cotizaciones(id),
    motivo_perdida    text,
    precio_competidor numeric(14,4),
    creada_en         timestamptz NOT NULL,
    creada_por        bigint REFERENCES usuarios(id),
    aprobada_en       timestamptz,
    aprobada_por      bigint REFERENCES usuarios(id),
    actualizada_en    timestamptz NOT NULL DEFAULT now(),
    json_legado       jsonb,
    UNIQUE (numero, version),
    CONSTRAINT fk_cotizacion_rfq FOREIGN KEY (rfq_id, version)
        REFERENCES rfqs(rfq_id, version),
    CONSTRAINT ck_cotizacion_aprobada
        CHECK (estado <> 'APROBADA' OR aprobada_en IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_cotizaciones_cliente ON cotizaciones (cliente_id, creada_en DESC);
CREATE INDEX IF NOT EXISTS ix_cotizaciones_estado  ON cotizaciones (estado, resultado);

CREATE TABLE IF NOT EXISTS cotizacion_secuencias (
    anio          integer NOT NULL,
    segmento      text    NOT NULL,
    ultimo_numero integer NOT NULL DEFAULT 0,
    PRIMARY KEY (anio, segmento)
);

CREATE TABLE IF NOT EXISTS cotizacion_partidas (
    id                    bigserial PRIMARY KEY,
    cotizacion_id         bigint NOT NULL REFERENCES cotizaciones(id) ON DELETE CASCADE,
    renglon               integer NOT NULL,
    resorte_id            bigint REFERENCES resortes(resorte_id),
    num_parte             text,
    revision              text,
    descripcion           text,
    notas                 text,
    unidad                text NOT NULL DEFAULT 'pc',
    material_id           bigint REFERENCES materiales(id),
    diam_pulg             numeric(8,4),
    peso_lb               numeric(12,5),
    precio_base_lb        numeric(12,4),
    surcharge_lb          numeric(12,4),
    transporte_lb         numeric(12,4),
    markup_pct            numeric(6,2),
    moq_lb                numeric(12,2),
    long_desarrollo_pulg  numeric(12,4),
    escalon_elegido       integer,
    escalon_ops           integer,
    overhead_override_pct numeric(6,2),
    observaciones         text,
    UNIQUE (cotizacion_id, renglon)
);
CREATE INDEX IF NOT EXISTS ix_cotizacion_partidas_parte ON cotizacion_partidas (num_parte);

CREATE TABLE IF NOT EXISTS partida_costos (
    id          bigserial PRIMARY KEY,
    partida_id  bigint NOT NULL REFERENCES cotizacion_partidas(id) ON DELETE CASCADE,
    tipo        text NOT NULL CHECK (tipo IN ('COMPONENTE','CONSUMIBLE')),
    seq         integer NOT NULL,
    descripcion text,
    usd         numeric(12,4),
    UNIQUE (partida_id, tipo, seq)
);

CREATE TABLE IF NOT EXISTS cotizacion_escalones (
    id                      bigserial PRIMARY KEY,
    partida_id              bigint NOT NULL REFERENCES cotizacion_partidas(id) ON DELETE CASCADE,
    escalon                 integer NOT NULL,
    cantidad                integer,
    es_borrador             boolean NOT NULL DEFAULT false,
    lote_produccion         integer,
    modo_moq                text NOT NULL DEFAULT 'SHIP' CHECK (modo_moq IN ('SHIP','STORE')),
    precio_override         numeric(14,4),
    descartado              boolean NOT NULL DEFAULT false,
    contribucion_pct        numeric(6,2),
    overhead_pct            numeric(6,2),
    herramental_desc        text,
    herramental_costo       numeric(14,2),
    herramental_amort_qty   integer,
    herramental_del_cliente boolean NOT NULL DEFAULT false,
    empaque_id              bigint REFERENCES empaques(id),
    piezas_por_caja         integer,
    sub_servicio_id         bigint REFERENCES subcontratista_servicios(id),
    sub_proveedor_texto     text,
    sub_servicio_texto      text,
    sub_minimo_usd          numeric(12,2),
    sub_precio_lb           numeric(12,4),
    sub_precio_pieza        numeric(12,4),
    precio_unitario         numeric(14,4),
    UNIQUE (partida_id, escalon),
    CONSTRAINT ck_escalon_cantidad CHECK (cantidad IS NULL OR cantidad > 0),
    CONSTRAINT ck_escalon_borrador CHECK (es_borrador = (cantidad IS NULL))
);

CREATE TABLE IF NOT EXISTS escalon_ruta (
    id           bigserial PRIMARY KEY,
    escalon_id   bigint NOT NULL REFERENCES cotizacion_escalones(id) ON DELETE CASCADE,
    seq          integer NOT NULL,
    maquina_id   bigint NOT NULL REFERENCES maquinas(id),
    horas_setup  numeric(10,4),
    pph          integer,
    horas_maq    numeric(12,4),
    horas_labor  numeric(10,4),
    ratio        numeric(8,4) NOT NULL DEFAULT 1,
    scrap_pct    numeric(6,2) NOT NULL DEFAULT 0,
    horas_obj    numeric(12,4),
    horas_reales numeric(12,4),
    es_copia     boolean NOT NULL DEFAULT true,
    UNIQUE (escalon_id, seq)
);
CREATE INDEX IF NOT EXISTS ix_escalon_ruta_maquina ON escalon_ruta (maquina_id);

-- ---------------------------------------------------------------------
-- 9. Detalle de la extracción IA y de la factibilidad
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS resortes_cotizacion_campos (
    id            bigserial PRIMARY KEY,
    extraccion_id bigint NOT NULL REFERENCES resortes_cotizacion(id) ON DELETE CASCADE,
    clave         text NOT NULL,
    etiqueta      text,
    valor         text,
    unidad        text,
    confianza     numeric(5,4),
    caja          numeric(10,8)[],
    recorte_path  text,
    aceptado      boolean
);
CREATE INDEX IF NOT EXISTS ix_extraccion_campos ON resortes_cotizacion_campos (extraccion_id, clave);

CREATE TABLE IF NOT EXISTS rfq_banderas (
    id             bigserial PRIMARY KEY,
    rfq_version_id bigint NOT NULL REFERENCES rfqs(id) ON DELETE CASCADE,
    nivel          text NOT NULL CHECK (nivel IN ('ok','info','warn','crit')),
    titulo         text NOT NULL
);

-- ---------------------------------------------------------------------
-- 10. Documentos, órdenes de compra y bitácora
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cotizacion_documentos (
    id            bigserial PRIMARY KEY,
    cotizacion_id bigint NOT NULL REFERENCES cotizaciones(id) ON DELETE CASCADE,
    tipo          text NOT NULL
                  CHECK (tipo IN ('PDF_COTIZACION','DIBUJO_CLIENTE','PO','OTRO')),
    archivo       text NOT NULL,
    ruta          text NOT NULL,
    sha256        text,
    bytes         bigint,
    subido_en     timestamptz NOT NULL DEFAULT now(),
    subido_por    bigint REFERENCES usuarios(id)
);
CREATE INDEX IF NOT EXISTS ix_cotizacion_documentos ON cotizacion_documentos (cotizacion_id, tipo);

CREATE TABLE IF NOT EXISTS ordenes_compra (
    id            bigserial PRIMARY KEY,
    cotizacion_id bigint REFERENCES cotizaciones(id),
    cliente_id    text NOT NULL REFERENCES clientes(cliente_id),
    num_orden     text NOT NULL,
    recibida_en   date NOT NULL,
    moneda        char(3) NOT NULL DEFAULT 'USD',
    nota          text,
    UNIQUE (cliente_id, num_orden)
);

CREATE TABLE IF NOT EXISTS orden_compra_lineas (
    id              bigserial PRIMARY KEY,
    orden_id        bigint NOT NULL REFERENCES ordenes_compra(id) ON DELETE CASCADE,
    partida_id      bigint REFERENCES cotizacion_partidas(id),
    num_parte       text,
    cantidad        integer NOT NULL,
    precio_unitario numeric(14,4) NOT NULL,
    fecha_promesa   date
);

CREATE TABLE IF NOT EXISTS bitacora (
    id            bigserial PRIMARY KEY,
    ocurrido_en   timestamptz NOT NULL DEFAULT now(),
    usuario_id    bigint REFERENCES usuarios(id),
    usuario_texto text,
    area          text,
    entidad       text,
    entidad_id    text,
    accion        text,
    detalle       text,
    antes_json    jsonb,
    despues_json  jsonb
);
CREATE INDEX IF NOT EXISTS ix_bitacora_fecha   ON bitacora (ocurrido_en DESC);
CREATE INDEX IF NOT EXISTS ix_bitacora_entidad ON bitacora (entidad, entidad_id);

-- ---------------------------------------------------------------------
-- 11. Disparador de actualizado_en en clientes
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION toca_actualizado() RETURNS trigger AS $fn$
BEGIN
    NEW.actualizado_en = now();
    RETURN NEW;
END $fn$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION toca_actualizada() RETURNS trigger AS $fn$
BEGIN
    NEW.actualizada_en = now();
    RETURN NEW;
END $fn$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tg_clientes_toca ON clientes;
CREATE TRIGGER tg_clientes_toca BEFORE UPDATE ON clientes
    FOR EACH ROW EXECUTE FUNCTION toca_actualizado();

DROP TRIGGER IF EXISTS tg_cotizaciones_toca ON cotizaciones;
CREATE TRIGGER tg_cotizaciones_toca BEFORE UPDATE ON cotizaciones
    FOR EACH ROW EXECUTE FUNCTION toca_actualizada();

COMMIT;

-- =====================================================================
-- Para revertir por completo:
--
--   BEGIN;
--   DROP TABLE IF EXISTS orden_compra_lineas, ordenes_compra, bitacora,
--     cotizacion_documentos, rfq_banderas, resortes_cotizacion_campos,
--     escalon_ruta, cotizacion_escalones, partida_costos,
--     cotizacion_partidas, cotizacion_secuencias, cotizaciones,
--     param_valores, param_juegos, historial_plating, empaques,
--     subcontratista_servicios, subcontratistas, acabado_alias, acabados,
--     aleacion_surcharges, material_precio_proveedores, material_precios,
--     maquina_tarifas, maquina_capacidades, maquinas, familias_maquina,
--     cliente_direcciones, cliente_contactos, materiales, proveedores,
--     usuarios, rol_permisos, permisos, roles, condiciones_pago CASCADE;
--   ALTER TABLE clientes DROP COLUMN IF EXISTS nombre_legado, ... ;
--   COMMIT;
-- =====================================================================
