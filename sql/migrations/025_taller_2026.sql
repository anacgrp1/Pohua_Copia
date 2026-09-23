-- 025_taller_2026.sql
--
-- GENERADO por scripts/generar_taller.py desde
-- pricing/nucleo/taller_2026.json. No editar a mano: se regenera.
--
-- Fuente de los números: ISC Machine Selection Rules DATA REQUEST - FILLED.xlsx
--
-- Qué cambia y por qué importa
-- -----------------------------
-- Los valores que había salían de derivarlos del precio de compra de la
-- máquina. Los de aquí los contestó el taller. No se parecen:
--
--     TORIN W11A     antes 11.16 $/h, 600 pzs/h   ahora 15.00 $/h, 1500 pzs/h
--     Grinder A      antes 11.16 $/h, sin pzs/h   ahora 15.00 $/h,  500 pzs/h
--     Stationary Oven antes 8.93 $/h, sin pzs/h   ahora 10.00 $/h,  400 pzs/h
--
-- Y los rangos de alambre cambian de quién puede hacer qué: la W11A
-- figuraba sin rango capturado, y toma de 0.381 a 1.829 mm.
--
-- Es la MISMA tabla que usa la calculadora de la planta. Que las dos den
-- el mismo precio para la misma pieza depende de eso.
--
-- El objetivo de CCV/hora sale de `machineParams` del catálogo:
-- bobinadoras x3, secundarias x5.

-- Las máquinas se localizan por el nombre normalizado —sin (FENN) y sin
-- puntuación— porque el taller escribe «TORIN W11A» y el catálogo
-- «TORIN (FENN) W11A». Son la misma máquina.
CREATE OR REPLACE FUNCTION isc_norm_maquina(t text) RETURNS text AS $$
    SELECT regexp_replace(replace(upper(coalesce(t, '')), '(FENN)', ''),
                          '[^A-Z0-9]', '', 'g');
$$ LANGUAGE sql IMMUTABLE;

-- SIMPLEX MC 50 (COILER)
UPDATE maquinas SET
    horas_setup = 5,
    pph_default = 950,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 1
  WHERE isc_norm_maquina(nombre) = 'SIMPLEXMC50';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'SIMPLEXMC50')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'SIMPLEXMC50');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 60, 180, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'SIMPLEXMC50';
UPDATE maquina_capacidades SET
    alambre_min_mm = 1.016,
    alambre_max_mm = 5.029,
    od_max_mm = 76.2,
    hace_compresion = true,
    hace_extension = false,
    hace_torsion = false,
    hace_wireform = false
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'SIMPLEXMC50');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 1.016, 5.029, 76.2, true, false, false, false FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'SIMPLEXMC50'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- TORIN W10A (COILER)
UPDATE maquinas SET
    horas_setup = 3,
    pph_default = 5000,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 4
  WHERE isc_norm_maquina(nombre) = 'TORINW10A';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW10A')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW10A');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 15, 45, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'TORINW10A';
UPDATE maquina_capacidades SET
    alambre_min_mm = 0.203,
    alambre_max_mm = 0.711,
    od_max_mm = 22.22,
    hace_compresion = true,
    hace_extension = false,
    hace_torsion = false,
    hace_wireform = false
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW10A');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 0.203, 0.711, 22.22, true, false, false, false FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'TORINW10A'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- TORIN W11A (COILER)
UPDATE maquinas SET
    horas_setup = 3,
    pph_default = 1500,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 2
  WHERE isc_norm_maquina(nombre) = 'TORINW11A';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW11A')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW11A');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 15, 45, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'TORINW11A';
UPDATE maquina_capacidades SET
    alambre_min_mm = 0.381,
    alambre_max_mm = 1.829,
    od_max_mm = 39.67,
    hace_compresion = true,
    hace_extension = true,
    hace_torsion = false,
    hace_wireform = false
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW11A');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 0.381, 1.829, 39.67, true, true, false, false FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'TORINW11A'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- TORIN W11T (COILER)
UPDATE maquinas SET
    horas_setup = 3,
    pph_default = 500,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 11
  WHERE isc_norm_maquina(nombre) = 'TORINW11T';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW11T')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW11T');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 15, 45, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'TORINW11T';
UPDATE maquina_capacidades SET
    alambre_min_mm = 0.381,
    alambre_max_mm = 1.854,
    od_max_mm = 39.7,
    hace_compresion = true,
    hace_extension = false,
    hace_torsion = true,
    hace_wireform = false
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW11T');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 0.381, 1.854, 39.7, true, false, true, false FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'TORINW11T'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- TORIN W115A (COILER)
UPDATE maquinas SET
    horas_setup = 3,
    pph_default = 400,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 7
  WHERE isc_norm_maquina(nombre) = 'TORINW115A';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW115A')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW115A');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 15, 45, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'TORINW115A';
