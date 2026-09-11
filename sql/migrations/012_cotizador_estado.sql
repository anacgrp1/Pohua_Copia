-- =====================================================================
-- 012 — El estado de la calculadora, en Neon
--
-- La calculadora guardaba su trabajo en un único fichero, ISC_V4_DATA.json,
-- dentro de una carpeta de OneDrive que cada persona conectaba a mano desde
-- su navegador. Funcionaba, pero traía tres problemas que no se arreglan
-- desde el navegador:
--
--   * quien no conectaba la carpeta trabajaba en LOCAL MODE, y sus
--     cotizaciones vivían sólo en su equipo hasta que alguien se acordaba;
--   * OneDrive entrega ficheros "en la nube" que aún no ha descargado, y el
--     propio código tiene reintentos y avisos para no machacarlos;
--   * no había forma de consultar nada desde el servidor: ni cuántas ofertas
--     hay, ni de quién, ni desde cuándo.
--
-- A partir de aquí ese fichero es una fila de esta tabla. La calculadora sigue
-- viendo un documento JSON —no se le cambia el formato ni una coma— pero quien
-- lo guarda es el Cotizador, contra Neon, con la sesión de Pohua.
--
-- POR QUÉ UN JSONB Y NO TABLAS NORMALIZADAS. Porque el documento es el estado
-- interno de otra aplicación, con su propia forma y su propio ritmo de
-- cambios: normalizarlo aquí obligaría a migrar esta base cada vez que la
-- calculadora añada un campo, y a mantener dos verdades del mismo dato. Las
-- tablas de costeo (007) son otra cosa: ésas SÍ son datos de ISC y viven
-- normalizadas. Pasar clientes y materiales de este documento a esas tablas
-- es el paso siguiente, y es una decisión aparte.
--
-- Idempotente: se puede aplicar las veces que haga falta.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- El documento vivo. Una sola fila, siempre.
-- ---------------------------------------------------------------------
-- El CHECK sobre la clave primaria es lo que garantiza "una sola": sin él,
-- un INSERT despistado crearía un segundo estado y a partir de ahí dos
-- personas verían cotizaciones distintas sin que nada fallara.
CREATE TABLE IF NOT EXISTS cotizador_estado (
    id            smallint     PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    documento     jsonb        NOT NULL,
    rev           bigint       NOT NULL DEFAULT 1,
    guardado_en   timestamptz  NOT NULL DEFAULT now(),
    guardado_por  text
);

COMMENT ON TABLE cotizador_estado IS
    'Estado de la calculadora de precios (antes ISC_V4_DATA.json en OneDrive). Una sola fila.';
COMMENT ON COLUMN cotizador_estado.rev IS
    'Sube en cada guardado. La calculadora lo sondea para enterarse de que otro guardó.';

-- ---------------------------------------------------------------------
-- El historial. Es la red de seguridad, no un lujo.
-- ---------------------------------------------------------------------
-- La carpeta de OneDrive daba versiones anteriores sin que nadie las pidiera,
-- y eso salvaba de un guardado malo. Al traernos el documento a una fila hay
-- que traerse también esa red: sin ella, un cliente que sobrescriba el estado
-- con basura borra el trabajo de todos y no hay dónde volver.
--
-- Guarda el documento ANTERIOR a cada guardado, así que la fila viva nunca
-- está duplicada aquí.
CREATE TABLE IF NOT EXISTS cotizador_estado_historial (
    id            bigserial    PRIMARY KEY,
    rev           bigint       NOT NULL,
    documento     jsonb        NOT NULL,
    guardado_en   timestamptz  NOT NULL,
    guardado_por  text,
    archivado_en  timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_cotizador_estado_historial_rev
    ON cotizador_estado_historial (rev DESC);

COMMENT ON TABLE cotizador_estado_historial IS
    'Cada versión anterior del estado. Sustituye al historial de versiones que daba OneDrive.';

-- ---------------------------------------------------------------------
-- Las ofertas en PDF
-- ---------------------------------------------------------------------
-- La calculadora escribía los PDF en QUOTES/<cliente>/ dentro de la carpeta
-- compartida. Aquí se guardan con el cliente y el nombre de fichero que ella
-- misma decide, para no cambiarle el flujo: sigue "guardando la oferta", sólo
-- que el archivador es la base.
CREATE TABLE IF NOT EXISTS cotizador_ofertas (
    id            bigserial    PRIMARY KEY,
    cliente       text         NOT NULL,
    subcarpeta    text,
    nombre        text         NOT NULL,
    contenido     bytea        NOT NULL,
    bytes         integer      NOT NULL,
    creado_en     timestamptz  NOT NULL DEFAULT now(),
    creado_por    text
);

CREATE INDEX IF NOT EXISTS ix_cotizador_ofertas_cliente
    ON cotizador_ofertas (cliente, creado_en DESC);

COMMENT ON TABLE cotizador_ofertas IS
    'PDF de oferta generados por la calculadora (antes QUOTES/<cliente>/ en la carpeta compartida).';

COMMIT;
