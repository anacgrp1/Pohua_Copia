-- Esquema para control de duplicados del cotizador
CREATE TABLE IF NOT EXISTS correos_procesados (
    id              SERIAL PRIMARY KEY,
    message_id      TEXT NOT NULL UNIQUE,
    remitente       TEXT,
    asunto          TEXT,
    fecha_correo    TEXT,
    fecha_registro  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índice para el conteo rápido por message-id
CREATE INDEX IF NOT EXISTS idx_correos_message_id
    ON correos_procesados (message_id);

-- Historial de RFQ: asocia cada correo (message-id) a un RFQ
CREATE TABLE IF NOT EXISTS rfq_historial (
    id              SERIAL PRIMARY KEY,
    rfq_id          TEXT NOT NULL,
    message_id      TEXT NOT NULL UNIQUE,
    asunto          TEXT,
    fecha_registro  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_historial_rfq ON rfq_historial (rfq_id);
CREATE INDEX IF NOT EXISTS idx_historial_msg ON rfq_historial (message_id);

-- Variables físicas del resorte extraídas del dibujo por el modelo de visión
CREATE TABLE IF NOT EXISTS resortes_cotizacion (
    id                      SERIAL PRIMARY KEY,
    rfq_id                  TEXT,
    message_id              TEXT,
    origen_archivo          TEXT,
    tipo_resorte            TEXT,
    material                TEXT,
    diametro_alambre_mm     NUMERIC,
    diametro_exterior_mm    NUMERIC,
    diametro_interior_mm    NUMERIC,
    diametro_medio_mm       NUMERIC,
    longitud_libre_mm       NUMERIC,
    numero_espiras_totales  NUMERIC,
    numero_espiras_activas  NUMERIC,
    paso_mm                 NUMERIC,
    sentido_enrollado       TEXT,
    tipo_extremos           TEXT,
    constante_resorte_n_mm  NUMERIC,
    acabado                 TEXT,
    cantidad                NUMERIC,
    unidad                  TEXT,
    confianza               NUMERIC,
    listo_para_cotizar      BOOLEAN,
    datos_json              JSONB,
    fecha_registro          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_resortes_rfq ON resortes_cotizacion (rfq_id);
CREATE INDEX IF NOT EXISTS idx_resortes_msg ON resortes_cotizacion (message_id);

-- Clientes: datos maestros del cliente (una fila por cliente). DER COT-86/87.
CREATE TABLE IF NOT EXISTS clientes (
    cliente_id        TEXT PRIMARY KEY,
    razon_social      TEXT NOT NULL,
    rfc               TEXT UNIQUE,
    correo_principal  TEXT,
    payment_terms     TEXT,
    codigo_termino_pago TEXT,
    tax_state         TEXT,
    origen_datos      TEXT,
    estatus           TEXT NOT NULL DEFAULT 'Activo'
                      CHECK (estatus IN ('Activo', 'Inactivo')),
    es_estrella       BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_registro    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Para asegurar que las columnas nuevas se agreguen si la tabla ya existía:
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS codigo_termino_pago TEXT;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS tax_state TEXT;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS origen_datos TEXT;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS es_estrella BOOLEAN NOT NULL DEFAULT FALSE;

-- Cliente_Dominios: dominios de correo por cliente (multi-dominio, COT-71).
-- Una fila por (cliente, dominio); un dominio identifica a un solo cliente.
CREATE TABLE IF NOT EXISTS cliente_dominios (
    id                SERIAL PRIMARY KEY,
    cliente_id        TEXT NOT NULL REFERENCES clientes (cliente_id),
    dominio           TEXT NOT NULL UNIQUE,
    fecha_registro    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cliente_dominios_dom ON cliente_dominios (LOWER(dominio));
CREATE INDEX IF NOT EXISTS idx_cliente_dominios_cli ON cliente_dominios (cliente_id);

-- RFQs: registro de solicitudes de cotización. Un mismo rfq_id puede tener
-- varias versiones (seguimiento/actualización de un proyecto existente); no
-- se duplica el RFQ, se abre una nueva versión vinculada al mismo id.
CREATE TABLE IF NOT EXISTS rfqs (
    id               SERIAL PRIMARY KEY,
    rfq_id           TEXT NOT NULL,
    version          INTEGER NOT NULL DEFAULT 1,
    cliente_id       TEXT,
    nombre_proyecto  TEXT,
    part_number      TEXT,
    volumen          TEXT,
    material         TEXT,
    estado           TEXT NOT NULL DEFAULT 'New',
    message_id       TEXT,
    datos_json       JSONB,
    fecha_registro   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (rfq_id, version)
);

CREATE INDEX IF NOT EXISTS idx_rfqs_rfq_id ON rfqs (rfq_id);

-- -----------------------------------------------------------------------------
-- Nuevos Catálogos y Tablas para Contactos y Direcciones
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS terminos_pago (
  codigo          TEXT PRIMARY KEY,
  etiqueta        TEXT NOT NULL,
  dias_netos      NUMERIC(6,1),
  descuento_pct   NUMERIC(6,2),
  dias_descuento  NUMERIC(6,1),
  es_prepago      BOOLEAN NOT NULL DEFAULT FALSE,
  nota            TEXT
);

CREATE TABLE IF NOT EXISTS puestos_contacto (
  nombre TEXT PRIMARY KEY,
  seq    INTEGER
);

CREATE TABLE IF NOT EXISTS cliente_direcciones (
  id             SERIAL PRIMARY KEY,
  cliente_id     TEXT NOT NULL REFERENCES clientes(cliente_id) ON UPDATE CASCADE ON DELETE CASCADE,
  direccion_bruta TEXT NOT NULL,
  calle          TEXT,
  ciudad         TEXT,
  codigo_estado  TEXT,
  codigo_postal  TEXT,
  pais           TEXT NOT NULL DEFAULT 'US',
  es_principal   BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE (cliente_id, direccion_bruta)
);
CREATE INDEX IF NOT EXISTS idx_cliente_direcciones_cli ON cliente_direcciones (cliente_id);
CREATE INDEX IF NOT EXISTS idx_cliente_direcciones_est ON cliente_direcciones (codigo_estado);

CREATE TABLE IF NOT EXISTS cliente_contactos (
  id              SERIAL PRIMARY KEY,
  cliente_id      TEXT NOT NULL REFERENCES clientes(cliente_id) ON UPDATE CASCADE ON DELETE CASCADE,
  direccion_id    INTEGER REFERENCES cliente_direcciones(id) ON DELETE SET NULL,
  nombre_completo TEXT,
  puesto          TEXT REFERENCES puestos_contacto(nombre) ON UPDATE CASCADE,
  telefono        TEXT,
  telefono_ext    TEXT,
  telefono_bruto  TEXT,
  es_cuenta_rol   BOOLEAN NOT NULL DEFAULT FALSE,
  es_activo       BOOLEAN NOT NULL DEFAULT TRUE,
  CHECK (nombre_completo IS NOT NULL OR telefono IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_cliente_contactos_cli ON cliente_contactos (cliente_id);
CREATE INDEX IF NOT EXISTS idx_cliente_contactos_nom ON cliente_contactos (lower(nombre_completo));

CREATE TABLE IF NOT EXISTS cliente_contacto_correos (
  id              SERIAL PRIMARY KEY,
  contacto_id     INTEGER NOT NULL REFERENCES cliente_contactos(id) ON DELETE CASCADE,
  correo          TEXT NOT NULL,
  es_principal    BOOLEAN NOT NULL DEFAULT FALSE,
  formato_valido  BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE UNIQUE INDEX IF NOT EXISTS udx_contacto_correo ON cliente_contacto_correos (contacto_id, lower(correo));
CREATE INDEX IF NOT EXISTS idx_contacto_correo_dir ON cliente_contacto_correos (lower(correo));

-- -----------------------------------------------------------------------------
-- Configuración para PostgREST
-- -----------------------------------------------------------------------------

-- Crear rol anónimo para PostgREST (si no existe, se hace un bloque anónimo para evitar error)
DO $$
BEGIN
  CREATE ROLE web_anon NOLOGIN;
EXCEPTION WHEN DUPLICATE_OBJECT THEN
  RAISE NOTICE 'Role web_anon already exists';
END
$$;

-- Dar permisos de uso del esquema público
GRANT USAGE ON SCHEMA public TO web_anon;

-- Dar permisos para leer y escribir en todas las tablas y secuencias
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO web_anon;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO web_anon;