UPDATE maquina_capacidades SET
    alambre_min_mm = 0.813,
    alambre_max_mm = 2.845,
    od_max_mm = 53.97,
    hace_compresion = true,
    hace_extension = true,
    hace_torsion = false,
    hace_wireform = false
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW115A');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 0.813, 2.845, 53.97, true, true, false, false FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'TORINW115A'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- TORIN W125 (COILER)
UPDATE maquinas SET
    horas_setup = 3,
    pph_default = 300,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 6
  WHERE isc_norm_maquina(nombre) = 'TORINW125';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW125')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW125');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 15, 45, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'TORINW125';
UPDATE maquina_capacidades SET
    alambre_min_mm = 2.032,
    alambre_max_mm = 5.258,
    od_max_mm = 95.25,
    hace_compresion = true,
    hace_extension = true,
    hace_torsion = true,
    hace_wireform = false
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW125');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 2.032, 5.258, 95.25, true, true, true, false FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'TORINW125'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- TORIN W12T (COILER)
UPDATE maquinas SET
    horas_setup = 3,
    pph_default = 350,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 14
  WHERE isc_norm_maquina(nombre) = 'TORINW12T';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW12T')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW12T');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 15, 45, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'TORINW12T';
UPDATE maquina_capacidades SET
    alambre_min_mm = 1.194,
    alambre_max_mm = 3.759,
    od_max_mm = 69.85,
    hace_compresion = true,
    hace_extension = false,
    hace_torsion = true,
    hace_wireform = false
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINW12T');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 1.194, 3.759, 69.85, true, false, true, false FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'TORINW12T'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- TORIN FZ-11 (COILER)
UPDATE maquinas SET
    horas_setup = 3,
    pph_default = 4900,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 8
  WHERE isc_norm_maquina(nombre) = 'TORINFZ11';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINFZ11')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINFZ11');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 20, 60, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'TORINFZ11';
UPDATE maquina_capacidades SET
    alambre_min_mm = 0.508,
    alambre_max_mm = 2.159,
    od_max_mm = NULL,
    hace_compresion = true,
    hace_extension = true,
    hace_torsion = true,
    hace_wireform = false
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'TORINFZ11');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 0.508, 2.159, NULL, true, true, true, false FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'TORINFZ11'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- KMH-508 (COILER)
UPDATE maquinas SET
    horas_setup = 5,
    pph_default = 5000,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 16
  WHERE isc_norm_maquina(nombre) = 'KMH508';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'KMH508')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'KMH508');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 20, 60, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'KMH508';
UPDATE maquina_capacidades SET
    alambre_min_mm = 0.305,
    alambre_max_mm = 0.787,
    od_max_mm = NULL,
    hace_compresion = true,
    hace_extension = false,
    hace_torsion = false,
    hace_wireform = false
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'KMH508');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 0.305, 0.787, NULL, true, false, false, false FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'KMH508'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- KMH-516 (COILER)
UPDATE maquinas SET
    horas_setup = 5,
    pph_default = 7500,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 18
  WHERE isc_norm_maquina(nombre) = 'KMH516';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'KMH516')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'KMH516');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 20, 60, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'KMH516';
UPDATE maquina_capacidades SET
    alambre_min_mm = 0.787,
    alambre_max_mm = 1.6,
    od_max_mm = NULL,
    hace_compresion = true,
    hace_extension = false,
    hace_torsion = false,
    hace_wireform = false
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'KMH516');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 0.787, 1.6, NULL, true, false, false, false FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'KMH516'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- SHINKO TF-23 (COILER)
UPDATE maquinas SET
    horas_setup = 10,
    pph_default = 327,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 17
  WHERE isc_norm_maquina(nombre) = 'SHINKOTF23';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'SHINKOTF23')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'SHINKOTF23');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 40, 120, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'SHINKOTF23';
UPDATE maquina_capacidades SET
    alambre_min_mm = 0.203,
    alambre_max_mm = 2.311,
    od_max_mm = NULL,
    hace_compresion = true,
    hace_extension = true,
    hace_torsion = true,
    hace_wireform = false
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'SHINKOTF23');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 0.203, 2.311, NULL, true, true, true, false FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'SHINKOTF23'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- SHINKO TF-45 (COILER)
UPDATE maquinas SET
    horas_setup = 10,
    pph_default = 450,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 9
  WHERE isc_norm_maquina(nombre) = 'SHINKOTF45';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'SHINKOTF45')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'SHINKOTF45');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 50, 150, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'SHINKOTF45';
