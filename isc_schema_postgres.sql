-- =====================================================================================
--  ISC / CGR INTERNATIONAL  --  ESQUEMA POSTGRESQL
--
--  Extraido de:
--    * ISC Price Calculator V7 to Automate DEMO.html   (BRAIN 18.0.1-DEMO, build 2026-07-14)
--    * Spring Engineering Calculator.html
--  Generado: 2026-09-01
--
--  Contenido:
--    0. Esquema, tipos y dominios
--    1. Seguridad y parametros globales
--    2. Catalogos maestros (clientes, materiales, precios, maquinas, subcontratacion,
--       empaque, historico de plating)
--    3. Reglas de negocio (BRAIN) y motores de sugerencia (routing / packing)
--    4. Base de ingenieria del Spring Engineering Calculator
--    5. Modelo transaccional de cotizaciones (quote -> PN -> tier -> operacion)
--    6. Resultados de calculo, banderas, feasibility, Delta Won, bitacora, locks
--    7. Vistas de consulta
--    8. DATOS SEMILLA (todo lo extraido de ambas calculadoras)
--
--  Uso:   psql -U <usuario> -d <base> -v ON_ERROR_STOP=1 -f isc_schema_postgres.sql
--  Nota:  el script arranca con DROP SCHEMA isc CASCADE. Comenta esa linea si ya
--         tienes datos productivos en el esquema.
-- =====================================================================================

\set ON_ERROR_STOP on
BEGIN;

-- ------------------------------------------------------------------ 0. ESQUEMA
DROP SCHEMA IF EXISTS isc CASCADE;
CREATE SCHEMA isc;
SET search_path = isc, public;

COMMENT ON SCHEMA isc IS 'ISC Price Calculator V7 + Spring Engineering Calculator - CGR International';

CREATE TYPE user_role       AS ENUM ('ADMIN','QUOTE');
CREATE TYPE machine_family  AS ENUM ('COILER','SECONDARY');
CREATE TYPE spring_type     AS ENUM ('compression','extension','torsion','wireform');
CREATE TYPE quote_status    AS ENUM ('DRAFT','APPROVED','SUPERSEDED');
CREATE TYPE quote_outcome   AS ENUM ('PO RECEIVED','LOST','NO RECEPTION');
CREATE TYPE moq_mode        AS ENUM ('SHIP','STORE');
CREATE TYPE flag_level      AS ENUM ('err','warn','info','ok');
CREATE TYPE setup_class     AS ENUM ('Low','Medium','High');
CREATE TYPE price_unit      AS ENUM ('pc','lb');
CREATE TYPE brain_category  AS ENUM ('CGR_INTERNATIONAL','CGR_ISC','CALC_RULES');

CREATE DOMAIN pct    AS numeric(9,4);
CREATE DOMAIN usd    AS numeric(16,6);
CREATE DOMAIN usd_pc AS numeric(16,6);