UPDATE maquina_capacidades SET
    alambre_min_mm = 2.007,
    alambre_max_mm = 4.496,
    od_max_mm = NULL,
    hace_compresion = true,
    hace_extension = true,
    hace_torsion = true,
    hace_wireform = false
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'SHINKOTF45');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 2.007, 4.496, NULL, true, true, true, false FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'SHINKOTF45'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- ZX250 (COILER)
UPDATE maquinas SET
    horas_setup = 6,
    pph_default = 500,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 5
  WHERE isc_norm_maquina(nombre) = 'ZX250';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'ZX250')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'ZX250');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 25, 75, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'ZX250';
UPDATE maquina_capacidades SET
    alambre_min_mm = 0.508,
    alambre_max_mm = 2.489,
    od_max_mm = NULL,
    hace_compresion = true,
    hace_extension = false,
    hace_torsion = true,
    hace_wireform = true
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'ZX250');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 0.508, 2.489, NULL, true, false, true, true FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'ZX250'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- AIM 3000 (COILER)
UPDATE maquinas SET
    horas_setup = 6,
    pph_default = 250,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 3
  WHERE isc_norm_maquina(nombre) = 'AIM3000';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'AIM3000')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'AIM3000');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 80, 240, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'AIM3000';
UPDATE maquina_capacidades SET
    alambre_min_mm = 3.607,
    alambre_max_mm = 9.525,
    od_max_mm = NULL,
    hace_compresion = true,
    hace_extension = true,
    hace_torsion = true,
    hace_wireform = true
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'AIM3000');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 3.607, 9.525, NULL, true, true, true, true FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'AIM3000'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- AIM AFM-3D2-T (COILER)
UPDATE maquinas SET
    horas_setup = 2,
    pph_default = 500,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 15
  WHERE isc_norm_maquina(nombre) = 'AIMAFM3D2T';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'AIMAFM3D2T')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'AIMAFM3D2T');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 25, 75, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'AIMAFM3D2T';
UPDATE maquina_capacidades SET
    alambre_min_mm = 3.175,
    alambre_max_mm = 11.1,
    od_max_mm = NULL,
    hace_compresion = false,
    hace_extension = false,
    hace_torsion = false,
    hace_wireform = true
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'AIMAFM3D2T');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 3.175, 11.1, NULL, false, false, false, true FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'AIMAFM3D2T'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- NUCOIL CSF-200 (COILER)
UPDATE maquinas SET
    horas_setup = 6,
    pph_default = 400,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 12
  WHERE isc_norm_maquina(nombre) = 'NUCOILCSF200';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'NUCOILCSF200')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'NUCOILCSF200');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 20, 60, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'NUCOILCSF200';
UPDATE maquina_capacidades SET
    alambre_min_mm = 0.457,
    alambre_max_mm = 2.032,
    od_max_mm = NULL,
    hace_compresion = false,
    hace_extension = true,
    hace_torsion = true,
    hace_wireform = true
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'NUCOILCSF200');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 0.457, 2.032, NULL, false, true, true, true FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'NUCOILCSF200'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- NUCOIL CSF-400 (COILER)
UPDATE maquinas SET
    horas_setup = 6,
    pph_default = 650,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 13
  WHERE isc_norm_maquina(nombre) = 'NUCOILCSF400';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'NUCOILCSF400')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'NUCOILCSF400');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 30, 90, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'NUCOILCSF400';
UPDATE maquina_capacidades SET
    alambre_min_mm = 1.829,
    alambre_max_mm = 4.064,
    od_max_mm = NULL,
    hace_compresion = false,
    hace_extension = true,
    hace_torsion = true,
    hace_wireform = true
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'NUCOILCSF400');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 1.829, 4.064, NULL, false, true, true, true FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'NUCOILCSF400'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- NUCOIL HX-60 (COILER)
UPDATE maquinas SET
    horas_setup = 10,
    pph_default = 334,
    horas_labor = 40,
    scrap_pct = 5,
    orden_uso = 10
  WHERE isc_norm_maquina(nombre) = 'NUCOILHX60';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'NUCOILHX60')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'NUCOILHX60');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 40, 120, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'NUCOILHX60';
UPDATE maquina_capacidades SET
    alambre_min_mm = 2.997,
    alambre_max_mm = 5.969,
    od_max_mm = NULL,
    hace_compresion = false,
    hace_extension = true,
    hace_torsion = true,
    hace_wireform = true
  WHERE maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'NUCOILHX60');