-- ============================================================ 1. SEGURIDAD / PARAMETROS
CREATE TABLE app_user (
  id          serial PRIMARY KEY,
  email       text        NOT NULL UNIQUE,
  full_name   text        NOT NULL,
  role        user_role   NOT NULL DEFAULT 'QUOTE',
  pw_hash     text,                       -- FNV-1a doble (hashPw de la app)
  is_active   boolean     NOT NULL DEFAULT TRUE,
  created_at  timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE app_user IS 'Usuarios de la app. ADMIN aprueba cotizaciones; QUOTE captura.';

-- Parametros globales de precio (DEFAULT_PARAMS + machineParams). Fila unica.
CREATE TABLE pricing_param (
  id                        smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  mat_markup_pct            pct NOT NULL DEFAULT 6,     -- materiales
  comp_markup_pct           pct NOT NULL DEFAULT 6,     -- componentes
  cons_markup_pct           pct NOT NULL DEFAULT 6,     -- consumibles
  sub_markup_pct            pct NOT NULL DEFAULT 50,    -- subcontratacion
  contribution_pct          pct NOT NULL DEFAULT 20,    -- contribucion sobre precio de venta
  hq_pct                    pct NOT NULL DEFAULT 5,     -- costo corporativo
  commission_nic_pct        pct NOT NULL DEFAULT 5,     -- solo si el rep es Nic Scherer
  oh_ladder_pct             pct[] NOT NULL,             -- overheads por numero de operaciones
  oh_sub_pct                pct NOT NULL DEFAULT 35,    -- overhead cuando hay subcontratacion
  oh_min_pct                pct NOT NULL DEFAULT 10,
  oh_max_pct                pct NOT NULL DEFAULT 35,
  floor_base_usd            usd NOT NULL DEFAULT 800,   -- piso de trabajo (primera operacion)
  floor_per_op_usd          usd NOT NULL DEFAULT 200,   -- piso por operacion adicional
  scrap_default_pct         pct NOT NULL DEFAULT 5,
  wire_max_in               numeric(8,4) NOT NULL DEFAULT 0.59,  -- limite de factibilidad ISC
  coiler_mult               numeric(6,3) NOT NULL DEFAULT 3,
  secondary_mult            numeric(6,3) NOT NULL DEFAULT 5,
  plating_surcharge_per_pn  usd NOT NULL DEFAULT 30,
  updated_at                timestamptz NOT NULL DEFAULT now()
);
COMMENT ON COLUMN pricing_param.oh_ladder_pct IS
  'Overheads segun numero de operaciones: indice 1 = 1 op, 2 = 2 ops, 3 = 3 ops, 4 = 4 o mas.';
COMMENT ON COLUMN pricing_param.floor_base_usd IS
  'Piso ISC: ningun trabajo por debajo de 800 USD; cada operacion adicional suma 200 USD.';

-- Opciones permitidas de scrap
CREATE TABLE scrap_option (
  scrap_pct  pct PRIMARY KEY,
  is_flagged boolean NOT NULL DEFAULT FALSE   -- arriba de 5 por ciento se marca
);

-- Tarifas de mano de obra por familia de maquina
CREATE TABLE labor_rate (
  family      machine_family PRIMARY KEY,
  usd_per_h   usd NOT NULL,
  effective   date,
  note        text
);

-- ============================================================ 2. CATALOGOS MAESTROS
CREATE TABLE customer (
  code        text PRIMARY KEY,
  name        text NOT NULL,
  terms       text NOT NULL DEFAULT 'Net 30',
  is_active   boolean NOT NULL DEFAULT TRUE,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_customer_name ON customer (lower(name));

-- Leyenda de codigos de material usados por ISC (materialLegend + WIRE_DENS)
CREATE TABLE material_legend (
  code            text PRIMARY KEY,
  description     text NOT NULL,
  density_lb_in3  numeric(10,5)      -- densidad usada para el peso de wire forms
);
COMMENT ON COLUMN material_legend.density_lb_in3 IS
  'Peso de wire form = pi/4 * diametro^2 * longitud desarrollada * densidad. Default 0.284 lb/in3.';

-- Ficha tecnica resumida por material (matReference del BRAIN)
CREATE TABLE material_reference (
  id             serial PRIMARY KEY,
  name           text NOT NULL UNIQUE,
  astm           text,
  density_kg_m3  numeric(10,2),
  d_min_mm       numeric(8,3),
  d_max_mm       numeric(8,3),
  temp_max_c     numeric(8,2),
  cost_factor    numeric(8,3),
  fatigue        text,
  note           text
);

-- Historico de precios de alambre por codigo + diametro (materialPrices)
CREATE TABLE material_price (
  id             bigserial PRIMARY KEY,
  material_code  text NOT NULL REFERENCES material_legend(code) ON UPDATE CASCADE,
  dia_in         numeric(9,4) NOT NULL,
  latest_usd_lb  usd,
  wavg_usd_lb    usd,
  min_usd_lb     usd,
  max_usd_lb     usd,
  positions      integer,           -- numero de compras en el historico
  qty_lb         numeric(14,3),
  price_date     date,
  supplier       text,
  UNIQUE (material_code, dia_in)
);
COMMENT ON TABLE material_price IS
  'La app sugiere precio por match exacto de diametro y, si no existe, por interpolacion log-lineal entre el diametro inmediato inferior y el superior; fuera de rango, extrapola y exige revision manual.';

-- Surcharge de aleacion por libra
CREATE TABLE surcharge (
  code                 text PRIMARY KEY,
  alloy                text NOT NULL,
  per_lb               usd,
  prev_per_lb          usd,
  effective_date       date,
  updated_date         date,
  applies_to_quote     boolean NOT NULL DEFAULT FALSE,  -- surchargeAppliesTo: SS, SS177, 316
  in_isc_material_list boolean NOT NULL DEFAULT TRUE,
  note                 text
);

-- Maquinas del taller
CREATE TABLE machine (
  id               serial PRIMARY KEY,
  name             text NOT NULL UNIQUE,
  family           machine_family NOT NULL,
  m1_code          text,                       -- codigo en el ERP M1
  setup_h          numeric(9,3),
  pph              numeric(12,3),              -- piezas por hora
  purchase_usd     usd,
  labor_usd_h      usd,
  amort_years      numeric(6,2),
  load_pct         numeric(6,3),
  hours_per_year   numeric(10,2),
  oee              numeric(6,4),
  cost_rate_usd_h  usd,                        -- costo maquina por hora
  ccv_target_usd_h usd,                        -- objetivo de C/CV por hora maquina
  wire_min_mm      numeric(8,3),
  wire_max_mm      numeric(8,3),
  od_max_mm        numeric(8,2),
  cap_compression  boolean,
  cap_extension    boolean,
  cap_torsion      boolean,
  setup_class      setup_class,
  uses             text,
  risk             text,
  is_active        boolean NOT NULL DEFAULT TRUE
);
COMMENT ON COLUMN machine.ccv_target_usd_h IS
  'Objetivo de contribucion sobre costos variables por hora maquina; la app compara el C/CV/h logrado contra este objetivo (ratio 1 = 100 por ciento).';

CREATE TABLE subcontractor (
  id            serial PRIMARY KEY,
  name          text NOT NULL UNIQUE,
  quote_date    date,
  certs_usd     usd,          -- costo de certificados
  loop_trip_usd usd,          -- transporte ida y vuelta por skid
  skid_max_lb   numeric(12,2),
  strip_per_lb  usd,
  is_active     boolean NOT NULL DEFAULT TRUE
);

CREATE TABLE subcontractor_service (
  id                serial PRIMARY KEY,
  subcontractor_id  integer NOT NULL REFERENCES subcontractor(id) ON DELETE CASCADE,
  service           text NOT NULL,
  min_usd           usd,
  per_lb            usd,
  per_pc            usd,
  UNIQUE (subcontractor_id, service)
);
COMMENT ON TABLE subcontractor_service IS
  'Costo por lote = MAX(min_usd, per_lb * lb del lote, per_pc * piezas del lote); despues se aplica el markup de subcontratacion (50 por ciento).';

-- Historico de acabados / plating cotizados por PN
CREATE TABLE plating_history (
  id             bigserial PRIMARY KEY,
  pn             text NOT NULL,
  customer_name  text,
  finish         text,
  per_lb         usd,
  raw_text       text,
  notes          text
);
CREATE INDEX ix_plating_pn ON plating_history (pn);

CREATE TABLE packing (
  id              serial PRIMARY KEY,
  code            text NOT NULL,          -- identificador textual usado por la app
  description     text,
  supplier        text,
  price_usd       usd,
  uom             text DEFAULT 'EACH',
  default_per_box integer,
  is_active       boolean NOT NULL DEFAULT TRUE,
  UNIQUE (code, description)
);

-- ============================================================ 3. REGLAS DE NEGOCIO (BRAIN)
CREATE TABLE brain_meta (
  id                     smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  version                text NOT NULL,
  built_at               date,
  banner                 text,
  offer_standard_remark  text
);

CREATE TABLE brain_rule (
  id        serial PRIMARY KEY,
  category  brain_category NOT NULL,
  seq       integer NOT NULL,
  rule_text text NOT NULL,
  UNIQUE (category, seq)
);

CREATE TABLE brain_glossary (
  term        text PRIMARY KEY,
  definition  text NOT NULL
);

CREATE TABLE brain_stage (
  key    text PRIMARY KEY,
  seq    integer NOT NULL,
  title  text NOT NULL
);

CREATE TABLE brain_stage_body (
  id         serial PRIMARY KEY,
  stage_key  text NOT NULL REFERENCES brain_stage(key) ON DELETE CASCADE,
  seq        integer NOT NULL,
  body_text  text NOT NULL,
  UNIQUE (stage_key, seq)
);

-- Descripciones de parte permitidas y su mapeo a tipo de resorte
CREATE TABLE part_description (
  description  text PRIMARY KEY,
  spring_type  spring_type,
  seq          integer
);

-- Motor "Suggest routing": carril de coiler por diametro de alambre
CREATE TABLE routing_lane (
  id            serial PRIMARY KEY,
  seq           integer NOT NULL UNIQUE,
  max_dia_in    numeric(9,4) NOT NULL,
  machine_name  text NOT NULL REFERENCES machine(name) ON UPDATE CASCADE,
  pph           numeric(12,2) NOT NULL
);
COMMENT ON TABLE routing_lane IS
  'Se elige el primer carril cuyo max_dia_in sea mayor o igual al diametro del alambre. Wire Form no usa carril: fuerza SIMPLEX MC 50 a 1000 pph.';

-- Cadena de operaciones secundarias sugeridas por familia de parte
CREATE TABLE routing_secondary (
  id                serial PRIMARY KEY,
  part_description  text NOT NULL REFERENCES part_description(description) ON UPDATE CASCADE,
  seq               integer NOT NULL,
  machine_name      text NOT NULL REFERENCES machine(name) ON UPDATE CASCADE,
  pph               numeric(12,2) NOT NULL,
  UNIQUE (part_description, seq)
);

-- Motor "Suggest packing": regla por peso enviado del tier
CREATE TABLE packing_rule (
  id                serial PRIMARY KEY,
  seq               integer NOT NULL UNIQUE,
  min_tier_lb       numeric(12,2),
  part_description  text REFERENCES part_description(description) ON UPDATE CASCADE,
  packing_code      text NOT NULL,
  target_box_lb     numeric(10,2) NOT NULL,
  note              text
);

-- ============================================================ 4. SPRING ENGINEERING CALCULATOR
CREATE TABLE spring_material (
  id            text PRIMARY KEY,
  name          text NOT NULL,
  astm          text,
  g_mpa         numeric(12,2) NOT NULL,   -- modulo de rigidez
  e_mpa         numeric(12,2) NOT NULL,   -- modulo de elasticidad
  density_kg_m3 numeric(10,2) NOT NULL,
  a_coef        numeric(12,3) NOT NULL,   -- Sut = a_coef / d^m_exp   (d en mm, Sut en MPa)
  m_exp         numeric(10,5) NOT NULL,
  d_min_mm      numeric(8,3),
  d_max_mm      numeric(8,3),
  temp_max_c    numeric(8,2),
  shear_fac     numeric(6,4) NOT NULL,    -- esfuerzo torsional admisible / Sut
  bend_fac      numeric(6,4) NOT NULL,    -- esfuerzo de flexion admisible / Sut
  cost_fac      numeric(8,3),
  fatigue       text,
  note          text,
  isc_material_code text REFERENCES material_legend(code) ON UPDATE CASCADE
);
COMMENT ON TABLE spring_material IS
  'Materiales del Spring Engineering Calculator. El diametro se acota a 0.05-30 mm antes de evaluar Sut.';

CREATE TABLE spring_machine (
  id              text PRIMARY KEY,
  name            text NOT NULL,
  wire_min_mm     numeric(8,3),
  wire_max_mm     numeric(8,3),
  od_max_mm       numeric(8,2),
  cap_compression boolean,
  cap_extension   boolean,
  cap_torsion     boolean,
  axes            text,
  setup_class     setup_class,
  uses            text,
  risk            text,
  machine_id      integer REFERENCES machine(id)   -- enlace a la maquina real del taller
);

CREATE TABLE spring_end_type (
  id         text PRIMARY KEY,
  label      text NOT NULL,
  end_coils  numeric(4,1) NOT NULL,
  is_ground  boolean NOT NULL
);

CREATE TABLE spring_hook_type (
  id            text PRIMARY KEY,
  label         text NOT NULL,
  turns_factor  numeric(6,3) NOT NULL   -- vueltas equivalentes que agrega el gancho
);

CREATE TABLE spring_score_band (
  id          serial PRIMARY KEY,
  min_score   integer NOT NULL,
  band        text NOT NULL,
  color_hex   text,
  description text
);

CREATE TABLE unit_conversion (
  kind        text NOT NULL,   -- len | force | stress | rate | moment | freq
  unit_system text NOT NULL,   -- in | mm
  factor      numeric(20,10) NOT NULL,   -- valor en SI * factor = valor mostrado
  label       text NOT NULL,
  PRIMARY KEY (kind, unit_system)
);

-- ============================================================ 5. COTIZACIONES
CREATE TABLE quote (
  id                text PRIMARY KEY,            -- id de la app (qXXXX) o uuid
  number            text NOT NULL,               -- AAAA-CLIENTE-SEQ
  version           integer NOT NULL DEFAULT 1,
  status            quote_status NOT NULL DEFAULT 'DRAFT',
  outcome           quote_outcome,
  customer_code     text REFERENCES customer(code) ON UPDATE CASCADE,
  rfq_date          date,
  sales_rep         text,
  payment_terms     text DEFAULT 'Net 30',
  lead_days         integer DEFAULT 45,
  will              text DEFAULT 'PENDING',      -- Stage 1: decision de cotizar
  contribution_pct  pct DEFAULT 20,
  created_at        timestamptz NOT NULL DEFAULT now(),
  created_by        text,
  approved_at       timestamptz,
  approved_by       text,
  pdf_path          text,
  is_deleted        boolean NOT NULL DEFAULT FALSE,
  deleted_at        timestamptz,
  deleted_by        text,
  UNIQUE (number, version)
);
CREATE INDEX ix_quote_customer ON quote (customer_code);
CREATE INDEX ix_quote_status   ON quote (status, outcome);
COMMENT ON COLUMN quote.will IS 'Stage 1 (Feasibility / Will): PENDING, YES o NO.';
COMMENT ON TABLE quote IS
  'Una cotizacion se registra en el log en el instante en que se crea. Aprobar la bloquea y genera el PDF; los cambios exigen una nueva version (la anterior queda SUPERSEDED). Solo un DRAFT puede borrarse.';

CREATE TABLE quote_part (
  id                bigserial PRIMARY KEY,
  quote_id          text NOT NULL REFERENCES quote(id) ON DELETE CASCADE,
  pn_index          integer NOT NULL,
  pn                text,
  description       text REFERENCES part_description(description) ON UPDATE CASCADE,
  revision          text,
  notes             text,                 -- notas internas, no salen en la oferta
  remarks           text,                 -- comentarios que SI se imprimen en la oferta
  unit              price_unit NOT NULL DEFAULT 'pc',
  oh_override_pct   pct,
  selected_tier     integer CHECK (selected_tier BETWEEN 1 AND 5),
  -- tarjeta de material
  material_code     text REFERENCES material_legend(code) ON UPDATE CASCADE,
  dia_in            numeric(9,4),
  weight_lb         numeric(14,6),
  dev_length_in     numeric(12,4),        -- longitud desarrollada (wire forms)
  base_per_lb       usd,
  surcharge_per_lb  usd,
  transport_per_lb  usd,
  mat_markup_pct    pct,
  moq_lb            numeric(14,3),
  -- componentes (2 lineas) y consumible (1 linea)
  component1_desc   text, component1_usd usd,
  component2_desc   text, component2_usd usd,
  consumable_desc   text, consumable_usd usd,
  UNIQUE (quote_id, pn_index)
);
CREATE INDEX ix_quote_part_pn ON quote_part (pn);

CREATE TABLE quote_part_drawing (
  quote_part_id  bigint PRIMARY KEY REFERENCES quote_part(id) ON DELETE CASCADE,
  spring_type    spring_type,
  file_name      text,
  ai_model       text,
  parsed_at      timestamptz DEFAULT now(),
  raw_payload    jsonb
);

CREATE TABLE quote_part_drawing_field (
  id             bigserial PRIMARY KEY,
  quote_part_id  bigint NOT NULL REFERENCES quote_part(id) ON DELETE CASCADE,
  field_key      text NOT NULL,   -- wireDia, od, id, meanDia, freeLength, bodyLength, coils, developedLength, material
  field_value    text,
  unit           text,            -- in | mm
  UNIQUE (quote_part_id, field_key)
);

CREATE TABLE quote_tier (
  id                   bigserial PRIMARY KEY,
  quote_part_id        bigint NOT NULL REFERENCES quote_part(id) ON DELETE CASCADE,
  tier_no              integer NOT NULL CHECK (tier_no BETWEEN 1 AND 5),
  qty                  numeric(16,2),
  price_override       usd_pc,
  is_killed            boolean NOT NULL DEFAULT FALSE,
  prod_batch           numeric(16,2),      -- piezas por lote de produccion: multiplica los setups
  moq_mode             moq_mode NOT NULL DEFAULT 'SHIP',
  ship_qty             numeric(16,2),
  contrib_pct          pct,                -- override de contribucion del tier
  oh_pct               pct,                -- override de overheads del tier
  -- herramental (pass-through, NRE amortizado)
  tooling_desc         text,
  tooling_cost         usd,
  tooling_amort_qty    numeric(16,2),
  -- subcontratacion
  sub_subcontractor_id integer REFERENCES subcontractor(id),
  sub_service          text,
  sub_min_usd          usd,
  sub_per_lb           usd,
  sub_per_pc           usd,
  sub_parts_per_batch  numeric(16,2),
  sub_share_skid       boolean NOT NULL DEFAULT FALSE,
  -- empaque
  packing_id           integer REFERENCES packing(id),
  packing_qty_per_box  numeric(12,2),
  UNIQUE (quote_part_id, tier_no)
);
COMMENT ON COLUMN quote_tier.moq_mode IS
  'SHIP = MOQ a producir y embarcar en un solo envio. STORE = ISC produce todo, almacena y libera en embarques iguales al lote de produccion (maximo 3 meses de almacenaje).';

CREATE TABLE tier_operation (
  id             bigserial PRIMARY KEY,
  quote_tier_id  bigint NOT NULL REFERENCES quote_tier(id) ON DELETE CASCADE,
  op_no          integer NOT NULL CHECK (op_no BETWEEN 1 AND 8),
  machine_name   text REFERENCES machine(name) ON UPDATE CASCADE,
  family         machine_family,
  setup_h        numeric(9,3),
  pph            numeric(12,3),
  machine_usd_h  usd,
  labor_usd_h    usd,
  workers_ratio  numeric(6,3) NOT NULL DEFAULT 1.0,  -- maquinas atendidas por un operador
  scrap_pct      pct NOT NULL DEFAULT 5,
  target_usd_h   usd,                                -- objetivo de C/CV por hora de la operacion
  UNIQUE (quote_tier_id, op_no)
);
COMMENT ON COLUMN tier_operation.workers_ratio IS
  'El costo de mano de obra por hora maquina es labor_usd_h dividido entre este ratio.';
COMMENT ON COLUMN tier_operation.scrap_pct IS
  'El scrap es acumulativo hacia atras: la cantidad de arranque de cada operacion se calcula con el rendimiento de todas las operaciones posteriores.';

-- ============================================================ 6. RESULTADOS Y TRAZABILIDAD
-- Snapshot del P&L calculado por la app para cada tier (almacenamiento, no calculo)
CREATE TABLE tier_result (
  quote_tier_id            bigint PRIMARY KEY REFERENCES quote_tier(id) ON DELETE CASCADE,
  computed_at              timestamptz NOT NULL DEFAULT now(),
  qty                      numeric(16,2),
  start_qty                numeric(16,2),      -- qty entre el rendimiento acumulado por scrap
  lb_needed                numeric(16,4),
  lb_bought                numeric(16,4),
  moq_binds                boolean,
  setups                   integer,
  ops_count                integer,
  -- costos por pieza
  material_pc              usd_pc,
  material_no_surcharge_pc usd_pc,
  surcharge_pc             usd_pc,
  components_pc            usd_pc,
  consumables_pc           usd_pc,
  sub_raw_pc               usd_pc,
  sub_marked_pc            usd_pc,
  sub_transport_pc         usd_pc,
  packing_pc               usd_pc,
  tooling_pc               usd_pc,
  run_pc                   usd_pc,
  setup_pc                 usd_pc,
  variable_cost_pc         usd_pc,
  -- precio
  oh_pct                   pct,
  contrib_pct              pct,
  divisor                  numeric(10,6),
  sell_calc_pc             usd_pc,
  floor_job_usd            usd,
  floor_pc                 usd_pc,
  sell_pc                  usd_pc,
  is_overridden            boolean,
  below_floor              boolean,
  below_contrib            boolean,
  floor_binds              boolean,
  revenue_usd              usd,
  -- P&L
  purchases_pc             usd_pc,
  av_pc                    usd_pc,   av_pct          pct,
  ms_variable_pc           usd_pc,   ms_variable_pct pct,
  machine_direct_pc        usd_pc,
  ms_direct_fix_pc         usd_pc,
  ccv_pc                   usd_pc,   ccv_pct         pct,
  ccd_pc                   usd_pc,   ccd_pct         pct,
  oh_usd_pc                usd_pc,
  hq_usd_pc                usd_pc,
  commission_usd_pc        usd_pc,
  result_pc                usd_pc,
  -- horas y ratio
  run_hours                numeric(14,4),
  setup_hours              numeric(14,4),
  total_hours              numeric(14,4),
  ccv_per_hour             usd,
  target_rate              usd,
  ccv_ratio                numeric(12,4),
  setup_share              numeric(8,5)
);
COMMENT ON TABLE tier_result IS
  'Gross-up: precio de venta = costo variable / (1 - contribucion - comision - HQ - overheads), todos como porcentaje del precio de venta. Luego se aplica el piso: precio final = MAX(calculado, piso por pieza).';
COMMENT ON COLUMN tier_result.av_pc IS
  'AV = Valor agregado = precio de venta menos contenido comprado (material, surcharge, componentes, consumibles, subcontratacion, transporte, empaque, herramental).';
COMMENT ON COLUMN tier_result.ccv_pc IS 'C/CV = AV menos salarios variables (operaciones SECONDARY).';
COMMENT ON COLUMN tier_result.ccd_pc IS 'C/CD = C/CV menos costo directo de maquina menos salarios fijos directos (operaciones COILER).';

CREATE TABLE quote_flag (
  id             bigserial PRIMARY KEY,
  quote_id       text NOT NULL REFERENCES quote(id) ON DELETE CASCADE,
  quote_part_id  bigint REFERENCES quote_part(id) ON DELETE CASCADE,
  tier_no        integer,
  level          flag_level NOT NULL,
  message        text NOT NULL,
  raised_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE spring_feasibility (
  quote_part_id  bigint PRIMARY KEY REFERENCES quote_part(id) ON DELETE CASCADE,
  score          integer CHECK (score BETWEEN 0 AND 100),
  band           text,
  calc_type      spring_type,
  weight_lb      numeric(14,6),
  payload        jsonb,
  received_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE spring_feasibility_flag (
  id             bigserial PRIMARY KEY,
  quote_part_id  bigint NOT NULL REFERENCES spring_feasibility(quote_part_id) ON DELETE CASCADE,
  level          flag_level NOT NULL,
  title          text NOT NULL,
  recommendation text
);

CREATE TABLE delta_won (
  id            bigserial PRIMARY KEY,
  quote_id      text NOT NULL UNIQUE REFERENCES quote(id) ON DELETE CASCADE,
  recorded_at   timestamptz NOT NULL DEFAULT now(),
  recorded_by   text
);

CREATE TABLE delta_won_item (
  id            bigserial PRIMARY KEY,
  delta_won_id  bigint NOT NULL REFERENCES delta_won(id) ON DELETE CASCADE,
  pn            text NOT NULL,
  family        text,
  new_price_pc  usd_pc,
  qty           numeric(16,2),
  unit          price_unit,
  is_new_pn     boolean NOT NULL DEFAULT FALSE,
  prev_price_pc usd_pc,
  delta_pc      usd_pc,
  delta_usd     usd,
  new_usd       usd,
  CHECK (is_new_pn OR prev_price_pc IS NOT NULL)
);
COMMENT ON TABLE delta_won_item IS
  'Delta Won: al marcar PO RECEIVED se exige el precio anterior por pieza de cada PN, o marcarlo como PN nuevo (entra al reporte NEW SALES en lugar del delta).';

CREATE TABLE journal (
  id         bigserial PRIMARY KEY,
  when_ts    timestamptz NOT NULL DEFAULT now(),
  who        text,
  area       text,          -- INIT, QUOTE, AI, DB, MIGRATE, USER
  detail     text NOT NULL
);
CREATE INDEX ix_journal_when ON journal (when_ts DESC);

CREATE TABLE quote_lock (
  quote_id   text PRIMARY KEY REFERENCES quote(id) ON DELETE CASCADE,
  user_email text NOT NULL,
  locked_at  timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE quote_lock IS 'Bloqueo blando de edicion; la app lo considera vencido a los 30 minutos.';

-- ============================================================ 7. VISTAS
CREATE VIEW v_quote_log AS
SELECT q.id, q.number, q.version, q.status, q.outcome,
       q.customer_code, c.name AS customer_name, q.sales_rep, q.rfq_date,
       q.created_at, q.created_by, q.approved_at, q.approved_by,
       string_agg(DISTINCT p.pn, ', ') AS pns,
       count(DISTINCT p.id) AS pn_count
FROM quote q
LEFT JOIN customer   c ON c.code = q.customer_code
LEFT JOIN quote_part p ON p.quote_id = q.id
WHERE NOT q.is_deleted
GROUP BY q.id, c.name;

-- Ingreso por cotizacion usando el tier seleccionado de cada PN
CREATE VIEW v_quote_revenue AS
SELECT q.id AS quote_id, q.number, q.status, q.outcome, q.customer_code,
       sum(r.revenue_usd)     AS revenue_usd,
       sum(r.ccv_pc * r.qty)  AS ccv_usd,
       sum(r.total_hours)     AS machine_hours
FROM quote q
JOIN quote_part  p ON p.quote_id = q.id
JOIN quote_tier  t ON t.quote_part_id = p.id AND t.tier_no = p.selected_tier
JOIN tier_result r ON r.quote_tier_id = t.id
WHERE NOT q.is_deleted
GROUP BY q.id;

-- Precio entregado por material y diametro (precio + surcharge aplicable)
CREATE VIEW v_material_price_latest AS
SELECT mp.material_code, ml.description, mp.dia_in, mp.latest_usd_lb, mp.wavg_usd_lb,
       mp.price_date, mp.supplier,
       COALESCE(s.per_lb, 0) AS surcharge_usd_lb,
       mp.latest_usd_lb + COALESCE(s.per_lb, 0) AS delivered_usd_lb
FROM material_price mp
JOIN material_legend ml ON ml.code = mp.material_code
LEFT JOIN surcharge  s  ON s.code  = mp.material_code AND s.applies_to_quote;

-- Matriz de capacidad: que maquina puede correr que resorte
CREATE VIEW v_machine_capability AS
SELECT name, family, wire_min_mm, wire_max_mm, od_max_mm,
       cap_compression, cap_extension, cap_torsion, setup_class,
       cost_rate_usd_h, ccv_target_usd_h, labor_usd_h, uses, risk
FROM machine
WHERE is_active;


-- =====================================================================================
-- 8. DATOS SEMILLA
-- =====================================================================================

-- 8.1 Usuarios
INSERT INTO app_user (email, full_name, role, pw_hash) VALUES
  ('admin@cgr-international.com', 'CGR AI Team (Admin)', 'ADMIN', NULL),
  ('quoting@cgr-international.com', 'CGR AI Team (Quoting)', 'QUOTE', NULL);

-- 8.2 Parametros globales de precio (DEFAULT_PARAMS + machineParams)
INSERT INTO pricing_param (id, mat_markup_pct, comp_markup_pct, cons_markup_pct, sub_markup_pct,
  contribution_pct, hq_pct, commission_nic_pct, oh_ladder_pct, oh_sub_pct, oh_min_pct, oh_max_pct,
  floor_base_usd, floor_per_op_usd, scrap_default_pct, wire_max_in,
  coiler_mult, secondary_mult, plating_surcharge_per_pn) VALUES
  (1, 6, 6, 6, 50, 20, 5, 5, ARRAY[30,30,30,30]::pct[], 35, 10, 35, 800, 200, 5, 0.59, 3, 5, 30);

-- Opciones de scrap permitidas (arriba de 5 por ciento se marca con bandera)
INSERT INTO scrap_option (scrap_pct, is_flagged) VALUES
  (1, FALSE),
  (2, FALSE),
  (3, FALSE),
  (4, FALSE),
  (5, FALSE),
  (10, TRUE),
  (15, TRUE),
  (20, TRUE),
  (25, TRUE),
  (50, TRUE);

-- Tarifas de mano de obra (actualizadas 2026-07-15)
INSERT INTO labor_rate (family, usd_per_h, effective, note) VALUES
  ('COILER', 40, DATE '2026-07-15', 'Operador de enrollado. Su costo va a MS Direct Fix.'),
  ('SECONDARY', 27, DATE '2026-07-15', 'Operador de operaciones secundarias. Su costo va a MS Variable.');

-- 8.3 Clientes (412)
INSERT INTO customer (code, name, terms) VALUES
  ('2RTOOL', '2R Tool & Machine, Inc.', 'Net 30'),
  ('A&K RAIL', 'A & K Railroad Inc', 'Net 30'),
  ('AAAA SPEC', 'AAAA Specialties', 'Net 30'),
  ('ABB MOTORS', 'ABB Motors and Mechanical Inc.', 'Net 30'),
  ('ABILENE', 'Abilene Machine Inc.', 'Net 30'),
  ('ACI', 'ACI Services, Inc.', 'Net 30'),
  ('AERIFICATI', 'Aerification Plus LLC', 'Net 30'),
  ('AEROM', 'Aeromotive, Inc.', 'Net 30'),
  ('AEROT', 'Aero Transportation Products Inc. (Wabtec Corp,)', 'Net 30'),
  ('AFC', 'AFC Industries Inc', 'Net 30'),
  ('A-J', 'A J Manufacturing Co Inc', 'Net 30'),
  ('ALAMO', 'Alamo Group (SMC) Inc', 'Net 30'),
  ('ALKAR', 'Alkar-RapidPak, Inc.', 'Net 30'),
  ('ALLEGMFG', 'Allegiant Manufacturing', 'Net 30'),
  ('ALLEN FILT', 'Allen Filters', 'Net 30'),
  ('ALLIM', 'Allied Materials & Equip., Inc.', 'Net 30'),
  ('ALLOY', 'Alloy Process Engineering, Inc.', 'Net 30'),
  ('ALTEC AIR', 'Altec Air, LLC', 'Net 30'),
  ('AMDIS', 'American Dish Service', 'Net 30'),
  ('AMER PROS', 'American Prosthetic Components, LLC', 'Net 30'),
  ('AMERG', 'American Games, Inc.', 'Net 30'),
  ('AMERSY', 'American Syscomptel Inc', 'Net 30'),
  ('AMMFG', 'American Manufacturing', 'Net 30'),
  ('ANCO', 'Anco International Incorporated', 'Net 30'),
  ('APACI', 'Apache Hose & Belting, Inc.', 'Net 30'),
  ('APEXHAUST', 'AP Exhaust Products, Inc', 'Net 30'),
  ('APPLIED MO', 'Applied Industrial Technologies', 'Net 30'),
  ('APPLIED OH', 'Applied Industrial Technology', 'Net 30'),
  ('ARBOL', 'ABC Logistics div of Arkansas Bolt Co.', 'Net 30'),
  ('ARIENS', 'Ariens Company', 'Net 30'),
  ('ARMST', 'Armstrong Machine Co.', 'Net 30'),
  ('ARTIC', 'Arctic Fox', 'Net 30'),
  ('ARTSW', 'Arts-Way Manufacturing', 'Net 30'),
  ('ASPENPRO', 'Aspen Products', 'Net 30'),
  ('ASSEC', 'Associated Equipment Corporation', 'Net 30'),
  ('ASSEM', 'Assembled Products Corp', 'Net 30'),
  ('ATLAS ROOF', 'Atlas Roofing', 'Net 30'),
  ('ATLAS TUBE', 'Atlas Tube, Div of Zekelman Industries', 'Net 30'),
  ('AUEQP', 'Automatic Equiment Mfg dba Blue Ox', 'Net 30'),
  ('AUSTIN HAR', 'Austin Hardware & Supply, Inc.', 'Net 30'),
  ('AXE EQUIP', 'AXE Equipment', 'Net 30'),
  ('B&W', 'B & W Custom Truck Beds,Inc.', 'Net 30'),
  ('B&W BRAKE', 'B & W Brake, Inc.', 'Net 30'),
  ('BAXSALES', 'Bax Sales Inc', 'Net 30'),
  ('BEE', 'Bee Line Company', 'Net 30'),
  ('BERGM', 'Bergman Manufacturing Inc', 'Net 30'),
  ('BERKEL', 'Berkel and Co', 'Net 30'),
  ('BETTEN', 'Bettendorf Stanford', 'Net 30'),
  ('BISON', 'Bison Inc', 'Net 30'),
  ('BMG', 'BMG of Kansas, Inc.', 'Net 30'),
  ('BOBCAT', 'Clark Equipment Company (Doosan Bobcat NA, Inc.)', 'Net 30'),
  ('BONE', 'Allen Press Parts, formerly The Bone Pile', 'Net 30'),
  ('BOSSARD', 'Bossard North America', 'Net 30'),
  ('BOULD LINC', 'AFC Industries', 'Net 30'),
  ('BRADB', 'The Bradbury Co. Inc.', 'Net 30'),
  ('BRODERSON', 'Broderson Manufacturing Corp.', 'Net 30'),
  ('BROWNCO', 'Brown-Covey Inc', 'Net 30'),
  ('BRUNSON', 'Brunson Instrument Company', 'Net 30'),
  ('BSN', 'BSN Medical Inc', 'Net 30'),
  ('BUCKET', 'The Bucket Cover', 'Net 30'),
  ('BULK TANK', 'Bulk Tank Incorporated', 'Net 30'),
  ('BULLMOOSE', 'Bull Moose Tube CompanyBUNZL PR|Bunzl Omaha (89-003)', 'Net 30'),
  ('BURG', 'Burger & Brown Engineering Inc.', 'Net 30'),
  ('CAPSA', 'CAPSA Healthcare', 'Net 30'),
  ('CARDC', 'Cardinal Components Inc', 'Net 30'),
  ('CASHCO', 'Cashco, Inc', 'Net 30'),
  ('CBC', 'Wesco (Formerly Carlton Bates)', 'Net 30'),
  ('CEI', 'CEI Equipment Co. DBA KT PACER', 'Net 30'),
  ('CERPW', 'Certified Power, Inc', 'Net 30'),
  ('CHANCE', 'Chance Rides Manufacturing Inc', 'Net 30'),
  ('CHECK', 'Check-All Valve Mfg. Co.', 'Net 30'),
  ('CHEVY', 'Classic Parts of America', 'Net 30'),
  ('CHOATE', 'Choate Machine and Tool, Inc', 'Net 30'),
  ('CLAYB', 'Clay & Bailey Mfg. Co.', 'Net 30'),
  ('CLEVELAND', 'Cleveland-Cliffs Tubular Components, LLC', 'Net 30'),
  ('COBRA', 'Cobra Motorcycle Mfg. Inc.', 'Net 30'),
  ('CO-LINE', 'Co-Line Manufacturing', 'Net 30'),
  ('COLLINS MA', 'Collins Machinery', 'Net 30'),
  ('COLLIS', 'Collis Toolholder Corporation', 'Net 30'),
  ('COLUM', 'Columbia Glass & Window Co.', 'Net 30'),
  ('COMMP', 'Community Playthings', 'Net 30'),
  ('COMP', 'Components Company Inc', 'Net 30'),
  ('COMPRESS', 'Compressor Parts & Components Co.', 'Net 30'),
  ('CONST PROD', 'Construction Products', 'Net 30'),
  ('CONTITECH', 'ContiTech USA, Inc.', 'Net 30'),
  ('CONTL', 'Control Devices LLC', 'Net 30'),
  ('CORNELIUS', 'Cornelius Manufacturing', 'Net 30'),
  ('COSER', 'Colorado Serum Company', 'Net 30'),
  ('CRICK', 'Ameri Source/ dba Crick Tool', 'Net 30'),
  ('CROSM', 'Cross Manufacturing Inc.-V100018', 'Net 30'),
  ('CROWN', 'Crown Packaging Corp.', 'Net 30'),
  ('CUSTOM SKA', 'Custom SkateWorks', 'Net 30'),
  ('CUSTPART', 'Custom Parts Engineering', 'Net 30'),
  ('CUTLER REP', 'Cutler Repaving', 'Net 30'),
  ('DALS', 'Bernard Dalsin Manufacturing', 'Net 30'),
  ('DALTO', 'Dalton AG Inc dba Dalton AG Products', 'Net 30'),
  ('DANU', 'Danuser Machine Company', 'Net 30'),
  ('DECKER', 'Decker Mfg Co', 'Net 30'),
  ('DECOP', 'Deco Products Company', 'Net 30'),
  ('DELTAKITS', 'Delta Kits', 'Net 30'),
  ('DEMCO', 'Demco Products', 'Net 30'),
  ('DEXT', 'Dexter Laundry, Inc', 'Net 30'),
  ('DIAGR', 'Diagraph Corporation', 'Net 30'),
  ('DIAM', 'Diamond Mfg. Inc.', 'Net 30'),
  ('DOERING', 'Doering Company, LLC', 'Net 30'),
  ('DORMAKABA', 'dormakaba USA, Inc.', 'Net 30'),
  ('DOUBH', 'Double HH Mfg Div of Hope Haven Inc', 'Net 30'),
  ('DUAL', 'Dual Dynamics Inc', 'Net 30'),
  ('DUTT', 'Dutton-Lainson Company', 'Net 30'),
  ('DWYER', 'Dwyer Instruments', 'Net 30'),
  ('EBCO', 'EBCO Products Corp', 'Net 30'),
  ('ECONTROLS', 'InPro/Seal, LLC DBA FW Murphy Production Controls', 'Net 30'),
  ('ELIJAH', 'Elijah Tooling Inc.', 'Net 30'),
  ('EMCOS', 'EMCO Enterprises Inc', 'Net 30'),
  ('EMERS', 'Emerson Mfg. Corp', 'Net 30'),
  ('EMMERT', 'Emmert Welding & Mfg Co', 'Net 30'),
  ('ENDRIES', 'Endries International Inc', 'Net 30'),
  ('ENERGYMFG', 'Energy Mfg. Company, Inc', 'Net 30'),
  ('ENSIGHT', 'Ensight Solutions LLC', 'Net 30'),
  ('ESKRI', 'Eskridge Inc.', 'Net 30'),
  ('EXCEL IND', 'Excel Industries Inc.', 'Net 30'),
  ('EXLIN', 'Exline, Inc.', 'Net 30'),
  ('EXP SCALE', 'Express Scale Parts', 'Net 30'),
  ('FAIR', 'Fair Manufacturing', 'Net 30'),
  ('FAIRF', 'Fairfield Industries Inc', 'Net 30'),
  ('FASCO3', 'Regal Beloit America Inc', 'Net 30'),
  ('FASTCOM', 'Fastcom Supply', 'Net 30'),
  ('FASTEN SOL', 'Fastener Solutions', 'Net 30'),
  ('FASTENAL I', 'Fastenal', 'Net 30'),
  ('FASTENAL O', 'Fastenal', 'Net 30'),
  ('FAWN', 'Fawn Engineering Corp.', 'Net 30'),
  ('FEATHERLIT', 'Featherlite Trailer Manufacturing LLC', 'Net 30'),
  ('FEMCO', 'Femco Inc.', 'Net 30'),
  ('FERG', 'Revere Plastics Systems (Formally Ferguson Prod.)', 'Net 30'),
  ('FIKE', 'Fike Corporation', 'Net 30'),
  ('FIMCO', 'Fimco Inc.', 'Net 30'),
  ('FINISHING', 'Carlisle Fluid Technologies (Finishing Brands)', 'Net 30'),
  ('FIRST WAVE', 'First Wave Products Group, LLC', 'Net 30'),
  ('FLEXTRON', 'Flextronics America, LLC', 'Net 30'),
  ('FOODCRAFT', 'Foodcraft', 'Net 30'),
  ('FORD MOTOR', 'Ford Motor Company', 'Net 30'),
  ('FOSTM', 'Foster Manufacturing Co., Inc.', 'Net 30'),
  ('FREEM', 'The Freeman Company', 'Net 30'),
  ('FULTON', 'Fulton Corporation', 'Net 30'),
  ('GARMIN', 'Garmin International, Inc.', 'Net 30'),
  ('GEM TECH', 'Gem Tech LLC', 'Net 30'),
  ('GEORGE', 'George Steel Fabricating', 'Net 30'),
  ('GLEND', 'Glendo LLC', 'Net 30'),
  ('GRAINCUSSO', 'Grainger Sourcing', 'Net 30'),
  ('GRAY', 'Gray Manufacturing Company Inc', 'Net 30'),
  ('GRESALES', 'Gregory Sales & Service', 'Net 30'),
  ('GRIND', 'Great Plains Industries', 'Net 30'),
  ('GRPLN', 'Great Plains Manufacturing', 'Net 30'),
  ('GULL', 'Gull Industries', 'Net 30'),
  ('HAMEL', 'Hamel Mfg Company Inc.', 'Net 30'),
  ('HAMPS', 'WS Hampshire, Inc', 'Net 30'),
  ('HANDICARE', 'Handicare USA, LLC', 'Net 30'),
  ('HANSR', 'Hans Rudolph Inc.', 'Net 30'),
  ('HANTOVER', 'Hantover Inc', 'Net 30'),
  ('HARL', 'Harlan Global Manufacturing,LLC', 'Net 30'),
  ('HARLEYATTA', 'Sweepster/Paladin Attachments LLC', 'Net 30'),
  ('HARMAN CO', 'Donald harman DBA Harman Company', 'Net 30'),
  ('HARP', 'Harper Trucks, Inc.', 'Net 30'),
  ('HAWAR', 'Hawarden Machine Inc. dba For-Most Inc', 'Net 30'),
  ('HCDUK', 'H.C. Duke & Son Inc.', 'Net 30'),
  ('HEN', 'Hen-Way Manufacturing Inc.', 'Net 30'),
  ('HENKE', 'Henke Mfg / Alamo Group', 'Net 30'),
  ('HENKEMACH', 'Global Equipment Co. Inc.', 'Net 30'),
  ('HEWIL', 'H.E. Williams Inc.', 'Net 30'),
  ('HI HEAT', 'Hi Heat Indsutries, Inc.', 'Net 30'),
  ('HIGHQ', 'High Quality Plastics Inc.', 'Net 30'),
  ('HIGHTECH', 'High Tech Tool', 'Net 30'),
  ('HILLS', 'Hills Stainless Steel & Eqp. Co.', 'Net 30'),
  ('HILO', 'Hi-Lo Manufacturing', 'Net 30'),
  ('HIX', 'Hix Corporation', 'Net 30'),
  ('HMC', 'HMC Industries', 'Net 30'),
  ('HOPKINS', 'Hopkins Manufacturing Corporation', 'Net 30'),
  ('HORN', 'Hornady Mfg. Company', 'Net 30'),
  ('HORSE', 'Horsepower Controls', 'Net 30'),
  ('HTS', 'HTS Technologies', 'Net 30'),
  ('HUBBELL', 'Hubbell Power Systems Inc', 'Net 30'),
  ('HUBBELL-IC', 'Hubbell Industrial Controls', 'Net 30'),
  ('HUGHE', 'Hughes Brothers Inc.', 'Net 30'),
  ('HUHTAMAKI', 'Huhtamaki, Inc.', 'Net 30'),
  ('HULCO', 'Hulco Parts', 'Net 30'),
  ('HUSQV', 'Husqvarna Turf Care Division', 'Net 30'),
  ('HUSQVCONST', 'Husqvarna Construction Products', 'Net 30'),
  ('HYD ELECTR', 'Hydraulic Electric Inc.', 'Net 30'),
  ('HYDAC', 'HYDAC Technology Corp', 'Net 30'),
  ('HYUNDAI', 'Hyundai Motor Manufacturing Alabama LLC', 'Net 30'),
  ('IBT', 'IBT, Inc', 'Net 30'),
  ('IHD', 'Industrial Hardware Distributors', 'Net 30'),
  ('INDACCES', 'Industrial Accessories Company', 'Net 30'),
  ('INDUS SALE', 'Industrial Sales & Manufacturing Inc.', 'Net 30'),
  ('INFIN', 'Infinity Fasteners Inc', 'Net 30'),
  ('INTERLOCK', 'InterLock Steel Intructures', 'Net 30'),
  ('INTER-TECH', 'Inter-Tech Supplies', 'Net 30'),
  ('INTPR', 'International Parts Supply', 'Net 30'),
  ('INVENTORY', 'Inventory Sales Company', 'Net 30'),
  ('IOWA', 'Iowa Spring Manufacturing Inc.', 'Net 30'),
  ('IOWAE', 'Iowa EPS Products', 'Net 30'),
  ('ISSCO', 'Issco Inc', 'Net 30'),
  ('JACKMA', 'Jack Maddox', 'Net 30'),
  ('JCI RUSKIN', 'Ruskin- Air Distribution Technologies', 'Net 30'),
  ('JDMFG', 'J & D Mfg Inc', 'Net 30'),
  ('JEM', 'JEM International', 'Net 30'),
  ('JETED', 'Jet Edge Inc', 'Net 30'),
  ('JGB', 'Echelon Supply and Service', 'Net 30'),
  ('JHTNA', 'Johnson Health Tech NA Mfg', 'Net 30'),
  ('JOHNF', 'Baader-Johnson Food Processing Equipment', 'Net 30'),
  ('JOHNSONGAS', 'Johnson Gas Appliance Company', 'Net 30'),
  ('JONES', 'Phil Jones', 'Net 30'),
  ('K&O', 'K And O Manufacturing Co.', 'Net 30'),
  ('KEGEL', 'Kegel LLC', 'Net 30'),
  ('KEJR', 'Kejr, Inc dba Geoprobe Systems', 'Net 30'),
  ('KINZE', 'Kinze Manufacturing Inc.', 'Net 30'),
  ('KIRBY', 'Kirby Risk Corporation', 'Net 30'),
  ('KLAUSPROEN', 'Klaus Proen', 'Net 30'),
  ('K-LINE', 'K-Line Industries', 'Net 30'),
  ('KMW', 'KMW, Ltd.', 'Net 30'),
  ('KNAPP', 'Knappco Corporation', 'Net 30'),
  ('KOCH', 'UltraSource LLC', 'Net 30'),
  ('KOMMEN', 'Kommen Industrial Supply', 'Net 30'),
  ('KOOIMAG', 'Kooimag Ag', 'Net 30'),
  ('KOSCH', 'Kosch Manufacturing, LLC', 'Net 30'),
  ('KTEK', 'K-TEK Wisconsin (A Griffiths Company)', 'Net 30'),
  ('LAB', 'LabStrong', 'Net 30'),
  ('LABCO', 'Labconco Corporation', 'Net 30'),
  ('LAKESIDE', 'Lakeside Casting Solutions', 'Net 30'),
  ('LANDMARK', 'Landmark Mfg Corporation (Good One)', 'Net 30'),
  ('LBT', 'L.B.T. Inc', 'Net 30'),
  ('LEEBOY', 'VT LeeBoy Inc (FAYAT Group)', 'Net 30'),
  ('LENEXA MFG', 'Lenexa Manufacturing Company', 'Net 30'),
  ('LIBBEY', 'Libbey Glass Inc.', 'Net 30'),
  ('LIFE FIT', 'Life Fitness dba Cybex Intl', 'Net 30'),
  ('LINDSAY', 'Lindsay Irrigation Solutions, LLC', 'Net 30'),
  ('LINN', 'Linn Pipe & Post Inc.', 'Net 30'),
  ('LIPPERT', 'Lippert Components', 'Net 30'),
  ('LISLE', 'Lisle Corp', 'Net 30'),
  ('LIVER', 'Livers Bronze Co. Inc.', 'Net 30'),
  ('LOON', 'Counter Shox LLC', 'Net 30'),
  ('LOREN', 'Lorenson Industries Inc.', 'Net 30'),
  ('LORENCOOK', 'Loren Cook Company', 'Net 30'),
  ('LOVE LIFE', 'Love Lifesciences', 'Net 30'),
  ('LP STEEL', 'LP Tube, LLC', 'Net 30'),
  ('LS IND', 'LS Industries', 'Net 30'),
  ('LT SERVICE', 'L.T. Service Company L.L.C.', 'Net 30'),
  ('MAGNUM', 'Magnum ENP (Bucyrus)', 'Net 30'),
  ('MAINFILTER', 'Hengst Filtration USA LLC. (formerly Main Filter)', 'Net 30'),
  ('MARAT', 'Marathon Sales Inc', 'Net 30'),
  ('MARLEN', 'Marlen International', 'Net 30'),
  ('MASTP', 'Master Pitching Machine Inc', 'Net 30'),
  ('MAYVILLE', 'MEC-Mayville Engineering Company Inc', 'Net 30'),
  ('MCDONALD', 'McDonald Plastic Molding', 'Net 30'),
  ('MERIT MED', 'Merit Medical', 'Net 30'),
  ('MERR', 'Merrill Mfg. Company', 'Net 30'),
  ('METALCRAFT', 'Metalcraft of Mayville', 'Net 30'),
  ('METCRAFT', 'Metcraft Industries Inc.', 'Net 30'),
  ('METROLOGY', 'MetrologyWorks', 'Net 30'),
  ('MHILL', 'Hot Grass and Vines (Formerly Total Habitat LC)', 'Net 30'),
  ('MICROCOM', 'Microcom Corporation', 'Net 30'),
  ('MID CONTIN', 'Mid-Continent Machining, Inc.', 'Net 30'),
  ('MIDLAND', 'Midland Plastics Inc.', 'Net 30'),
  ('MIDWEST CO', 'Midwest Control Products Corp.', 'Net 30'),
  ('MIDWEST ME', 'Midwest Metalcraft & Equipment', 'Net 30'),
  ('MIDWESTBRD', 'Midwest BRD, Inc.', 'Net 30'),
  ('MILBA', 'Milbank Mfg. Company', 'Net 30'),
  ('MILLER MFG', 'Miller Manufacturing Company', 'Net 30'),
  ('MILLT', 'Milltronics Mfg Co', 'Net 30'),
  ('MK SPECIAL', 'MK Specialties', 'Net 30'),
  ('MOBILITY', 'Mobility Worldwide', 'Net 30'),
  ('MOC PROD', 'MOC Products Company, Inc.', 'Net 30'),
  ('MODFO', 'Modernfold Inc.', 'Net 30'),
  ('MOFF', 'Moffatt Products Inc.', 'Net 30'),
  ('MOLY-COP', 'Moly-Cop USA, LLC', 'Net 30'),
  ('MONOSEM', 'Monosem Inc.', 'Net 30'),
  ('MORIDGE', 'Moridge Manufacturing Inc.', 'Net 30'),
  ('MOTION IND', 'Motion Industries, Inc', 'Net 30'),
  ('MT TABLES', 'MT Tables', 'Net 30'),
  ('MULTIVAC', 'Multivac Inc.', 'Net 30'),
  ('MUSCLE', 'Muscle Car Mike', 'Net 30'),
  ('NATION REP', 'Nationwide Repair Holdings', 'Net 30'),
  ('NATIONAL B', 'National Beef Leathers LLC', 'Net 30'),
  ('NEOGEN', 'Neogen Corporation', 'Net 30'),
  ('NIBCO', 'NIBCO Inc', 'Net 30'),
  ('NORTHSP', 'North Star Power Inc', 'Net 30'),
  ('NORTHWEST', 'Northwestern Tools', 'Net 30'),
  ('NORTTO', 'North Topeka Fabrication', 'Net 30'),
  ('NSK IND', 'NSK Industires', 'Net 30'),
  ('NVENIA', 'nVenia', 'Net 30'),
  ('O2 CORP', 'O2 Corporation', 'Net 30'),
  ('OBEY', 'Odey''s Field Experts', 'Net 30'),
  ('OCI', 'OCI Instruments', 'Net 30'),
  ('OMSTD', 'Palfinger North America LLC (Omaha Standard)', 'Net 30'),
  ('ORANGE', 'Orange EV LLC', 'Net 30'),
  ('OSBOR', 'Osborne Industries Inc.', 'Net 30'),
  ('OSSA', 'OSSA Engineering', 'Net 30'),
  ('OVERSIZE', 'Oversize Warning Products', 'Net 30'),
  ('PACER', 'Pacer Industrial Mixers', 'Net 30'),
  ('PARK', 'Park Industries Inc.', 'Net 30'),
  ('PARKHURST', 'Parkhurst Manufacturing Co. Inc.', 'Net 30'),
  ('PARKSON', 'Parkson Corporation', 'Net 30'),
  ('PATRIOT', 'Patriot Fire Protection, Inc.', 'Net 30'),
  ('PEERLESSG', 'Peerless Gear', 'Net 30'),
  ('PEREG', 'Peregrine Inc', 'Net 30'),
  ('PINNACLE', 'Pinnacle Climate Technologies', 'Net 30'),
  ('PIVOT', 'Pivot International', 'Net 30'),
  ('PJTRAIL', 'PJ Trailers, Mfg. Co.', 'Net 30'),
  ('PMP', 'Precision Machined Parts', 'Net 30'),
  ('POWER', 'Power Flame Incorporated', 'Net 30'),
  ('PREC MET', 'Precision Metals Corp', 'Net 30'),
  ('PREGIS', 'Pregis Intellipack LLC', 'Net 30'),
  ('PRIER', 'Prier Products Inc.', 'Net 30'),
  ('PRINCE', 'Prince Manufacturing Corporation', 'Net 30'),
  ('PTMW', 'PTMW', 'Net 30'),
  ('PTSOL', 'PT-Solutions', 'Net 30'),
  ('QC METAL', 'QC Metal Fab', 'Net 30'),
  ('QUAL CONN', 'Quality Connectionz Inc.', 'Net 30'),
  ('QUALITYSTA', 'Quality Stainless Products', 'Net 30'),
  ('RCZ ENT', 'RCZ Enterprises', 'Net 30'),
  ('RD LEVERAG', 'R & D Leverage', 'Net 30'),
  ('RDIND', 'RD Industries Inc', 'Net 30'),
  ('RELIANCE', 'Reliance Metalcenter', 'Net 30'),
  ('RH', 'R. H. Fastener', 'Net 30'),
  ('RIEAD', 'Rieadco Corp', 'Net 30'),
  ('RIGHT ANGL', 'Right Angle Steel & Fab', 'Net 30'),
  ('RMF FREEZ', 'RMF Freezers', 'Net 30'),
  ('RNPMEX', 'Refacciones Neumaticas La Paz De CV', 'Net 30'),
  ('ROCKHARD', 'Rock Hard 4X4', 'Net 30'),
  ('ROM', 'Safe Fleet (ROM)', 'Net 30'),
  ('RUGBY', 'Rugby Manufacturing Corp. div of TBEI', 'Net 30'),
  ('RYCOM', 'Rycom Instruments', 'Net 30'),
  ('RYKO', 'National Carwash Solutions (Ryko Solutions, Inc)', 'Net 30'),
  ('SAFE FLEET', 'Safe Fleet (Specialty Manufacturing, Inc)', 'Net 30'),
  ('SALINA VOR', 'Salina Vortex Corporation', 'Net 30'),
  ('SANSL', 'Santa Fe Sales Company', 'Net 30'),
  ('SCHENCK', 'Coperion Process Sol. LLC (Former Schenck Process)', 'Net 30'),
  ('SCHILLER', 'Schiller Grounds Care Inc.', 'Net 30'),
  ('SCOTT TRAI', 'Scott''s Custom Trailers', 'Net 30'),
  ('SCRIPTPRO', 'ScriptPro', 'Net 30'),
  ('SHARPLINE', 'Sharpline Converting, INC', 'Net 30'),
  ('SHAW SUPP', 'Shaw Supply Company', 'Net 30'),
  ('SHOR-LINE', 'Midmark (formerly Shor-Line)', 'Net 30'),
  ('SHUR', 'Shur-Co', 'Net 30'),
  ('SIGG', 'Siggins Co.', 'Net 30'),
  ('SKF', 'SKF USA Inc', 'Net 30'),
  ('SMILO', 'Smith & Loveless Inc.', 'Net 30'),
  ('SMOKIN', 'Smokin Brothers', 'Net 30'),
  ('SNARE', 'The Snare Shop', 'Net 30'),
  ('SNYDER', 'Tank Holding (Formerly Snyder Industries Inc)', 'Net 30'),
  ('SOR', 'SOR Inc.', 'Net 30'),
  ('SOUK', 'Soukup Machine', 'Net 30'),
  ('SPECIAL GA', 'Specialty Sales Co.', 'Net 30'),
  ('SPETY', 'Specialty Mfg. Company', 'Net 30'),
  ('SPILLMAN', 'Spillman Company', 'Net 30'),
  ('SPORTWORKS', 'Sportworks Global LLC', 'Net 30'),
  ('SR HOLDING', 'SR Holdings andInnovations, LLC', 'Net 30'),
  ('STANDARDMO', 'Standard Motor Products, Inc', 'Net 30'),
  ('STONE MFG', 'Stone Manufacturing & Supply Company', 'Net 30'),
  ('SUDEN', 'Sudenga Industries Inc.', 'Net 30'),
  ('SUNBRIGHT', 'Sunbright USA, Inc.', 'Net 30'),
  ('SUPPLY TEC', 'Supply Technologies', 'Net 30'),
  ('SWISH', 'SAI', 'Net 30'),
  ('SWITCHNGO', 'Switch-N-Go', 'Net 30'),
  ('SYR', 'Scot Young Research', 'Net 30'),
  ('SYSTEMS', 'Systems LLC', 'Net 30'),
  ('TBEI', 'TBEI, Inc', 'Net 30'),
  ('TCD', 'TCD Parts', 'Net 30'),
  ('TEKNO', 'Tekno, Inc', 'Net 30'),
  ('TEXTREZGO', 'Textron Finance Shared Services Center', 'Net 30'),
  ('TIRES', 'Tire Service International', 'Net 30'),
  ('TITANA', 'Titan Application', 'Net 30'),
  ('TITLE', 'Title Boxing,LLC', 'Net 30'),
  ('TL', 'T - L Irrigation Company', 'Net 30'),
  ('TMI', 'Technik Manufacturing, Inc.', 'Net 30'),
  ('TONGS', 'Midwest Tongs', 'Net 30'),
  ('TORO', 'Toro', 'Net 30'),
  ('TRIAN', 'Triangle Engineering', 'Net 30'),
  ('TRIANLE', 'Triangle Mfg.', 'Net 30'),
  ('TRITRON', 'Tri-Tronics Company', 'Net 30'),
  ('TROJANSPEC', 'Beck Sales Inc dba Trojan Specialty Products', 'Net 30'),
  ('TURF', 'Turfco Mfg Inc', 'Net 30'),
  ('TVH', 'TVH Parts Company', 'Net 30'),
  ('UNI BAK', 'United Bakery', 'Net 30'),
  ('UNIMACTS', 'Unimacts Globall', 'Net 30'),
  ('UNIVERSAL4', 'Universal 4 mations', 'Net 30'),
  ('UNIVERSALS', 'Universal Sign & Display, LLC', 'Net 30'),
  ('US TSUBAKI', 'US Tsubaki', 'Net 30'),
  ('USF', 'USF Fabrication an Eagle Mfg Company', 'Net 30'),
  ('USPOS', 'U.S. Postal Service', 'Net 30'),
  ('VANGUARD', 'Vanguard Packaging, Inc.', 'Net 30'),
  ('VC999', 'VC999 Packaging Systems', 'Net 30'),
  ('VIKCO', 'Viking Corporation', 'Net 30'),
  ('VISTM', 'Vista Machining Co. Inc', 'Net 30'),
  ('WATCO', 'Watco Mfg. Company', 'Net 30'),
  ('WATEROUS', 'Waterous Company', 'Net 30'),
  ('WATERTENT', 'Waterloo Tent & Tarp Company', 'Net 30'),
  ('WATSON', 'Watson Metal Masters', 'Net 30'),
  ('WDBIN', 'Woodbine Mfg Co. dba Tommy Gate Company', 'Net 30'),
  ('WDIX', 'Willie Stavig', 'Net 30'),
  ('WEILER', 'Weiler', 'Net 30'),
  ('WELD', 'Weldmatic Inc.', 'Net 30'),
  ('WESCH', 'Western Chemical Pumps', 'Net 30'),
  ('WESDF', 'Westendorf Manufacturing', 'Net 30'),
  ('WESFM', 'Western Forms Inc.', 'Net 30'),
  ('WESTHEFFER', 'Westheffer Company Inc', 'Net 30'),
  ('WISECO', 'Wise Company Inc', 'Net 30'),
  ('WISEMAN', 'Wiseman Industry', 'Net 30'),
  ('WORLDLAWN', 'Worldlawn Power Equipment', 'Net 30'),
  ('WWMAN', 'WW Capital Corp', 'Net 30'),
  ('ZEPHYR', 'Zephyr Products', 'Net 30'),
  ('ZIMMER', 'Zimmer Surgical, Inc.', 'Net 30');

-- 8.4 Leyenda de codigos de material y densidad de alambre (lb/in3)
INSERT INTO material_legend (code, description, density_lb_in3) VALUES
  ('316', 'Stainless Steel 316 (ASTM A313 Type 316)', 0.284),
  ('BB', 'Round Bar Stock', 0.284),
  ('BRASS', 'Brass Wire', 0.308),
  ('CSI', 'Chrome Silicon (ASTM A401)', 0.284),
  ('GHD', 'Galvanized Hard Drawn', 0.284),
  ('GMW', 'Galvanized Music Wire', 0.284),
  ('HAST', 'Hastelloy C-276', 0.321),
  ('HD', 'Hard Drawn (ASTM A227)', 0.284),
  ('MW', 'Music Wire (ASTM A228)', 0.284),
  ('OT', 'Oil Tempered (ASTM A229)', 0.284),
  ('PHOSB', 'Phosphor Bronze', 0.32),
  ('SG', 'Soft Galvanized', 0.284),
  ('SS', 'Stainless Steel 302/304 (ASTM A313)', 0.286),
  ('SS177', 'Stainless Steel 17-7 PH', 0.284);

-- 8.5 Ficha tecnica resumida de materiales (matReference del BRAIN)
INSERT INTO material_reference (name, astm, density_kg_m3, d_min_mm, d_max_mm, temp_max_c, cost_factor, fatigue, note) VALUES
  ('Music Wire', 'ASTM A228', 7860.0, 0.1, 6.5, 120.0, 1.0, 'Excellent', 'Highest-quality high-carbon wire. Best fatigue life of the carbon steels; preferred for dynamic / high-cycle service.'),
  ('Chrome Silicon', 'ASTM A401', 7860.0, 0.8, 12.0, 245.0, 2.5, 'Excellent', 'Alloy steel for shock, impact and elevated-temperature duty. High allowable stress; common for engine / valve springs.'),
  ('Stainless 302/304', 'ASTM A313', 7920.0, 0.1, 10.0, 290.0, 4.0, 'Moderate', 'Austenitic stainless. Good general corrosion resistance; lower allowable stress and modulus than carbon steel.'),
  ('17-7 PH Stainless', 'ASTM A313 (631)', 7800.0, 0.2, 6.0, 340.0, 6.0, 'Good', 'Precipitation-hardening stainless. Heat-treated after forming for high strength + corrosion + moderate elevated-temperature service.'),
  ('Oil Tempered', 'ASTM A229', 7860.0, 0.5, 16.0, 150.0, 0.7, 'Moderate', 'General-purpose pre-tempered carbon steel. Economical for static and moderate-cycle loads; not for high-cycle fatigue or shock.'),
  ('Hard Drawn', 'ASTM A227', 7860.0, 0.7, 12.0, 120.0, 0.5, 'Low', 'Lowest-cost spring wire. Suited to static / low-cycle, non-critical applications. Avoid fatigue, shock and tight tolerances.'),
  ('Inconel X-750', 'AMS 5698/5699', 8250.0, 0.4, 8.0, 370.0, 15.0, 'Good', 'Nickel-chromium superalloy for high-temperature and corrosive environments. Expensive; specify only when service conditions require it.'),
  ('Phosphor Bronze', 'ASTM B159', 8860.0, 0.1, 7.5, 95.0, 5.0, 'Low', 'Copper alloy with good electrical conductivity and corrosion resistance. Low modulus and modest strength; used for contacts / electrical springs.');

-- 8.6 Historico de precios de alambre (186 registros)
INSERT INTO material_price (material_code, dia_in, latest_usd_lb, wavg_usd_lb, min_usd_lb, max_usd_lb, positions, qty_lb, price_date, supplier) VALUES
  ('BB', 0.187, 0.81, 0.81, 0.81, 0.81, 1, 1600.0, DATE '2026-03-25', 'ISW'),
  ('BRASS', 0.05, 15.78, 15.78, 15.78, 15.78, 1, 25.0, DATE '2026-04-15', 'ISW'),
  ('CSI', 0.148, 1.4, 1.433333, 1.4, 1.44, 2, 600.0, DATE '2026-04-09', 'GIBBS'),
  ('GHD', 0.025, 5.81, 2.591818, 2.27, 5.81, 2, 275.0, DATE '2026-02-25', 'ISW'),
  ('GHD', 0.047, 2.34, 2.4232, 2.34, 2.55, 4, 3750.0, DATE '2026-04-09', 'GIBBS, ISW'),
  ('GHD', 0.051, 1.64, 1.646628, 1.64, 2.32, 3, 51300.0, DATE '2026-03-18', 'GIBBS, ISW'),
  ('GHD', 0.054, 2.25, 2.25, 2.25, 2.25, 1, 75.0, DATE '2026-01-14', 'ISW'),
  ('GHD', 0.062, 1.97, 1.97, 1.97, 1.97, 1, 350.0, DATE '2026-01-07', 'ISW'),
  ('GHD', 0.08, 1.43, 1.315455, 1.22, 1.43, 2, 1100.0, DATE '2026-02-11', 'ISW'),
  ('GHD', 0.091, 1.07, 1.083846, 1.07, 1.1, 3, 3250.0, DATE '2026-04-09', 'GIBBS, ISW'),
  ('GHD', 0.099, 1.1, 1.1, 1.1, 1.1, 3, 3426.0, DATE '2026-04-09', 'GIBBS, ISW'),
  ('GHD', 0.12, 1.13, 1.150769, 1.13, 1.22, 2, 650.0, DATE '2026-04-15', 'ISW'),
  ('GHD', 0.148, 1.13, 1.13, 1.13, 1.13, 1, 1500.0, DATE '2026-04-15', 'ISW'),
  ('GHD', 0.192, 1.22, 1.22, 1.22, 1.22, 1, 550.0, DATE '2026-01-07', 'ISW'),
  ('GMW', 0.016, 5.79, 5.725, 5.66, 5.79, 2, 100.0, DATE '2026-04-22', 'ISW'),
  ('GMW', 0.025, 4.8, 4.8, 4.8, 4.8, 1, 50.0, DATE '2026-03-11', 'ISW'),
  ('GMW', 0.03, 6.97, 6.97, 6.97, 6.97, 1, 25.0, DATE '2026-03-11', 'ISW'),
  ('GMW', 0.041, 2.75, 2.75, 2.75, 2.75, 1, 100.0, DATE '2026-04-15', 'GIBBS'),
  ('GMW', 0.047, 2.74, 2.74, 2.74, 2.74, 1, 500.0, DATE '2026-03-18', 'ISW'),
  ('GMW', 0.054, 2.54, 2.736, 2.54, 3.52, 2, 125.0, DATE '2026-04-09', 'ISW'),
  ('GMW', 0.105, 2.0, 1.977671, 1.89, 2.04, 3, 3650.0, DATE '2026-01-28', 'GIBBS, INTER'),
  ('GMW', 0.125, 1.91, 1.91, 1.91, 1.91, 1, 1500.0, DATE '2026-02-04', 'ISW'),
  ('HAST', 0.032, 50.04, 43.427143, 36.85, 51.19, 5, 2100.0, DATE '2026-03-11', 'ALLOY WIRE, ELGILOY'),
  ('HAST', 0.038, 76.71, 76.71, 76.71, 76.71, 1, 50.0, DATE '2026-03-04', 'ALLOY WIRE'),
  ('HD', 0.028, 1.95, 1.875, 1.8, 1.95, 2, 100.0, DATE '2026-04-15', 'ISW'),
  ('HD', 0.031, 1.54, 1.59, 1.54, 1.63, 2, 450.0, DATE '2026-02-11', 'ISW'),
  ('HD', 0.035, 1.56, 1.638, 1.56, 1.95, 2, 625.0, DATE '2026-03-25', 'ISW'),
  ('HD', 0.047, 4.28, 4.28, 4.28, 4.28, 1, 25.0, DATE '2026-04-22', 'ISW'),
  ('HD', 0.054, 1.08, 1.08, 1.08, 1.08, 1, 750.0, DATE '2026-02-04', 'ISW'),
  ('HD', 0.062, 0.85, 1.126667, 0.85, 2.01, 3, 375.0, DATE '2026-04-09', 'GIBBS, ISW'),
  ('HD', 0.072, 1.02, 0.916667, 0.88, 1.6, 4, 1560.0, DATE '2026-03-04', 'GIBBS'),
  ('HD', 0.08, 0.91, 0.91, 0.91, 0.91, 1, 275.0, DATE '2026-02-11', 'ISW'),
  ('HD', 0.091, 0.85, 0.873077, 0.85, 1.06, 4, 1300.0, DATE '2026-04-09', 'GIBBS, ISW'),
  ('HD', 0.099, 0.94, 0.914, 0.87, 0.94, 2, 3500.0, DATE '2026-04-29', 'GIBBS, ISW'),
  ('HD', 0.105, 0.91, 0.921287, 0.91, 2.05, 2, 2525.0, DATE '2026-01-28', 'GIBBS, ISW'),
  ('HD', 0.125, 0.91, 0.906842, 0.89, 0.91, 2, 950.0, DATE '2026-02-11', 'GIBBS, ISW'),
  ('HD', 0.177, 0.87, 0.87, 0.87, 0.87, 1, 200.0, DATE '2026-04-22', 'GIBBS'),
  ('HD', 0.192, 0.92, 0.92, 0.92, 0.92, 1, 4000.0, DATE '2026-04-15', 'ISW'),
  ('HD', 0.207, 1.18, 1.18, 1.18, 1.18, 1, 8000.0, DATE '2026-04-29', 'GIBBS'),
  ('HD', 0.25, 0.91, 0.91, 0.91, 0.91, 1, 2250.0, DATE '2026-01-28', 'ISW'),
  ('MW', 0.02, 2.8, 2.702, 2.66, 2.8, 3, 1000.0, DATE '2026-01-28', 'GIBBS, ISW'),
  ('MW', 0.023, 4.3, 4.3, 4.3, 4.3, 1, 25.0, DATE '2026-04-15', 'ISW'),
  ('MW', 0.026, 4.8, 3.716667, 2.55, 7.3, 3, 150.0, DATE '2026-04-20', 'GIBBS, ISW'),
  ('MW', 0.03, 2.26, 2.26, 2.26, 2.26, 1, 100.0, DATE '2026-04-22', 'GIBBS'),
  ('MW', 0.031, 3.95, 3.95, 3.95, 3.95, 1, 25.0, DATE '2026-04-15', 'ISW'),
  ('MW', 0.032, 2.2, 2.175, 2.15, 2.2, 2, 100.0, DATE '2026-03-11', 'GIBBS'),
  ('MW', 0.034, 2.44, 2.22, 2.11, 2.44, 3, 300.0, DATE '2026-03-26', 'GIBBS, ISW'),
  ('MW', 0.035, 3.19, 3.19, 3.19, 3.19, 1, 75.0, DATE '2026-02-25', 'ISW'),
  ('MW', 0.036, 2.15, 2.15, 2.15, 2.15, 1, 75.0, DATE '2026-01-28', 'ISW'),
  ('MW', 0.037, 1.99, 1.99, 1.99, 1.99, 1, 750.0, DATE '2026-01-07', 'INTER'),
  ('MW', 0.038, 2.03, 2.03, 2.03, 2.03, 1, 25.0, DATE '2026-01-14', 'GIBBS'),
  ('MW', 0.039, 1.8, 1.8, 1.8, 1.8, 1, 150.0, DATE '2026-01-07', 'INTER'),
  ('MW', 0.041, 1.93, 2.09697, 1.93, 2.38, 4, 825.0, DATE '2026-04-10', 'GIBBS, ISW'),
  ('MW', 0.042, 4.24, 3.135, 2.03, 4.24, 2, 50.0, DATE '2026-02-11', 'GIBBS, ISW'),
  ('MW', 0.043, 2.76, 2.76, 2.76, 2.76, 1, 50.0, DATE '2026-04-09', 'ISW'),
  ('MW', 0.045, 2.15, 2.15, 2.15, 2.15, 1, 75.0, DATE '2026-01-07', 'INTER'),
  ('MW', 0.047, 1.84, 1.84, 1.84, 1.84, 1, 50.0, DATE '2026-02-11', 'GIBBS'),
  ('MW', 0.048, 2.08, 2.08, 2.08, 2.08, 1, 75.0, DATE '2026-02-04', 'GIBBS'),
  ('MW', 0.051, 2.05, 2.05, 2.05, 2.05, 1, 25.0, DATE '2026-01-07', 'INTER'),
  ('MW', 0.054, 1.94, 1.94, 1.94, 1.94, 1, 1500.0, DATE '2026-02-04', 'GIBBS'),
  ('MW', 0.055, 5.33, 2.57, 2.11, 5.33, 2, 175.0, DATE '2026-04-29', 'ISW'),
  ('MW', 0.058, 2.05, 2.05, 2.05, 2.05, 1, 25.0, DATE '2026-01-07', 'INTER'),
  ('MW', 0.062, 1.39, 1.39, 1.39, 1.39, 1, 1500.0, DATE '2026-02-18', 'ISW'),
  ('MW', 0.063, 3.24, 2.87, 2.5, 3.24, 2, 50.0, DATE '2026-04-15', 'GIBBS, ISW'),
  ('MW', 0.067, 1.05, 1.05, 1.05, 1.05, 1, 150.0, DATE '2026-04-29', 'GIBBS'),
  ('MW', 0.07, 1.1, 1.1, 1.1, 1.1, 1, 8000.0, DATE '2026-02-18', 'ISW'),
  ('MW', 0.072, 1.2, 1.144444, 1.1, 1.2, 2, 2700.0, DATE '2026-03-11', 'GIBBS, ISW'),
  ('MW', 0.075, 1.12, 1.12, 1.12, 1.12, 1, 4500.0, DATE '2026-01-07', 'INTER'),
  ('MW', 0.078, 1.08, 1.39, 1.08, 2.01, 2, 150.0, DATE '2026-04-22', 'GIBBS'),
  ('MW', 0.08, 1.03, 1.036333, 1.03, 1.08, 3, 1500.0, DATE '2026-04-09', 'GIBBS, ISW'),
  ('MW', 0.087, 0.98, 0.98, 0.98, 0.98, 1, 200.0, DATE '2026-01-28', 'ISW'),
  ('MW', 0.088, 1.78, 1.78, 1.78, 1.78, 1, 100.0, DATE '2026-01-07', 'ISW'),
  ('MW', 0.09, 0.99, 0.99, 0.99, 0.99, 1, 6000.0, DATE '2026-01-14', 'ISW'),
  ('MW', 0.091, 1.05, 0.986364, 0.98, 1.05, 2, 1100.0, DATE '2026-04-22', 'GIBBS, ISW'),
  ('MW', 0.092, 2.17, 2.17, 2.17, 2.17, 1, 75.0, DATE '2026-04-22', 'ISW'),
  ('MW', 0.095, 1.01, 1.01, 1.01, 1.01, 1, 2500.0, DATE '2026-01-14', 'ISW'),
  ('MW', 0.098, 1.03, 1.03, 1.03, 1.03, 1, 300.0, DATE '2026-03-25', 'ISW'),
  ('MW', 0.105, 1.04, 1.035352, 1.01, 1.04, 2, 1775.0, DATE '2026-04-15', 'ISW'),
  ('MW', 0.106, 1.01, 0.996667, 0.98, 1.01, 2, 450.0, DATE '2026-01-14', 'ISW'),
  ('MW', 0.112, 0.98, 0.98, 0.98, 0.98, 1, 750.0, DATE '2026-01-07', 'ISW'),
  ('MW', 0.115, 0.98, 0.98, 0.98, 0.98, 1, 1250.0, DATE '2026-01-07', 'ISW'),
  ('MW', 0.118, 1.01, 1.01, 1.01, 1.01, 1, 100.0, DATE '2026-01-28', 'ISW'),
  ('MW', 0.12, 1.03, 1.020741, 0.98, 1.03, 3, 2700.0, DATE '2026-04-09', 'GIBBS, ISW'),
  ('MW', 0.125, 1.04, 1.003333, 0.99, 1.04, 2, 3750.0, DATE '2026-04-22', 'GIBBS, ISW'),
  ('MW', 0.135, 1.03, 1.024815, 1.01, 1.03, 2, 675.0, DATE '2026-04-01', 'ISW'),
  ('MW', 0.142, 1.01, 1.01, 1.01, 1.01, 1, 2000.0, DATE '2026-03-11', 'ISW'),
  ('MW', 0.148, 1.01, 0.998793, 0.98, 1.01, 4, 34800.0, DATE '2026-04-15', 'ISW'),
  ('MW', 0.156, 1.02, 0.988846, 0.98, 1.02, 3, 2600.0, DATE '2026-04-29', 'GIBBS, ISW'),
  ('MW', 0.162, 1.01, 1.01, 1.01, 1.01, 2, 3500.0, DATE '2026-02-04', 'ISW'),
  ('MW', 0.165, 1.04, 1.04, 1.04, 1.04, 1, 125.0, DATE '2026-04-15', 'ISW'),
  ('MW', 0.172, 1.04, 1.081818, 1.04, 1.5, 2, 550.0, DATE '2026-04-15', 'GIBBS, ISW'),
  ('MW', 0.177, 1.03, 1.013158, 0.99, 1.03, 3, 9500.0, DATE '2026-04-22', 'ISW'),
  ('MW', 0.187, 1.01, 1.019355, 1.01, 1.1, 6, 3100.0, DATE '2026-04-29', 'GIBBS, ISW'),
  ('MW', 0.192, 0.99, 0.993158, 0.99, 1.01, 2, 4750.0, DATE '2026-02-04', 'ISW'),
  ('MW', 0.2, 1.01, 1.01, 1.01, 1.01, 1, 100.0, DATE '2026-01-14', 'ISW'),
  ('MW', 0.218, 0.99, 0.9888, 0.97, 0.99, 2, 20000.0, DATE '2026-01-14', 'GIBBS, ISW'),
  ('MW', 0.283, 1.01, 1.01, 1.01, 1.01, 1, 200.0, DATE '2026-02-04', 'ISW'),
  ('OT', 0.072, 1.62, 1.62, 1.62, 1.62, 1, 700.0, DATE '2026-01-08', 'GIBBS'),
  ('OT', 0.148, 1.35, 1.35, 1.35, 1.35, 1, 3000.0, DATE '2026-02-18', 'ISW'),
  ('OT', 0.162, 1.35, 1.35, 1.35, 1.35, 1, 5000.0, DATE '2026-01-07', 'ISW'),
  ('OT', 0.177, 1.34, 1.337077, 1.29, 1.37, 5, 32500.0, DATE '2026-03-25', 'GIBBS, ISW'),
  ('OT', 0.187, 1.34, 1.276977, 1.16, 1.34, 4, 19712.0, DATE '2026-04-01', 'GIBBS, ISW'),
  ('OT', 0.207, 1.1, 1.1, 1.1, 1.1, 1, 14000.0, DATE '2026-01-14', 'GIBBS'),
  ('OT', 0.218, 1.19, 1.19, 1.19, 1.19, 1, 4250.0, DATE '2026-03-04', 'ISW'),
  ('OT', 0.375, 1.2, 1.1675, 1.15, 1.2, 3, 12000.0, DATE '2026-04-15', 'GIBBS, ISW'),
  ('PHOSB', 0.036, 19.47, 19.47, 19.47, 19.47, 1, 500.0, DATE '2026-03-11', 'ISW'),
  ('SG', 0.12, 1.06, 1.146, 1.06, 1.49, 2, 375.0, DATE '2026-04-29', 'ISW'),
  ('SS', 0.011, 10.59, 10.59, 10.59, 10.59, 1, 25.0, DATE '2026-04-22', 'ISW'),
  ('SS', 0.012, 7.98, 7.98, 7.98, 7.98, 1, 25.0, DATE '2026-03-04', 'ISW'),
  ('SS', 0.013, 5.6, 5.6, 5.6, 5.6, 1, 50.0, DATE '2026-04-22', 'GIBBS'),
  ('SS', 0.014, 7.16, 7.16, 7.16, 7.16, 1, 25.0, DATE '2026-01-28', 'ISW'),
  ('SS', 0.016, 6.17, 6.17, 6.17, 6.17, 1, 25.0, DATE '2026-04-29', 'GIBBS'),
  ('SS', 0.02, 4.84, 4.84, 4.84, 4.84, 1, 25.0, DATE '2026-03-18', 'GIBBS'),
  ('SS', 0.022, 3.89, 3.89, 3.89, 3.89, 1, 50.0, DATE '2026-01-28', 'ISW'),
  ('SS', 0.023, 3.67, 3.67, 3.67, 3.67, 1, 50.0, DATE '2026-03-25', 'ISW'),
  ('SS', 0.024, 4.71, 4.73, 4.71, 4.83, 2, 150.0, DATE '2026-04-29', 'GIBBS, ISW'),
  ('SS', 0.025, 3.54, 3.54, 3.54, 3.54, 1, 175.0, DATE '2026-02-11', 'ISW'),
  ('SS', 0.026, 5.14, 4.806, 3.47, 5.14, 3, 250.0, DATE '2026-04-02', 'INTER, ISW'),
  ('SS', 0.028, 3.66, 3.62, 3.54, 3.66, 2, 150.0, DATE '2026-03-11', 'ISW'),
  ('SS', 0.029, 1.98, 1.98, 1.98, 1.98, 1, 75.0, DATE '2026-02-25', 'GIBBS'),
  ('SS', 0.031, 2.77, 2.804286, 2.77, 2.89, 2, 175.0, DATE '2026-04-09', 'GIBBS, ISW'),
  ('SS', 0.032, 3.05, 2.894444, 2.77, 3.05, 2, 4500.0, DATE '2026-03-11', 'ISW'),
  ('SS', 0.035, 2.96, 2.9475, 2.91, 2.96, 2, 200.0, DATE '2026-02-04', 'INTER, ISW'),
  ('SS', 0.036, 2.96, 2.96, 2.96, 2.96, 1, 250.0, DATE '2026-02-04', 'ISW'),
  ('SS', 0.038, 3.05, 3.05, 3.05, 3.05, 1, 150.0, DATE '2026-03-04', 'ISW'),
  ('SS', 0.039, 2.77, 2.77, 2.77, 2.77, 1, 525.0, DATE '2026-04-15', 'ISW'),
  ('SS', 0.041, 2.61, 2.61, 2.61, 2.61, 1, 75.0, DATE '2026-03-25', 'ISW'),
  ('SS', 0.042, 2.87, 2.87, 2.87, 2.87, 1, 100.0, DATE '2026-03-11', 'ISW'),
  ('SS', 0.044, 2.75, 2.75, 2.75, 2.75, 1, 75.0, DATE '2026-04-09', 'ISW'),
  ('SS', 0.047, 2.61, 2.837761, 2.61, 2.98, 5, 1675.0, DATE '2026-04-09', 'GIBBS, ISW'),
  ('SS', 0.05, 4.07, 3.083333, 2.59, 4.07, 2, 75.0, DATE '2026-04-29', 'ISW'),
  ('SS', 0.054, 2.79, 2.79, 2.79, 2.79, 1, 500.0, DATE '2026-01-07', 'ISW'),
  ('SS', 0.055, 2.59, 2.82, 2.59, 3.23, 3, 200.0, DATE '2026-04-01', 'GIBBS, ISW'),
  ('SS', 0.058, 2.9, 2.9, 2.9, 2.9, 1, 50.0, DATE '2026-01-07', 'INTER'),
  ('SS', 0.06, 2.52, 2.52, 2.52, 2.52, 1, 200.0, DATE '2026-04-29', 'ISW'),
  ('SS', 0.062, 2.52, 2.934545, 2.52, 6.22, 3, 275.0, DATE '2026-04-22', 'GIBBS, ISW'),
  ('SS', 0.063, 2.52, 2.604615, 2.52, 2.95, 5, 455.0, DATE '2026-04-09', 'GIBBS, INTER, ISW'),
  ('SS', 0.067, 3.0, 2.906667, 2.86, 3.0, 2, 75.0, DATE '2026-02-04', 'GIBBS, INTER'),
  ('SS', 0.068, 2.45, 2.45, 2.45, 2.45, 1, 75.0, DATE '2026-03-18', 'GIBBS'),
  ('SS', 0.07, 2.39, 2.39, 2.39, 2.39, 1, 350.0, DATE '2026-04-09', 'ISW'),
  ('SS', 0.072, 2.03, 2.03, 2.03, 2.03, 1, 50.0, DATE '2026-01-08', 'GIBBS'),
  ('SS', 0.08, 2.96, 1.863465, 1.78, 2.96, 4, 3175.0, DATE '2026-03-25', 'GIBBS, INTER, ISW'),
  ('SS', 0.085, 1.85, 1.85, 1.85, 1.85, 1, 275.0, DATE '2026-01-14', 'ISW'),
  ('SS', 0.086, 1.85, 1.85, 1.85, 1.85, 1, 250.0, DATE '2026-04-22', 'ISW'),
  ('SS', 0.091, 1.85, 1.915, 1.85, 1.98, 2, 200.0, DATE '2026-03-25', 'ISW'),
  ('SS', 0.093, 1.85, 1.85, 1.85, 1.85, 3, 525.0, DATE '2026-03-30', 'ISW'),
  ('SS', 0.095, 1.85, 1.85, 1.85, 1.85, 1, 200.0, DATE '2026-02-26', 'ISW'),
  ('SS', 0.098, 1.85, 1.85, 1.85, 1.85, 1, 225.0, DATE '2026-04-15', 'ISW'),
  ('SS', 0.1, 1.85, 1.85, 1.85, 1.85, 1, 200.0, DATE '2026-04-09', 'ISW'),
  ('SS', 0.105, 1.85, 1.85, 1.85, 1.85, 3, 1250.0, DATE '2026-04-09', 'ISW'),
  ('SS', 0.112, 1.85, 1.887143, 1.85, 1.98, 2, 350.0, DATE '2026-02-04', 'ISW'),
  ('SS', 0.116, 1.85, 1.85, 1.85, 1.85, 2, 850.0, DATE '2026-01-28', 'ISW'),
  ('SS', 0.118, 3.48, 3.48, 3.48, 3.48, 1, 25.0, DATE '2026-04-15', 'ISW'),
  ('SS', 0.125, 1.85, 1.85, 1.85, 1.85, 3, 700.0, DATE '2026-04-15', 'ISW'),
  ('SS', 0.135, 3.64, 3.64, 3.64, 3.64, 1, 600.0, DATE '2026-01-28', 'ISW'),
  ('SS', 0.148, 1.85, 1.85, 1.85, 1.85, 1, 1000.0, DATE '2026-03-25', 'ISW'),
  ('SS', 0.156, 1.85, 1.870741, 1.85, 1.92, 2, 675.0, DATE '2026-04-09', 'GIBBS, ISW'),
  ('SS', 0.162, 1.85, 1.85, 1.85, 1.85, 2, 3900.0, DATE '2026-01-28', 'ISW'),
  ('SS', 0.177, 1.85, 1.85, 1.85, 1.85, 1, 1500.0, DATE '2026-01-28', 'ISW'),
  ('SS', 0.187, 1.85, 1.85, 1.85, 1.85, 1, 475.0, DATE '2026-04-09', 'ISW'),
  ('SS', 0.192, 1.85, 1.85, 1.85, 1.85, 1, 2600.0, DATE '2026-01-07', 'ISW'),
  ('SS', 0.207, 1.85, 1.85, 1.85, 1.85, 2, 850.0, DATE '2026-03-25', 'ISW'),
  ('SS', 0.234, 1.85, 1.85, 1.85, 1.85, 1, 300.0, DATE '2026-01-07', 'ISW'),
  ('SS', 0.25, 1.85, 1.85, 1.85, 1.85, 1, 3000.0, DATE '2026-04-09', 'ISW'),
  ('SS', 0.312, 2.04, 2.027148, 1.8, 2.38, 4, 15250.0, DATE '2026-04-15', 'GIBBS, ISW'),
  ('SS177', 0.032, 4.75, 4.75, 4.75, 4.75, 1, 25.0, DATE '2026-01-07', 'INTER'),
  ('SS177', 0.042, 4.59, 4.59, 4.59, 4.59, 1, 100.0, DATE '2026-04-09', 'ISW'),
  ('SS177', 0.045, 4.49, 4.49, 4.49, 4.49, 1, 150.0, DATE '2026-04-09', 'ISW'),
  ('SS177', 0.047, 4.52, 4.52, 4.52, 4.52, 1, 500.0, DATE '2026-02-04', 'GIBBS'),
  ('SS177', 0.051, 4.88, 4.88, 4.88, 4.88, 1, 50.0, DATE '2026-01-07', 'ISW'),
  ('SS177', 0.06, 4.39, 4.39, 4.39, 4.39, 1, 400.0, DATE '2026-01-21', 'GIBBS'),
  ('SS177', 0.062, 1.63, 1.63, 1.63, 1.63, 1, 100.0, DATE '2026-03-18', 'ISW'),
  ('SS177', 0.065, 5.22, 5.356667, 4.7, 6.15, 3, 75.0, DATE '2026-03-26', 'GIBBS, INTER, ISW'),
  ('SS177', 0.067, 4.22, 4.405, 4.22, 4.59, 2, 100.0, DATE '2026-04-15', 'ISW'),
  ('SS177', 0.105, 3.73, 3.752222, 3.73, 3.93, 2, 675.0, DATE '2026-04-22', 'ISW'),
  ('SS177', 0.12, 3.67, 3.66, 3.65, 3.67, 2, 150.0, DATE '2026-03-26', 'GIBBS, ISW'),
  ('SS177', 0.125, 3.43, 3.43, 3.43, 3.43, 1, 1250.0, DATE '2026-04-15', 'GIBBS'),
  ('SS177', 0.13, 3.53, 3.53, 3.53, 3.53, 1, 350.0, DATE '2026-03-25', 'GIBBS'),
  ('SS177', 0.148, 3.48, 3.48, 3.48, 3.48, 1, 500.0, DATE '2026-03-25', 'GIBBS'),
  ('SS177', 0.156, 3.67, 3.67, 3.67, 3.67, 1, 75.0, DATE '2026-04-09', 'ISW'),
  ('SS177', 0.162, 3.6, 3.536364, 3.5, 3.6, 2, 550.0, DATE '2026-04-15', 'GIBBS'),
  ('SS177', 0.177, 3.67, 3.548235, 3.44, 3.67, 2, 4250.0, DATE '2026-02-18', 'GIBBS, ISW'),
  ('SS177', 0.192, 3.36, 3.36, 3.36, 3.36, 1, 350.0, DATE '2026-02-25', 'GIBBS'),
  ('SS177', 0.207, 3.59, 3.59, 3.59, 3.59, 1, 750.0, DATE '2026-01-21', 'GIBBS'),
  ('SS177', 0.262, 3.67, 3.67, 3.67, 3.67, 1, 1750.0, DATE '2026-04-15', 'ISW'),
  ('SS177', 0.362, 3.81, 3.5348, 3.38, 3.81, 2, 2500.0, DATE '2026-04-09', 'GIBBS, ISW');

-- 8.7 Surcharges de aleacion (solo los marcados applies_to_quote entran al precio)
INSERT INTO surcharge (code, alloy, per_lb, prev_per_lb, effective_date, updated_date, applies_to_quote, in_isc_material_list, note) VALUES
  ('SS', '302 / 304', 1.3, 1.29, DATE '2026-05-01', DATE '2026-04-27', TRUE, TRUE, NULL),
  ('SS177', '17/7 PH (631)', 1.62, 1.61, DATE '2026-05-01', DATE '2026-04-27', TRUE, TRUE, NULL),
  ('316', '316', 2.11, 2.08, DATE '2026-05-01', DATE '2026-04-27', TRUE, TRUE, NULL),
  ('XM19', 'N50 (XM19)', 1.97, 1.93, DATE '2026-05-01', DATE '2026-04-27', FALSE, FALSE, 'Not in ISC material list yet'),
  ('304LVM', '304LVM', 1.54, 1.55, DATE '2026-05-01', DATE '2026-04-27', FALSE, FALSE, 'Not in ISC material list yet'),
  ('316LVM', '316LVM', 2.79, 2.79, DATE '2026-05-01', DATE '2026-04-27', FALSE, FALSE, 'Not in ISC material list yet'),
  ('SS174', '17/4 PH (630)', 1.39, 1.39, DATE '2026-05-01', DATE '2026-04-27', FALSE, FALSE, 'Not in ISC material list yet');

-- 8.8 Maquinas del taller (30)
INSERT INTO machine (name, family, m1_code, setup_h, pph, purchase_usd, labor_usd_h, amort_years, load_pct,
  hours_per_year, oee, cost_rate_usd_h, ccv_target_usd_h, wire_min_mm, wire_max_mm, od_max_mm,
  cap_compression, cap_extension, cap_torsion, setup_class, uses, risk) VALUES
  ('AIM 3000', 'COILER', 'AIM30', 6.0, 327.0, 700000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 80, 80, 0.8, 6.0, 80.0, TRUE, TRUE, TRUE, 'High', 'High-capability CNC former. Complex geometries, all three spring types, medium-to-large wire.', 'Highest setup time and tooling cost; reserve for complex or higher-value parts.'),
  ('AIM AFM-3D2-T', 'COILER', '3D2T', 2.0, 450.0, 250000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 25, 25, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('NUCOIL CSF-200', 'COILER', 'NUCO2', 6.0, 327.0, 200000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 20, 20, 0.15, 2.0, 25.0, TRUE, TRUE, FALSE, 'Medium', 'Fine-wire compression / extension coiler. Efficient for small high-volume parts.', 'No torsion capability; restricted OD and wire range.'),
  ('NUCOIL CSF-400', 'COILER', 'NUCOI', 6.0, 327.0, 300000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 30, 30, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('NUCOIL HX-60', 'COILER', 'HX-60', 10.0, 327.0, 400000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 40, 40, 1.0, 6.0, 90.0, TRUE, TRUE, FALSE, 'Medium', 'Heavy-duty coiler for larger compression and extension springs.', 'No torsion capability; limited for complex end forming.'),
  ('SIMPLEX MC 50', 'COILER', 'MC50', 5.0, 600.0, 650000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 60, 60, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('KMH-516', 'COILER', 'K516', 5.0, 600.0, 100000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 20, 20, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('KMH-508', 'COILER', 'K508', 5.0, 600.0, 100000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 20, 20, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('SHINKO TF-45', 'COILER', 'TF-45', 10.0, 327.0, 700000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 50, 50, 0.5, 4.5, 55.0, TRUE, TRUE, TRUE, 'High', 'Mid-range precision CNC former. Versatile for all types in the medium wire band.', 'Setup-intensive; over-capable (uneconomic) for simple high-volume parts.'),
  ('SHINKO TF-23', 'COILER', 'TF-23', 10.0, 327.0, 400000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 40, 40, 0.2, 2.3, 30.0, TRUE, TRUE, TRUE, 'High', 'Fine-wire precision CNC former. Small intricate springs, tight tolerances, all types.', 'Not suitable for larger wire; setup-intensive for simple parts.'),
  ('ZX250', 'COILER', 'ZX250', 6.0, 450.0, 250000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 25, 25, 0.3, 2.5, 32.0, TRUE, TRUE, TRUE, 'Medium', 'Compact CNC former. Good all-round machine for small / medium parts of all types.', 'Limited to small wire and OD; verify torsion tooling availability.'),
  ('AUTOLINK', 'COILER', 'AUTOL', 6.0, 600.0, 250000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 30, 30, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('TORIN (FENN) FZ-11', 'COILER', 'FZ-11', 3.0, 600.0, 200000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 20, 20, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('TORIN (FENN) W10A', 'COILER', 'W10A', 3.0, 600.0, 150000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 15, 15, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('TORIN (FENN) W115A', 'COILER', 'W115', 3.0, 600.0, 150000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 15, 15, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('TORIN (FENN) W11A', 'COILER', 'W11A', 3.0, 600.0, 150000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 15, 15, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('TORIN (FENN) W11T', 'COILER', 'W11T', 3.0, 600.0, 150000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 15, 15, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('TORIN (FENN) W125', 'COILER', 'W125', 3.0, 600.0, 150000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 15, 15, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('TORIN (FENN) W12T', 'COILER', 'W12T', 3.0, 600.0, 150000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 15, 15, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('TORIN (FENN) Z-11', 'COILER', 'Z-11', 3.0, 600.0, 150000.0, 40.0, 7.0, 1.0, 1920.0, 0.8, 15, 15, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('Grinder A', 'SECONDARY', 'SEC', 1.0, NULL, 150000.0, 27.0, 7.0, 1.0, 1920.0, 0.6, 15, 15, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('Grinder B', 'SECONDARY', 'SEC', 1.0, NULL, 140000.0, 27.0, 7.0, 1.0, 1920.0, 0.6, 15, 15, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('Grinder C', 'SECONDARY', 'SEC', 1.0, NULL, 130000.0, 27.0, 7.0, 1.0, 1920.0, 0.6, 15, 15, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('Grinder D', 'SECONDARY', 'SEC', 1.0, NULL, 120000.0, 27.0, 7.0, 1.0, 1920.0, 0.6, 15, 15, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('Grinder PED', 'SECONDARY', 'SEC', 1.0, NULL, 80000.0, 27.0, 7.0, 1.0, 1920.0, 0.6, 8, 8, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('Stationary Oven', 'SECONDARY', 'SEC', 3.0, NULL, 120000.0, 27.0, 7.0, 1.0, 1920.0, 0.6, 10, 10, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('Looping / Hooks', 'SECONDARY', 'SEC', 1.0, NULL, NULL, 27.0, 7.0, 1.0, 1920.0, 0.6, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('Bending / Kick', 'SECONDARY', 'SEC', 1.0, NULL, NULL, 27.0, 7.0, 1.0, 1920.0, 0.6, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('Assembly', 'SECONDARY', 'SEC', 1.0, NULL, NULL, 27.0, 7.0, 1.0, 1920.0, 0.6, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
  ('Inspection / Sorting', 'SECONDARY', 'SEC', 1.0, NULL, NULL, 27.0, 7.0, 1.0, 1920.0, 0.6, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);

-- 8.9 Subcontratistas y sus servicios
INSERT INTO subcontractor (id, name, quote_date, certs_usd, loop_trip_usd, skid_max_lb, strip_per_lb) VALUES
  (1, 'C&R Plating', DATE '2025-09-12', 11, 150, 2400, NULL),
  (2, 'Commercial Plating', NULL, 0, 120, 2400, 0.2);
SELECT setval(pg_get_serial_sequence('subcontractor','id'), (SELECT max(id) FROM subcontractor));

INSERT INTO subcontractor_service (subcontractor_id, service, min_usd, per_lb, per_pc) VALUES
  (1, 'Zinc Plate No Bake', 45.0, 0.52, NULL),
  (1, 'Zinc Plate Clear Bake', 55.0, 0.53, NULL),
  (1, 'Zinc Plate Yellow Bake', 60.0, 0.583, NULL),
  (1, 'Passivate', 40.0, 0.32, NULL),
  (1, 'Zinc Plate (Black) Bake', 100.0, 1.05, NULL),
  (1, 'Plating Certs', 11.0, NULL, NULL),
  (2, 'Zinc & Clear', 150.0, NULL, NULL),
  (2, 'Zinc Clear & Bake', 175.0, NULL, NULL),
  (2, 'Zinc Yellow & Bake', 200.0, NULL, NULL);

-- 8.10 Historico de acabados / plating por PN (116)
INSERT INTO plating_history (pn, customer_name, finish, per_lb, raw_text, notes) VALUES
  ('5281', 'AFC', 'Zinc-Clear & Bake', 0.85, NULL, NULL),
  ('98-3003', 'American Dish', 'Zinc Plate', 0.25, NULL, NULL),
  ('98-3011', 'American Dish', 'Zinc Plate', 0.22, NULL, NULL),
  ('ACC-390-0007', 'B & W', 'Zinc - Trivalent Clear & Bake', NULL, '0.40  min 175', NULL),
  ('3025-119PL', 'B&W Saddle Pins', 'Zinc Plate', 0.2, NULL, NULL),
  ('50N225SPTZ', 'B&W Truck Beds', 'Zinc-Clear & Bake', 0.235, NULL, NULL),
  ('034-8025-00', 'Bad Boy', 'Zinc-Yellow & Bake', 0.26, NULL, NULL),
  ('034-8045-00', 'Bad Boy', 'Zinc-Yellow & Bake', 0.35, NULL, NULL),
  ('034-9050-00', 'Bad Boy', 'Zinc-Yellow & Bake', 0.33, NULL, NULL),
  ('034-2009-00', 'Bad Boy/Arkansas Bolt/Eidos', 'Zinc-Yellow & Bake', 0.28, NULL, NULL),
  ('034-2020-00', 'BadBoy', 'Zinc-Clear & Bake', 0.235, NULL, NULL),
  ('034-2030-00', 'BadBoy', 'Zinc-Clear & Bake', 0.265, NULL, NULL),
  ('C730X075X4', 'Bax Sales', 'Zinc- Clear and Bake', NULL, '$1.00/lb $175 min', NULL),
  ('518487', 'Bobcat', 'Zinc- Clear and Bake', 0.45, NULL, NULL),
  ('27127', 'Cardinal Components', 'Zinc-Clear & Bake', 0.72, NULL, NULL),
  ('MA12', 'Community Products', 'Zinc-Yellow & Bake', 0.3, NULL, NULL),
  ('90P04P', 'Construction Products', 'Zinc-Clear & Bake', 0.33654, NULL, NULL),
  ('1A0744', 'Cross Manufacturing', 'Zinc-Trivalent Clear & Bake', 0.65, NULL, NULL),
  ('21148', 'Danuser Machine Company', 'Zinc-Clear & Bake', 0.2451, NULL, NULL),
  ('Z3CS', 'Decker', 'Zinc-Clear & Bake', 0.382, NULL, NULL),
  ('462159Z2', 'Deco Products', 'Zinc-Clear & Bake', 1.5, NULL, NULL),
  ('DCP10607', 'Dual Dunamics Inc', 'Zinc-Yellow & Bake', 0.58, NULL, NULL),
  ('008938', 'Excel Ind', 'Zinc-Clear & Bake', 0.235, NULL, NULL),
  ('607146', 'Excel Ind', 'Zinc-Clear & Bake', 0.382, NULL, NULL),
  ('601051', 'Excel Ind', 'Zinc-Clear & Bake', 0.235, NULL, NULL),
  ('601131', 'Excel Ind', 'Zinc-Clear & Bake', 0.7, NULL, NULL),
  ('8938', 'Excel Industriel', 'Zinc-Clear & Bake', 0.235, NULL, NULL),
  ('036384', 'Excel Industriel', 'Zinc-Clear & Bake', 0.34, NULL, NULL),
  ('008938', 'Excel Industries', 'Zinc - Trivalent Clear & Bake', NULL, NULL, NULL),
  ('K-105-PLATED', 'Fairfield Ind', 'Zinc-Clear & Bake', 1.15, NULL, NULL),
  ('K-105L-PLATED', 'FAIRFIELD INDUSTRIES INC', 'ZINC-CLEAR AND BAKE', 1.15, NULL, NULL),
  ('10760-06470', 'Fastenal', 'Zinc-Clear & Bake', 0.36, NULL, NULL),
  ('8370998', 'Fawn', 'Zinc Plate', 0.267, NULL, NULL),
  ('230325672', 'Femco Inc.', 'Zinc-Clear & Bake', 0.42, NULL, NULL),
  ('230325683', 'Femco Inc.', 'Zinc-Clear & Bake', 0.42, NULL, NULL),
  ('5019755', 'Fimco', 'Zinc-Clear & Bake', 0.32, NULL, NULL),
  ('807-273C', 'Great Plains  Manufacturing', 'Zinc-Yellow & Bake', 0.36, NULL, NULL),
  ('807-350C', 'Great Plains  Manufacturing', 'Zinc- Clear and Bake', 0.55, NULL, NULL),
  ('155213-01', 'Great Plains Industries', 'Zinc-Clear & Bake', 0.55, NULL, NULL),
  ('807-236C', 'Great Plains Manufacturing', 'Zinc- Clear and Bake', NULL, '$175 Min', NULL),
  ('807-068C', 'Great Plains MFG', 'Zinc-Clear & Bake', 0.28, NULL, NULL),
  ('807-367C', 'Great Plains MFG', 'Zinc-Clear & Bake', 0.33, NULL, NULL),
  ('807-185C', 'Great Plains MFG', 'Zinc-Yellow & Bake', 0.34, NULL, NULL),
  ('323245', 'Hahn Equip/Exmark MFG', 'Zinc-Yellow & Bake', 0.3, NULL, NULL),
  ('HDICT-14', 'Harper Trucks, Inc', 'Zinc-Clear & Bake', 0.85, NULL, NULL),
  ('T2050450', 'Hubbell Power Systems', 'Zinc - Clear', NULL, NULL, NULL),
  ('539118762', 'Husqvarna', 'Zinc-Yellow & Bake', 0.29, NULL, NULL),
  ('575230201', 'Husqvarna', 'Zinc-TRIVALENT Yellow & Bake', 0.45, NULL, NULL),
  ('670300030', 'Hydraulic Components', 'Zinc-Clear & Bake', 0.525, NULL, NULL),
  ('670300020', 'Hydraulic Components', 'Zinc-Clear & Bake', NULL, NULL, NULL),
  ('333055', 'Iowa Spring', 'Zinc-Clear & Bake', 0.323, NULL, NULL),
  ('333042', 'Iowa Spring', 'Zinc- Clear and Bake', 0.85, NULL, NULL),
  ('52047', 'Iowa Spring', 'Zinc- Clear and Bake', 0.5, NULL, NULL),
  ('3046601', 'JCI Ruskin', 'Zinc-Clear & Bake', 1.15, NULL, NULL),
  ('88003100', 'JCI Ruskin', 'Zinc-Clear & Bake', NULL, NULL, NULL),
  ('NK8053', 'Kreg Tool', 'Zinc-Clear & Bake', 0.21, NULL, NULL),
  ('2553040', 'Lislie Corp', 'Zinc- Clear and Bake', 0.8, NULL, NULL),
  ('WTR00181', 'LoadKing', 'Zinc-Clear & Bake', 0.3, NULL, NULL),
  ('283852', 'Moridge', 'Zinc-Clear & Bake', NULL, NULL, NULL),
  ('283516', 'Moridge', 'Zinc-Yellow & Bake', 0.42, NULL, NULL),
  ('284428', 'Moridge', 'Zinc-Yellow & Bake', 0.34, NULL, NULL),
  ('283823', 'Moridge', 'Zinc-Yellow & Bake', 0.43, NULL, NULL),
  ('283848', 'Moridge', 'Zinc-Yellow & Bake', 0.33, NULL, NULL),
  ('284429', 'Moridge', 'Zinc-Yellow & Bake', 0.35, NULL, NULL),
  ('283389', 'Moridge Manufacturing Inc.', 'Zinc-Yellow & Bake', NULL, NULL, NULL),
  ('283988', 'Moridge Manufacturing Inc.', 'Zinc - Yellow & Bake', 0.4, NULL, NULL),
  ('ISC-1625-Plate', 'Nolin', 'Zinc-Yellow & Bake', 0.355, NULL, NULL),
  ('670300001', 'Prince Manufacturing', 'Zinc- Clear and Bake', 0.65, NULL, NULL),
  ('ISC-7994', 'R. H. Fastener', 'Zinc- Clear and Bake', 0.65, NULL, NULL),
  ('2750083', 'Regal Beloit', 'Zinc - Clear and Bake', NULL, NULL, NULL),
  ('831115527', 'RH Fast', 'Zinc-Yellow & Bake', 0.26, NULL, NULL),
  ('100040', 'Schiller grounds care', 'Zinc- Clear and Bake', 0.44, NULL, NULL),
  ('61021101', 'SKF', 'Zinc-Clear & Bake', 0.6, NULL, NULL),
  ('87A373', 'Smith & Loveless', 'Zinc-Clear & Bake', NULL, NULL, NULL),
  ('6231176', 'SOR', 'Zinc-Clear & Bake', 0.25, NULL, NULL),
  ('102E', 'Stone Manufacturing', 'Zinc-Clear Plate', 0.4, NULL, NULL),
  ('FD48642', 'T - L Irrigation Company', 'Zinc - Clear and Bake', NULL, '$.30  min 175.00', NULL),
  ('ISC-7487', 'TCD Parts', 'Zinc-Clear & Bake', 0.32, NULL, NULL),
  ('ISC-7060', 'Timber King', 'Zinc- Clear and Bake', NULL, '$175 min.', NULL),
  ('138-0678', 'Toro', 'Zinc-Clear & Bake', 0.242, NULL, NULL),
  ('138-7228', 'Toro', 'Zinc-Clear & Bake', 0.3, NULL, NULL),
  ('138-7252', 'Toro', 'Zinc-Clear & Bake', 0.35, NULL, NULL),
  ('138-7264', 'Toro', 'Zinc-Clear & Bake', 0.3, NULL, NULL),
  ('109-0148', 'Toro', 'Zinc-Clear & Bake', 0.235, NULL, NULL),
  ('108-4052', 'Toro', 'Zinc-Yellow & Bake', 0.65, NULL, NULL),
  ('103-4281', 'Toro', 'Zinc-Yellow & Bake', 0.26, NULL, NULL),
  ('103-7997', 'Toro', 'Zinc-Yellow & Bake', 0.35, NULL, NULL),
  ('109-2230', 'Toro', 'Zinc-Yellow & Bake', 0.26, NULL, NULL),
  ('109-7124', 'Toro', 'Zinc-Yellow & Bake', 0.35, NULL, NULL),
  ('1-603693', 'Toro', 'Zinc-Yellow & Bake', 0.29, NULL, NULL),
  ('1-603402', 'Toro', 'Zinc-Yellow & Bake', 0.35, NULL, NULL),
  ('1-603414', 'Toro', 'Zinc-Yellow & Bake', 0.33, NULL, NULL),
  ('1-603807', 'Toro', 'Zinc-Yellow & Bake', 0.33, NULL, NULL),
  ('1-653331', 'Toro', 'Zinc-Yellow & Bake', 0.31, NULL, NULL),
  ('1-653544', 'Toro', 'Zinc-Yellow & Bake', 0.31, NULL, NULL),
  ('108-4056', 'Toro', 'Zinc-Yellow & Bake', 0.385, NULL, NULL),
  ('1-323161', 'Toro', 'Zinc-Bake & Black', 1.08, NULL, NULL),
  ('116-8470', 'Toro', 'Zinc-Yellow & Bake', 0.36, NULL, NULL),
  ('103-7398', 'Toro', 'Zinc-Yellow & Bake', NULL, NULL, NULL),
  ('1-633454', 'Toro', 'Zinc-Yellow & Bake', 0.36, NULL, NULL),
  ('103-1767', 'Toro', 'Zinc - Yellow & Bake', NULL, NULL, NULL),
  ('1-323071', 'Toro', 'Zinc - Black and Bake', NULL, '$300 Min', NULL),
  ('1-323245', 'Toro/Midwest Control', 'Zinc-Yellow & Bake', 0.35, NULL, NULL),
  ('PRT-832', 'Triangle MFG', 'Zinc-Yellow & Bake', 0.515, NULL, NULL),
  ('NSN-5360-88-200-1495', 'US Postal', 'Zinc-Yellow & Bake', 0.55, NULL, NULL),
  ('523327', 'WorldLawn', 'Zinc-Clear & Bake', 0.35, NULL, NULL),
  ('523278', 'WorldLawn', 'Zinc-Clear & Bake', 0.7, NULL, NULL),
  ('523109', 'WorldLawn', 'Zinc-Clear & Bake', 0.28, NULL, NULL),
  ('543520', 'WorldLawn', 'Zinc-Clear & Bake', 0.42, NULL, NULL),
  ('633382', 'Worldlawn', 'Zinc-Clear & Bake', NULL, '$0.23/$175 MIN', NULL),
  ('4113746', 'Bobcat', 'Zinc-Clear & Bake', 0.45, NULL, NULL),
  ('2553040', 'Lisle Corp.', 'Zinc-Clear & Bake', 0.8, NULL, NULL),
  ('284427', 'Moridge', 'Zinc-Clear & Bake', NULL, '$200 Min', NULL),
  ('7134220', 'Components Company', 'Zinc-Clear & Bake', NULL, '$175 min.', NULL),
  ('FSC455398', 'VC999 Packaging Systems', 'Zinc-Clear & Bake', NULL, '$175 min.', NULL),
  ('103-0265', 'Toro', 'Zinc-Yellow & Bake', 1.25, NULL, NULL);

-- 8.11 Catalogo de empaque (16)
INSERT INTO packing (id, code, description, supplier, price_usd, uom, default_per_box) VALUES
  (1, 'COR100803', '10 X 8 X 3 BOX', 'SIP', 0.63, 'EACH', NULL),
  (2, 'COR08010', '8X6X6 RSC STOCK CARTON', 'SIP', 0.4, 'EACH', NULL),
  (3, 'COR08030', '8x8x8  RSC-Glued 32ECT KFT PLN*', 'SIP', 0.48, 'EACH', NULL),
  (4, 'COR18002', '18X8X4 RSC STOCK CARTON (Sportworks)', 'SIP', 0.69, 'EACH', NULL),
  (5, 'CHP12012', '12" X 12" 22 pt. Chipboard Pad', 'SIP', 0.16, 'EACH', NULL),
  (6, 'COR11050', '11-1/4X8-3/4X12 RSC STK CTN  (Common Boxes)', 'SIP', 0.83, 'EACH', NULL),
  (7, 'COR121212U', '12x12x12 (10,8,6) RSC Stock Carton Boxes', 'SIP', 0.73, 'EACH', NULL),
  (8, 'COR14040', '14x14x14 RSC Stock Carton Boxes', 'SIP', 1.33, 'EACH', NULL),
  (9, 'COR24027A', '24" X 12" X 12" Double Wall Box', 'SIP', 1.95, 'EACH', NULL),
  (10, 'COR_ROW_11', 'DOUBLE WALL 12 x 12 x 12 rsc 48ect plain kraft', 'SIP', 1.67, 'EACH', NULL),
  (11, 'COR11812HD /-NON-INVETORY', '11 1/4 x 8 3/4 x 12 BOX HEAVY DUTY (US POSTAL & Toro MEXICO', 'SIP', 1.28, 'EACH', NULL),
  (12, 'COR240606', '24" x 6" x 6" Stock Carton Boxes (Sportworks)', 'SIP', 0.72, 'EACH', NULL),
  (13, 'TACKY BOARD 11 7/8" X 11 7/8"', 'TACKY BOARD 11 7/8" X 11 7/8"', 'PRESON', 0.52634, 'EACH', NULL),
  (14, 'barrels no lids', '30 gallon drums unlined', 'obry', 5.5, 'EACH', NULL),
  (15, 'barrels no lids', '38 gallon drums unlined', 'obry', 6.5, 'EACH', NULL),
  (16, 'GAYLORD', 'GAYLORD — special packaging', 'ISC', 30.0, 'EACH', NULL);
SELECT setval(pg_get_serial_sequence('packing','id'), (SELECT max(id) FROM packing));

-- 8.12 BRAIN: metadatos, reglas, glosario y etapas
INSERT INTO brain_meta (id, version, built_at, banner, offer_standard_remark) VALUES
  (1, '18.0.1-DEMO', DATE '2026-07-14', 'The best price for CGR is the highest price the customer can pay.', 'ISC will produce against SMI Tolerances. Block tolerances will remain referential.');

INSERT INTO brain_rule (category, seq, rule_text) VALUES
  ('CGR_INTERNATIONAL', 1, 'All prices must be validated by Miguel Rodea, Plant Manager.'),
  ('CGR_INTERNATIONAL', 2, 'When targeting a strategic project or order, CGR quotes with the best processes, best cycle times, and best technology.'),
  ('CGR_INTERNATIONAL', 3, 'Customers pay for all activities engineered in the quote. Processes may not be eliminated to flex the price.'),
  ('CGR_INTERNATIONAL', 4, 'Customers do not pay for lack of productivity: overtime, scrap above 5%, or slow cycle times.'),
  ('CGR_INTERNATIONAL', 5, 'All parts must be profitable at the quote level, per the Business Model for each product.'),
  ('CGR_INTERNATIONAL', 6, 'Plant overheads must always be covered in the piece price: 12% to 28% of selling price by operation count (CGR principle range 10-35%).'),
  ('CGR_INTERNATIONAL', 7, 'HQ costs must always be covered in the piece price: 5% of selling price.'),
  ('CGR_INTERNATIONAL', 8, 'When applicable, Sales Representative commissions must be covered in the selling price.'),
  ('CGR_ISC', 1, 'No job below $800 USD. A single coiling operation floors at $800.'),
  ('CGR_ISC', 2, 'Each additional operation is charged at a minimum of $200 USD. Example: Coiling + Grinding + Secondary + Plating = $1,400.'),
  ('CGR_ISC', 3, 'No job is launched or released to the floor without an order.'),
  ('CGR_ISC', 4, 'A job may be created, released, and produced when backed by a forecast, order, open PO, or similar customer commitment.'),
  ('CGR_ISC', 5, 'For low-volume jobs with minimal material consumption, protect against obsolescence and excess inventory: if the supplier MOQ exceeds the needed material, quote the pieces at the cost of the MOQ, or offer a larger-quantity option that consumes the MOQ.'),
  ('CALC_RULES', 1, 'Materials markup: 6% (default, editable). Components 6%. Consumables 6%. Subcontracting 50%.'),
  ('CALC_RULES', 2, 'Loop transport, packaging and tooling are pass-through (no markup). Tooling is NRE amortized over the agreed quantity.'),
  ('CALC_RULES', 3, 'Operations, tooling, subcontracting and packaging are defined PER TIER: each tier carries its own machines, cycle times, setups, scrap, batches, transport and packaging.'),
  ('CALC_RULES', 4, 'Overheads ladder per tier (% of selling price): 12% with 1 operation, 16% with 2, 20% with 3, 24% with 4+, and 28% whenever subcontracting is involved. Editable per PN.'),
  ('CALC_RULES', 5, 'Contribution: 20% of selling price by default, editable per quote.'),
  ('CALC_RULES', 6, 'Commission: 5% of selling price, only when Nic Scherer is the Sales Rep. HQ: 5% of selling price.'),
  ('CALC_RULES', 7, 'PRICE BUILD-UP (gross-up): Selling price = Variable cost / (1 - Contribution - Commission - HQ - Overheads), all shares of the SELLING price.'),
  ('CALC_RULES', 8, 'FLOOR per tier: job minimum = $800 + $200 x (operations beyond the first); subcontracting counts as an operation. Per-piece floor = job floor / order quantity. Final price = MAX(calculated, floor).'),
  ('CALC_RULES', 9, 'Price Override accepts ANY value — below $1, below the floor, below the 20% contribution. Overrides raise flags; they never block. Approval challenges open flags.'),
  ('CALC_RULES', 10, 'Scrap options: 1, 2, 3, 4, 5, 10, 15, 20, 25, 50%. Above 5% is flagged (customers do not pay for lack of productivity).'),
  ('CALC_RULES', 11, 'Production batches: a per-tier Parts-per-production-batch value multiplies every setup — 8,000 parts with a 2,000 batch = 4 setups priced. Blank = 1 setup.'),
  ('CALC_RULES', 12, 'Wire diameter >= 0.59 in (15 mm) is NOT feasible at ISC: flag it, do not price it.'),
  ('CALC_RULES', 13, 'Labor rates: Coiler operator 40 USD/h, Secondary operator 27 USD/h (updated 2026-07-15). Machine $/h defaults to the C/CV target (cost rate x3 coiler / x5 secondary).'),
  ('CALC_RULES', 14, 'Wire forms: part weight = pi/4 x diameter^2 x developed length x density (lb/in3 by material code). The developed length is read from the drawing at parse or typed in the Material card; the weight stays editable.'),
  ('CALC_RULES', 15, 'Packaging: the card shows the shipped weight per box (qty/box x part lb) and of the whole tier (order qty x part lb). GAYLORD special packaging: 30.00 USD per unit.'),
  ('CALC_RULES', 16, 'Pull routing: with 2+ PNs, the Ops bar can pull the full 5-tier routing (+ production batches) from another PN. Quantities, tooling, subcontracting, packaging and overrides stay per PN.'),
  ('CALC_RULES', 17, 'MOQ mode per tier: MOQ to Produce & Ship (default, single shipment) or MOQ to Produce & Store — ISC produces the full quantity, stores it and releases it in shipments. STORE tiers print the shipment quantity on the offer as "Shipments of X pcs" &mdash; always equal to that tier&rsquo;s production batch (the two fields are synced); the offer also carries the remark that storage is considered for a maximum of 3 months. The selection prints on the offer against that price line.'),
  ('CALC_RULES', 18, 'Subcontracting cost basis: batch cost = MAX(MIN USD, $/lb x batch lb, $/pc x parts per batch) — any of the three may be entered; then +50% subcontracting markup.'),
  ('CALC_RULES', 19, 'The PDF button only VIEWS the filed offer (both roles). Filing happens ONCE, automatically, at approval. Admin is offered Re-create if the file is missing from the folder.'),
  ('CALC_RULES', 20, 'Quote outcome (PO RECEIVED / LOST / NO RECEPTION) is set in the Quote Log by John or Miguel alike, always editable; the journal records who changed it. Approving stays Miguel-only.'),
  ('CALC_RULES', 21, 'Quote Log layout: customers alphabetized A-Z, one collapsed row each (click to open). Quick filters with live counts: All / Pending approval (drafts) / Approved - a filter shows only matching customers, auto-expanded.'),
  ('CALC_RULES', 22, 'Deleting a quote: Miguel only, and only while it is a DRAFT - approved and superseded quotes are the record and can never be deleted. Deletions are journaled and guarded so a deleted draft cannot silently reappear from another open session.'),
  ('CALC_RULES', 23, 'Quote Log quick filters: All / Pending approval (drafts) / Approved / PO Received / Lost - live counts, one click.'),
  ('CALC_RULES', 24, 'Quote Log search: the search bar finds quotes live by PN (partial ok), quote number or customer name, combines with the status filters, and Esc clears it.'),
  ('CALC_RULES', 25, 'V6 filing: every customer folder under QUOTES now has two subfolders — "RFQ Info" (drawings, Excel tables, emails; parsed drawings are filed there automatically when the customer is set) and "Quotes sent" (offer PDFs filed at approval). Old PDFs in the customer root are still found by View PDF.'),
  ('CALC_RULES', 26, 'V6 defaults: lead time 45 working days, payment terms Net 30, on every new quote.'),
  ('CALC_RULES', 27, 'V6 suggestions (Ops bar): "Suggest routing" proposes the coiler by wire Ø lane + the standard secondary chain of the family, with ESTIMATED cycle times (historical medians) that MUST be validated; "Suggest packing" fills packing + pcs/box per tier by the target-box-weight rule (≈11–15 lb boxes, barrels ≈130 lb for heavy tiers).'),
  ('CALC_RULES', 28, 'V6 parsing: select SEVERAL PDFs at once — one PN is created per drawing, then the blue REVIEW bar walks PN by PN (Prev/Next/Done). PN, Description and Revision are mandatory: missing ones turn yellow after parsing. The AI model is selectable in Settings (claude-fable-5 available) with a token counter.'),
  ('CALC_RULES', 29, 'V6 folder: the App remembers the shared folder — it reconnects silently at start, or with ONE click (no browsing) if the browser asks for permission.'),
  ('CALC_RULES', 30, 'DELTA WON (V15): setting PO RECEIVED requires the previous price $/pc for every PN (or NEW PN if never sold). Delta = (new - previous) x selected-tier qty, accumulated in the cockpit by PO reception month, with detail per customer, family and PN. NEW PNs count in the NEW SALES report instead (price x qty). Won quotes from before V15 show in the cockpit with an Add button to complete the data.'),
  ('CALC_RULES', 31, 'Per-tier P&L (V15): the CBD has a Contribution % and an Overheads % input per tier - blank keeps the quote contribution and the automatic OH ladder / PN override. Drawing Revision is per PN (V15) - each PN keeps its own rev; the PDF filename lists every rev.'),
  ('CALC_RULES', 32, 'SALES COCKPIT (tab next to Brain, visible to John and Miguel, Sales Rep filter): Quoted = APPROVED offers, latest version only (superseded never double-counted); $ = the log Revenue (selected tier per PN); Won = PO Received; Waiting = No Reception; Lost = Lost. One-screen dashboard: KPI tiles with hit rate + the quoted-money strip; TOP CUSTOMERS by $ (won overlaid); $ BY FAMILY donut (revenue attributed per PN by its Description); $ BY REP donut; monthly quoted-vs-won $ by APPROVAL date; ACTIVITY chart of approved-quote counts with a Week/Month toggle; then the WAITING follow-up list (days waiting, >30 highlighted) and the collapsed Lost list. Live from the Quote Log - no extra data entry.');

INSERT INTO brain_glossary (term, definition) VALUES
  ('AV', 'Added Value = Selling price - purchased content (material, surcharge, components, consumables, subcontracting, transport, packaging, tooling).'),
  ('MS Variable', 'Variable Wages: labor of SECONDARY-family operations.'),
  ('MS Direct Fix', 'Direct fixed wages: labor of COILER-family operations.'),
  ('Machine Direct', 'Machine-rate portion of all operations (setup + run).'),
  ('C/CV', 'Contribution on Variable Costs = AV - MS Variable.'),
  ('C/CD', 'Contribution on Direct Costs = C/CV - Machine Direct - MS Direct Fix.'),
  ('C/CV per hour', 'C/CV of the tier / machine hours of the tier. Shown as 0,000.00 (RATIO); ratio = achieved / weighted machine C/CV target, whole number, 1 = 100%.');

INSERT INTO brain_stage (key, seq, title) VALUES
  ('stage1', 1, 'Stage 1 — Feasibility / Will'),
  ('stage2', 2, 'Stage 2 — Material & Volumes'),
  ('components', 3, 'Components'),
  ('consumables', 4, 'Consumables'),
  ('tiers', 5, 'Volume Tiers'),
  ('stage3', 6, 'Stages 3–5 — Operations per Tier'),
  ('tooling', 7, 'Tooling'),
  ('stage4', 8, 'Subcontracting'),
  ('stage5', 9, 'Packaging'),
  ('validation', 10, 'Feasibility'),
  ('costmodel', 11, 'CBD — Cost Model (all tiers)'),
  ('summary', 12, 'Summary View'),
  ('log', 13, 'Quote Log');

INSERT INTO brain_stage_body (stage_key, seq, body_text) VALUES
  ('stage1', 1, 'Decide whether ISC wants to quote. Review drawings and calculate the springs, with or without AI.'),
  ('stage1', 2, 'Capture: Quote Number (auto YEAR-CUSTOMER-SEQ), RFQ Date, Customer (add a new one inline with + new), PN Description (dropdown), Drawing Revision, Lead Time, Sales Rep, Payment Terms.'),
  ('stage1', 3, 'AI Read Drawing: uses the local Drawing Parser server when it is running (start it with the launcher .vbs), or the direct AI key from Settings. After parsing, the App offers to launch the Spring Calculator; its “Use weight in quote” button fills the part weight.'),
  ('stage1', 4, 'Auto-filled fields are highlighted blue until you edit them — check them, edit anything that looks wrong.'),
  ('stage1', 5, 'Every quote is stored in the Quote Log the instant it is created. Wire Ø >= 0.59 in (15 mm) is not feasible.'),
  ('stage2', 1, 'Unit per lb or per piece, material code, wire Ø (inches), weight (lb), Base + Surcharge + Transport (USD/lb), markup 6% default.'),
  ('stage2', 2, 'AI Suggest uses the internal price history (exact match, then log-linear interpolation). Surcharge auto-fills for SS / SS177 / 316.'),
  ('stage2', 3, 'MOQ protection: if the supplier MOQ exceeds needs, the quote carries the MOQ cost and flags the larger-quantity option.'),
  ('stage2', 4, 'Components: 2 lines. Consumables: 1 line. All marked up 6%. Scrap lives per operation in the routing.'),
  ('components', 1, 'Up to 2 lines, description + USD/part. Markup 6%.'),
  ('consumables', 1, 'One line, description + USD/part. Markup 6%.'),
  ('tiers', 1, 'Five order-quantity tiers. EACH TIER carries its own routing, tooling, subcontracting and packaging — select the tier tab in the Operations card.'),
  ('tiers', 2, 'Use “Copy this tier to…” to duplicate a tier’s operations, then adjust.'),
  ('tiers', 3, 'A tier can be price-overridden or eliminated in the CBD.'),
  ('stage3', 1, 'The tier tabs (T1–T5) switch which tier you are editing. Every parameter below belongs to the selected tier only.'),
  ('stage3', 2, 'Routing: up to 8 operations; selecting a machine auto-fills setup, pcs/hour, family, Machine $/h (C/CV target) and Labor $/h — all editable. Machines-per-Worker ratio: one worker on R machines charges Labor/R per machine hour.'),
  ('stage3', 3, 'Scrap options: 1, 2, 3, 4, 5, 10, 15, 20, 25, 50% — above 5% is flagged.'),
  ('stage3', 4, 'Parts per production batch (per tier): 8,000 parts with a 2,000 batch = 4 setups priced — every operation setup cost and its hours multiply by the setups. Blank = 1 setup.'),
  ('stage3', 5, 'Subcontracting: MAX(MIN, batch lb x USD/lb) +50% markup; loop transport by skids (2,400 lb max); “Share the skid?” splits the loop across sharing PNs. Packaging: box price / qty per box.'),
  ('tooling', 1, 'Tool cost / amortization quantity = $/pc, per tier. No markup.'),
  ('stage4', 1, 'Select supplier and service; MIN and USD/lb auto-fill from the database. Cost per batch = MAX(MIN, batch lb x rate), marked up 50%. Subcontracting forces the 28% overhead tier and counts as an operation for the floor.'),
  ('stage5', 1, 'Box type + quantity per box, per tier. Cost/pc = box price / qty per box. Pass-through.'),
  ('validation', 1, 'Flags collect everything the rules catch: floor binding, overrides below floor or contribution, scrap above 5%, MOQ, setup share, wire limit.'),
  ('validation', 2, 'The Spring Calculator feasibility (score, band, checklist) appears here after the drawing handoff.'),
  ('validation', 3, 'Remarks print on the customer offer — keep them customer-safe. EVERY offer automatically carries the fixed statement: ISC will produce against SMI Tolerances. Block tolerances will remain referential.'),
  ('validation', 4, 'After PO reception the Alternative Processing table shows which machines can run the spring (capability data, replace estimates with real specs).'),
  ('costmodel', 1, 'All five tiers side by side: $ per piece, $ per tier and % of sell for every P&L line.'),
  ('costmodel', 2, 'Pricing controls live here: Price Override (any value — below floor or contribution allowed, flagged), Select tier (star = the tier used in Summary and offer), Eliminate tier.'),
  ('costmodel', 3, 'P&L order: Sell → Material → Surcharge → Components/Consumables → Sub + Transport → Packaging → Tooling → AV → MS Variable → C/CV → Machine Direct → MS Direct Fix → C/CD → Overheads → HQ → Commission → Result.'),
  ('costmodel', 4, 'Final line: C/CV per hour as $0,000.00 (RATIO).'),
  ('summary', 1, 'Available when the quote has MORE THAN 2 PNs, or when a single PN carries MORE THAN 2 active tiers; otherwise the Summary button is greyed out.'),
  ('summary', 2, 'Opening it first asks how to build it: select PNs, select tiers per PN, or all PNs with all tiers (default). Rows = the PN-and-tier combinations you pick.'),
  ('summary', 3, 'The TOTALS row totals every column: volumes and all $/tier columns are summed, % columns are recomputed from the totals, per-piece columns are weighted averages, and C/CV per hour is total C/CV over total hours with its ratio.'),
  ('summary', 4, 'Columns: PN, Tier, Volume, Selling Price, Unit, Revenue, AV (pc/tier/%), MS Variable (pc/tier/%), C/CV (pc/tier/% + $/h ratio), C/CD (pc/tier/%).'),
  ('log', 1, 'Every quote is logged the moment it is created (draft or final, by any user).'),
  ('log', 2, 'Approving locks the quote and files the customer PDF into the customer folder inside QUOTES on the shared folder. Changes require a new version.'),
  ('log', 3, 'After PO reception the quote is view-only for M1 JOB setup, with the Alternative Processing table.');

-- 8.13 Descripciones de parte y su tipo de resorte
INSERT INTO part_description (description, spring_type, seq) VALUES
  ('Compression Spring', 'compression', 1),
  ('Torsion Spring', 'torsion', 2),
  ('Tension Spring', 'extension', 3),
  ('Wire Form', 'wireform', 4),
  ('Sub-Assembly', NULL, 5),
  ('Miscellaneous Part', NULL, 6);

-- 8.14 Motor de sugerencia de ruta: carriles de coiler por diametro (SG_LANES)
INSERT INTO routing_lane (seq, max_dia_in, machine_name, pph) VALUES
  (1, 0.02, 'TORIN (FENN) W10A', 5000),
  (2, 0.035, 'TORIN (FENN) FZ-11', 4900),
  (3, 0.062, 'TORIN (FENN) W11A', 1000),
  (4, 0.095, 'ZX250', 500),
  (5, 0.115, 'TORIN (FENN) W115A', 250),
  (6, 0.148, 'TORIN (FENN) W125', 500),
  (7, 0.2, 'NUCOIL HX-60', 325),
  (8, 0.59, 'AIM 3000', 300);
-- Wire Form no usa carril: la app fuerza SIMPLEX MC 50 @ 1000 pph.

-- Cadena secundaria sugerida por familia (SG_SECONDARY)
INSERT INTO routing_secondary (part_description, seq, machine_name, pph) VALUES
  ('Compression Spring', 1, 'Grinder A', 500),
  ('Compression Spring', 2, 'Stationary Oven', 350),
  ('Tension Spring', 1, 'Looping / Hooks', 125),
  ('Tension Spring', 2, 'Stationary Oven', 350),
  ('Torsion Spring', 1, 'Bending / Kick', 125),
  ('Torsion Spring', 2, 'Stationary Oven', 350),
  ('Wire Form', 1, 'Bending / Kick', 125),
  ('Wire Form', 2, 'Stationary Oven', 350);

-- 8.15 Motor de sugerencia de empaque (regla por peso enviado del tier)
INSERT INTO packing_rule (seq, min_tier_lb, part_description, packing_code, target_box_lb, note) VALUES
  (1, 400, NULL, 'barrels no lids', 130, 'Tier pesado: tambores, ~130 lb por tambor (mediana historica).'),
  (2, 30, 'Wire Form', 'CHP12012', 15, 'Wire forms de peso medio.'),
  (3, 200, NULL, 'COR121212U', 17, 'Caja 12x12x12, ~17 lb.'),
  (4, 60, NULL, 'COR100803', 13, 'Caja 10x8x3, ~13 lb.'),
  (5, 0, NULL, 'COR11050', 11, 'Regla por defecto, ~11 lb por caja.');
-- Piezas por caja = redondeo de target_box_lb / peso de la pieza al valor 'redondo' mas cercano
-- de la serie 1,2,5,10,25,50,100,200,250,500,1000,2000,2500,5000,10000,25000,50000 (tope: la cantidad del tier).

-- 8.16 Spring Engineering Calculator: materiales (Sut = A / d^m, d en mm -> MPa)
INSERT INTO spring_material (id, name, astm, g_mpa, e_mpa, density_kg_m3, a_coef, m_exp, d_min_mm, d_max_mm,
  temp_max_c, shear_fac, bend_fac, cost_fac, fatigue, note, isc_material_code) VALUES
  ('music', 'Music Wire', 'ASTM A228', 81000, 203400, 7860, 2211, 0.145, 0.1, 6.5, 120, 0.45, 0.78, 1, 'Excellent', 'Highest-quality high-carbon wire. Best fatigue life of the carbon steels; preferred for dynamic / high-cycle service.', 'MW'),
  ('crsi', 'Chrome Silicon', 'ASTM A401', 77200, 203400, 7860, 1974, 0.108, 0.8, 12, 245, 0.5, 0.87, 2.5, 'Excellent', 'Alloy steel for shock, impact and elevated-temperature duty. High allowable stress; common for engine / valve springs.', 'CSI'),
  ('ss302', 'Stainless 302/304', 'ASTM A313', 69000, 193000, 7920, 1867, 0.146, 0.1, 10, 290, 0.35, 0.61, 4, 'Moderate', 'Austenitic stainless. Good general corrosion resistance; lower allowable stress and modulus than carbon steel.', 'SS'),
  ('ss177', '17-7 PH Stainless', 'ASTM A313 (631)', 75800, 203400, 7800, 2065, 0.127, 0.2, 6, 340, 0.45, 0.75, 6, 'Good', 'Precipitation-hardening stainless. Heat-treated after forming for high strength + corrosion + moderate elevated-temperature service.', 'SS177'),
  ('otemp', 'Oil Tempered', 'ASTM A229', 77200, 196500, 7860, 1855, 0.187, 0.5, 16, 150, 0.5, 0.87, 0.7, 'Moderate', 'General-purpose pre-tempered carbon steel. Economical for static and moderate-cycle loads; not for high-cycle fatigue or shock.', 'OT'),
  ('harddr', 'Hard Drawn', 'ASTM A227', 78600, 196500, 7860, 1783, 0.19, 0.7, 12, 120, 0.45, 0.75, 0.5, 'Low', 'Lowest-cost spring wire. Suited to static / low-cycle, non-critical applications. Avoid fatigue, shock and tight tolerances.', 'HD'),
  ('inconel', 'Inconel X-750', 'AMS 5698/5699', 79000, 214000, 8250, 1400, 0.1, 0.4, 8, 370, 0.35, 0.61, 15, 'Good', 'Nickel-chromium superalloy for high-temperature and corrosive environments. Expensive; specify only when service conditions require it.', NULL),
  ('phosb', 'Phosphor Bronze', 'ASTM B159', 41400, 103000, 8860, 1000, 0.028, 0.1, 7.5, 95, 0.35, 0.61, 5, 'Low', 'Copper alloy with good electrical conductivity and corrosion resistance. Low modulus and modest strength; used for contacts / electrical springs.', 'PHOSB');

-- Base de factibilidad de maquina del Spring Calculator (datos ESTIMADOS)
INSERT INTO spring_machine (id, name, wire_min_mm, wire_max_mm, od_max_mm, cap_compression, cap_extension,
  cap_torsion, axes, setup_class, uses, risk, machine_id) VALUES
  ('aim3000', 'AIM 3000', 0.8, 6, 80, TRUE, TRUE, TRUE, 'CNC multi-axis former', 'High', 'High-capability CNC former. Complex geometries, all three spring types, medium-to-large wire.', 'Highest setup time and tooling cost; reserve for complex or higher-value parts.', (SELECT id FROM machine WHERE name = 'AIM 3000')),
  ('tf23', 'Shinko TF23', 0.2, 2.3, 30, TRUE, TRUE, TRUE, 'CNC 10-12 axis former', 'High', 'Fine-wire precision CNC former. Small intricate springs, tight tolerances, all types.', 'Not suitable for larger wire; setup-intensive for simple parts.', (SELECT id FROM machine WHERE name = 'SHINKO TF-23')),
  ('tf45', 'Shinko TF45', 0.5, 4.5, 55, TRUE, TRUE, TRUE, 'CNC multi-axis former', 'High', 'Mid-range precision CNC former. Versatile for all types in the medium wire band.', 'Setup-intensive; over-capable (uneconomic) for simple high-volume parts.', (SELECT id FROM machine WHERE name = 'SHINKO TF-45')),
  ('hx60', 'Nucoil HX-60', 1, 6, 90, TRUE, TRUE, FALSE, '2-axis coiler', 'Medium', 'Heavy-duty coiler for larger compression and extension springs.', 'No torsion capability; limited for complex end forming.', (SELECT id FROM machine WHERE name = 'NUCOIL HX-60')),
  ('csf200', 'Nucoil CSF200', 0.15, 2, 25, TRUE, TRUE, FALSE, 'CNC coiler', 'Medium', 'Fine-wire compression / extension coiler. Efficient for small high-volume parts.', 'No torsion capability; restricted OD and wire range.', (SELECT id FROM machine WHERE name = 'NUCOIL CSF-200')),
  ('zx250', 'ZX250', 0.3, 2.5, 32, TRUE, TRUE, TRUE, 'CNC multi-axis former', 'Medium', 'Compact CNC former. Good all-round machine for small / medium parts of all types.', 'Limited to small wire and OD; verify torsion tooling availability.', (SELECT id FROM machine WHERE name = 'ZX250'));

-- Condiciones de extremo (resortes de compresion)
INSERT INTO spring_end_type (id, label, end_coils, is_ground) VALUES
  ('plain', 'Plain', 0, FALSE),
  ('plain_ground', 'Plain & Ground', 1, TRUE),
  ('closed', 'Squared (Closed)', 2, FALSE),
  ('closed_ground', 'Squared & Ground', 2, TRUE);

-- Tipos de gancho (resortes de extension): vueltas equivalentes agregadas
INSERT INTO spring_hook_type (id, label, turns_factor) VALUES
  ('machine_full', 'Machine loop - full', 1),
  ('machine_half', 'Machine loop - half', 0.55),
  ('crossover', 'Crossover center loop', 1.15),
  ('side', 'Side loop', 1.05),
  ('extended', 'Extended hook', 1.7),
  ('special', 'Special / custom hook', 1.2);

-- Bandas de manufacturabilidad (score 0-100)
INSERT INTO spring_score_band (min_score, band, color_hex, description) VALUES
  (90, 'Easy to manufacture', '#1f8a4c', 'Design sits well inside normal shop limits.'),
  (70, 'Manufacturable', '#3f9e57', 'Producible with normal process controls.'),
  (50, 'Engineering review', '#b9770e', 'Requires engineering review before quoting / release.'),
  (30, 'High manufacturing risk', '#d35400', 'Significant risk - expect yield loss and added cost.'),
  (0, 'Not recommended', '#c0392b', 'Design is at or beyond practical limits - redesign advised.');

-- Conversiones de unidades del Spring Calculator (valor SI * factor = valor mostrado)
INSERT INTO unit_conversion (kind, unit_system, factor, label) VALUES
  ('len', 'in', 0.03937007874015748, 'in'),
  ('len', 'mm', 1, 'mm'),
  ('force', 'in', 0.2248089438709618, 'lbf'),
  ('force', 'mm', 1, 'N'),
  ('stress', 'in', 0.14503774, 'ksi'),
  ('stress', 'mm', 1, 'MPa'),
  ('rate', 'in', 5.7101471, 'lbf/in'),
  ('rate', 'mm', 1, 'N/mm'),
  ('moment', 'in', 0.0088507458, 'lbf·in'),
  ('moment', 'mm', 1, 'N·mm'),
  ('freq', 'in', 1, 'Hz'),
  ('freq', 'mm', 1, 'Hz');

-- 8.17 Bitacora inicial
INSERT INTO journal (who, area, detail) VALUES
  ('SYSTEM','INIT','Base PostgreSQL inicializada desde ISC Price Calculator V7 (BRAIN 18.0.1-DEMO) y Spring Engineering Calculator.');

COMMIT;

-- =====================================================================================
-- FIN
-- =====================================================================================


-- =====================================================================================
-- 9. APENDICE A -- DE DONDE SALE CADA TABLA
-- =====================================================================================
--  TABLA                        ORIGEN EN LOS ARCHIVOS HTML
--  ---------------------------  --------------------------------------------------------
--  app_user                     SEED.users
--  pricing_param                DEFAULT_PARAMS + SEED.machineParams
--  scrap_option                 BRAIN.calcRules (1,2,3,4,5,10,15,20,25,50)
--  labor_rate                   BRAIN.calcRules + migracion labor4027 (40 / 27 USD/h)
--  customer                     SEED.customers (412)
--  material_legend              SEED.materialLegend + ENGINE.WIRE_DENS
--  material_reference           SEED.matReference
--  material_price               SEED.materialPrices (186)
--  surcharge                    SEED.surcharges + SEED.surchargeAppliesTo
--  machine                      SEED.machines (30)
--  subcontractor(_service)      SEED.subcontractors
--  plating_history              SEED.platingHistory (116)
--  packing                      SEED.packing (16, incluye GAYLORD a 30 USD)
--  brain_meta / rule / glossary / stage / stage_body   BRAIN (v18.0.1-DEMO)
--  part_description             DESC_OPTIONS + DESC2TYPE
--  routing_lane                 SG_LANES
--  routing_secondary            SG_SECONDARY
--  packing_rule                 funcion suggestPackingFor()
--  spring_material              Spring Calculator MAT_DEFAULTS
--  spring_machine               Spring Calculator MCH_DEFAULTS
--  spring_end_type              Spring Calculator END_TYPES
--  spring_hook_type             factores de gancho de calcExtension()
--  spring_score_band            funcion bandFromScore()
--  unit_conversion              Spring Calculator CONV + ULBL
--  quote / quote_part / quote_tier / tier_operation    blankQuote(), blankPn(), blankTier(), blankOps()
--  tier_result                  salida de ENGINE.computePN()
--  quote_flag                   banderas de ENGINE.computePN()
--  spring_feasibility(_flag)    mensaje postMessage type=springFeasibility
--  quote_part_drawing(_field)   salida del Drawing Parser / fullParseAI()
--  delta_won(_item)             deltaWonModal() (V15)
--  journal / quote_lock         shared.journal / shared.locks
--
-- =====================================================================================
-- 10. APENDICE B -- FORMULAS QUE LA APLICACION APLICA SOBRE ESTOS DATOS
--     (se documentan aqui; el calculo vive en la aplicacion, no en la base)
-- =====================================================================================
--  Rendimiento por scrap (acumulado hacia atras):
--     Y[k] = Y[k+1] * (1 - scrap[k]/100)      Y[n] = 1      cantidad de arranque = qty / Y[0]
--  Material por pieza:
--     lb necesarias = peso_pieza * cantidad_arranque
--     lb compradas  = MAX(lb necesarias, MOQ)          -- si el MOQ obliga, se marca bandera
--     material/pc   = lb compradas * (base + surcharge + transporte) / qty * (1 + markup/100)
--  Setups por tier:
--     setups = CEIL(qty / lote_de_produccion), minimo 1   (lote vacio = 1 setup)
--  Costo de operacion por pieza (por cada operacion k):
--     corrida maquina = machine_usd_h / pph / Y[k]
--     corrida MO      = (labor_usd_h / workers_ratio) / pph / Y[k]
--     setup maquina   = setup_h * machine_usd_h * setups / qty
--     setup MO        = setup_h * labor_usd_h    * setups / qty
--     la MO de familia SECONDARY va a MS Variable; la de COILER va a MS Direct Fix
--  Subcontratacion:
--     costo lote = MAX(min_usd, per_lb * lb del lote, per_pc * piezas del lote)
--     sub/pc     = costo lote / piezas del lote * (1 + 50/100)
--     transporte = loop_trip * CEIL(lb del lote / skid_max_lb) / piezas del lote
--                  (dividido entre los PN que comparten skid si sub_share_skid)
--  Empaque y herramental (sin markup, pass-through):
--     empaque/pc = precio de la caja / piezas por caja
--     herramental/pc = costo del herramental / cantidad de amortizacion
--  Overheads del tier:
--     override del PN, si existe; si hay subcontratacion = oh_sub_pct;
--     si no, oh_ladder_pct segun el numero de operaciones (la subcontratacion cuenta como una)
--  Gross-up (precio de venta por pieza):
--     divisor = 1 - contribucion - comision - HQ - overheads      (todos sobre el precio de venta)
--     precio  = costo variable / divisor                          (divisor <= 0.05 = error)
--  Piso ISC:
--     piso del trabajo = 800 + 200 * (numero de operaciones - 1)
--     piso por pieza   = piso del trabajo / qty
--     precio final     = MAX(precio calculado, piso por pieza)     -- el override lo puede violar, con bandera
--  P&L:
--     compras = material + componentes + consumibles + subcontratacion + transporte + empaque + herramental
--     AV   = precio - compras
--     C/CV = AV - MS Variable
--     C/CD = C/CV - costo directo de maquina - MS Direct Fix
--     Resultado = C/CD - overheads - HQ - comision
--     C/CV por hora = (C/CV * qty) / horas del tier;  ratio = C/CV por hora / objetivo ponderado
--  Peso de wire form:
--     peso (lb) = pi/4 * diametro^2 * longitud_desarrollada * densidad (material_legend.density_lb_in3)
--  Spring Calculator:
--     Sut(d) = a_coef / d^m_exp  (d en mm, acotado 0.05-30)
--     k (compresion) = G * d^4 / (8 * D^3 * Na)
--     factor de Wahl   Kw = (4C-1)/(4C-4) + 0.615/C ,  C = D/d
--     factor de Bergstrasser Kb = (4C+2)/(4C-3)
--     esfuerzo admisible = shear_fac * Sut (torsion) o bend_fac * Sut (flexion)
--
-- =====================================================================================
-- 11. APENDICE C -- EJEMPLO DE CAPTURA DE UNA COTIZACION (descomentar para probar)
-- =====================================================================================
-- SET search_path = isc, public;
-- BEGIN;
-- INSERT INTO quote (id, number, version, status, customer_code, rfq_date, sales_rep,
--                    payment_terms, lead_days, will, contribution_pct, created_by)
-- VALUES ('q_demo_001','2026-ABB MOTORS-001',1,'DRAFT','ABB MOTORS', DATE '2026-09-01','John Tvrdy',
--         'Net 30',45,'YES',20,'quoting@cgr-international.com');
--
-- INSERT INTO quote_part (quote_id, pn_index, pn, description, revision, unit, selected_tier,
--                         material_code, dia_in, weight_lb, base_per_lb, surcharge_per_lb,
--                         transport_per_lb, mat_markup_pct, moq_lb)
-- VALUES ('q_demo_001',1,'12345-A','Compression Spring','C','pc',2,
--         'SS',0.062,0.0085,5.60,1.30,0.10,6,NULL)
-- RETURNING id;
--
-- INSERT INTO quote_tier (quote_part_id, tier_no, qty, prod_batch, moq_mode, packing_id, packing_qty_per_box)
-- SELECT p.id, v.tier_no, v.qty, v.batch, 'SHIP',
--        (SELECT id FROM packing WHERE code='COR11050' LIMIT 1), 1000
-- FROM quote_part p, (VALUES (1,1000::numeric,NULL::numeric),(2,5000,2500),(3,10000,2500)) AS v(tier_no,qty,batch)
-- WHERE p.quote_id='q_demo_001' AND p.pn_index=1;
--
-- INSERT INTO tier_operation (quote_tier_id, op_no, machine_name, family, setup_h, pph,
--                             machine_usd_h, labor_usd_h, workers_ratio, scrap_pct, target_usd_h)
-- SELECT t.id, o.op_no, m.name, m.family, m.setup_h, o.pph, m.ccv_target_usd_h,
--        (SELECT usd_per_h FROM labor_rate WHERE family=m.family), 1.0, 5, m.ccv_target_usd_h
-- FROM quote_tier t
-- JOIN quote_part p ON p.id=t.quote_part_id AND p.quote_id='q_demo_001'
-- JOIN (VALUES (1,'TORIN (FENN) W11A',1000::numeric),(2,'Grinder A',500),(3,'Stationary Oven',350)) AS o(op_no,mname,pph) ON TRUE
-- JOIN machine m ON m.name=o.mname;
-- COMMIT;
-- SELECT number, pn, tier_no, qty, count(op.*) AS ops
-- FROM v_quote_log l JOIN quote_part p ON p.quote_id=l.id
-- JOIN quote_tier t ON t.quote_part_id=p.id
-- LEFT JOIN tier_operation op ON op.quote_tier_id=t.id
-- GROUP BY 1,2,3,4 ORDER BY tier_no;