INSERT INTO maquina_capacidades
       (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
        hace_compresion, hace_extension, hace_torsion, hace_wireform)
  SELECT m.id, 2.997, 5.969, NULL, false, true, true, true FROM maquinas m
   WHERE isc_norm_maquina(m.nombre) = 'NUCOILHX60'
     AND NOT EXISTS (SELECT 1 FROM maquina_capacidades c
                      WHERE c.maquina_id = m.id);

-- Grinder A (SECONDARY)
UPDATE maquinas SET
    horas_setup = 1,
    pph_default = 500,
    horas_labor = 27,
    scrap_pct = 5,
    orden_uso = NULL
  WHERE isc_norm_maquina(nombre) = 'GRINDERA';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'GRINDERA')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'GRINDERA');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 15, 75, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'GRINDERA';

-- Grinder B (SECONDARY)
UPDATE maquinas SET
    horas_setup = 1,
    pph_default = 500,
    horas_labor = 27,
    scrap_pct = 5,
    orden_uso = NULL
  WHERE isc_norm_maquina(nombre) = 'GRINDERB';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'GRINDERB')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'GRINDERB');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 15, 75, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'GRINDERB';

-- Grinder C (SECONDARY)
UPDATE maquinas SET
    horas_setup = 1,
    pph_default = NULL,
    horas_labor = 27,
    scrap_pct = 5,
    orden_uso = NULL
  WHERE isc_norm_maquina(nombre) = 'GRINDERC';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'GRINDERC')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'GRINDERC');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 15, 75, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'GRINDERC';

-- Grinder D (SECONDARY)
UPDATE maquinas SET
    horas_setup = 1,
    pph_default = NULL,
    horas_labor = 27,
    scrap_pct = 5,
    orden_uso = NULL
  WHERE isc_norm_maquina(nombre) = 'GRINDERD';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'GRINDERD')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'GRINDERD');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 15, 75, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'GRINDERD';

-- Grinder PED (SECONDARY)
UPDATE maquinas SET
    horas_setup = 1,
    pph_default = 50,
    horas_labor = 27,
    scrap_pct = 5,
    orden_uso = NULL
  WHERE isc_norm_maquina(nombre) = 'GRINDERPED';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'GRINDERPED')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'GRINDERPED');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 8, 40, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'GRINDERPED';

-- Stationary Oven (SECONDARY)
UPDATE maquinas SET
    horas_setup = 3,
    pph_default = 400,
    horas_labor = 27,
    scrap_pct = 5,
    orden_uso = NULL
  WHERE isc_norm_maquina(nombre) = 'STATIONARYOVEN';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'STATIONARYOVEN')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'STATIONARYOVEN');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 10, 50, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'STATIONARYOVEN';

-- Looping / Hooks (SECONDARY)
UPDATE maquinas SET
    horas_setup = 1,
    pph_default = 125,
    horas_labor = 27,
    scrap_pct = 5,
    orden_uso = NULL
  WHERE isc_norm_maquina(nombre) = 'LOOPINGHOOKS';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'LOOPINGHOOKS')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'LOOPINGHOOKS');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 0, 0, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'LOOPINGHOOKS';

-- Bending / Kick (SECONDARY)
UPDATE maquinas SET
    horas_setup = 1,
    pph_default = 125,
    horas_labor = 27,
    scrap_pct = 5,
    orden_uso = NULL
  WHERE isc_norm_maquina(nombre) = 'BENDINGKICK';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'BENDINGKICK')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'BENDINGKICK');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 0, 0, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'BENDINGKICK';

-- Assembly (SECONDARY)
UPDATE maquinas SET
    horas_setup = 1,
    pph_default = 300,
    horas_labor = 27,
    scrap_pct = 5,
    orden_uso = NULL
  WHERE isc_norm_maquina(nombre) = 'ASSEMBLY';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'ASSEMBLY')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'ASSEMBLY');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 0, 0, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'ASSEMBLY';

-- Inspection / Sorting (SECONDARY)
UPDATE maquinas SET
    horas_setup = 1,
    pph_default = 1000,
    horas_labor = 27,
    scrap_pct = 5,
    orden_uso = NULL
  WHERE isc_norm_maquina(nombre) = 'INSPECTIONSORTING';
UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
  WHERE vigente_hasta IS NULL AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'INSPECTIONSORTING')
    AND vigente_desde < CURRENT_DATE;
DELETE FROM maquina_tarifas
  WHERE vigente_desde = CURRENT_DATE AND maquina_id IN
        (SELECT id FROM maquinas WHERE isc_norm_maquina(nombre) = 'INSPECTIONSORTING');
INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde)
  SELECT id, 0, 0, CURRENT_DATE FROM maquinas
   WHERE isc_norm_maquina(nombre) = 'INSPECTIONSORTING';

