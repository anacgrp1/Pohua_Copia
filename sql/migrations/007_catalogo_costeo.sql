-- =====================================================================
-- 007 — Catálogo de costeo inicial  (COT-101)
--
-- Generado a partir de la constante SEED que vive dentro de pricing/engine.js.
-- Esos datos (máquinas, tarifas, materiales, empaques y parámetros) estaban
-- escritos dentro del código JavaScript, así que no se podían consultar,
-- versionar ni corregir sin editar el motor y volver a desplegar.
--
-- A partir de aquí la fuente de verdad es la base: pricing/repository.py lee
-- de estas tablas y el motor recibe lo que salga de ellas.
--
-- LO QUE ESTE ARCHIVO **NO** TRAE: los precios del alambre (material_precios).
-- La constante SEED los tenía vacíos, así que no hay nada que migrar y hay que
-- capturarlos. Mientras esa tabla esté vacía, /api/price responde con
-- completo=false y dice exactamente qué material no tiene precio.
--
-- Idempotente: se puede aplicar las veces que haga falta.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- Familias de máquina
-- ---------------------------------------------------------------------
INSERT INTO familias_maquina (codigo, nombre, multiplicador) VALUES
    ('COILER',    'Enrolladoras',        1.0),
    ('SECONDARY', 'Procesos secundarios', 1.0)
ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre;

-- ---------------------------------------------------------------------
-- Máquinas
--
-- `codigo` tiene que ser único, y los datos de ISC no siempre lo permiten:
-- todas las máquinas de la familia SECONDARY comparten el mismo m1 ("SEC") y
-- varias lo traen vacío. El criterio, para no inventar identificadores:
--   * si el m1 de ISC es único, se usa tal cual  (AIM30, NUCO2, TF-45, ...)
--   * si está repetido o vacío, el código se deriva del NOMBRE real de la
--     máquina (Grinder B -> GRINDER-B).
-- Así cada código sale de un dato que ISC ya tenía escrito. Si en la planta
-- manejan otras claves, se cambian aquí y en maquinas.codigo.
-- ---------------------------------------------------------------------
INSERT INTO maquinas (codigo, nombre, familia_id, costo_compra, anios_amort,
                      horas_anio, carga_pct, oee, horas_labor, horas_setup,
                      clase_setup, pph_default, activo) VALUES
    ('AIM30', 'AIM 3000', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 700000.0, 7, 1920, 1.0, 0.8, 40.0, 6.0, 'High', 327, true),
    ('3D2T', 'AIM AFM-3D2-T', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 250000.0, 7, 1920, 1.0, 0.8, 40.0, 2.0, NULL, 450, true),
    ('NUCO2', 'NUCOIL CSF-200', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 200000.0, 7, 1920, 1.0, 0.8, 40.0, 6.0, 'Medium', 327, true),
    ('NUCOI', 'NUCOIL CSF-400', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 300000.0, 7, 1920, 1.0, 0.8, 40.0, 6.0, NULL, 327, true),
    ('HX-60', 'NUCOIL HX-60', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 400000.0, 7, 1920, 1.0, 0.8, 40.0, 10.0, 'Medium', 327, true),
    ('MC50', 'SIMPLEX MC 50', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 650000.0, 7, 1920, 1.0, 0.8, 40.0, 5.0, NULL, 600, true),
    ('K516', 'KMH-516', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 100000.0, 7, 1920, 1.0, 0.8, 40.0, 5.0, NULL, 600, true),
    ('K508', 'KMH-508', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 100000.0, 7, 1920, 1.0, 0.8, 40.0, 5.0, NULL, 600, true),
    ('SLEEPER-1-2', 'SLEEPER 1/2', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 100000.0, 7, 1920, 1.0, 0.8, 40.0, 2.0, NULL, 360, true),
    ('TF-45', 'SHINKO TF-45', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 700000.0, 7, 1920, 1.0, 0.8, 40.0, 10.0, 'High', 327, true),
    ('TF-23', 'SHINKO TF-23', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 400000.0, 7, 1920, 1.0, 0.8, 40.0, 10.0, 'High', 327, true),
    ('ZX250', 'ZX250', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 250000.0, 7, 1920, 1.0, 0.8, 40.0, 6.0, 'Medium', 450, true),
    ('AUTOL', 'AUTOLINK', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 250000.0, 7, 1920, 1.0, 0.8, 40.0, 6.0, NULL, 600, true),
    ('FZ-11', 'TORIN (FENN) FZ-11', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 200000.0, 7, 1920, 1.0, 0.8, 40.0, 3.0, NULL, 600, true),
    ('W10A', 'TORIN (FENN) W10A', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 150000.0, 7, 1920, 1.0, 0.8, 40.0, 3.0, NULL, 600, true),
    ('W115', 'TORIN (FENN) W115A', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 150000.0, 7, 1920, 1.0, 0.8, 40.0, 3.0, NULL, 600, true),
    ('W11A', 'TORIN (FENN) W11A', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 150000.0, 7, 1920, 1.0, 0.8, 40.0, 3.0, NULL, 600, true),
    ('W11T', 'TORIN (FENN) W11T', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 150000.0, 7, 1920, 1.0, 0.8, 40.0, 3.0, NULL, 600, true),
    ('W125', 'TORIN (FENN) W125', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 150000.0, 7, 1920, 1.0, 0.8, 40.0, 3.0, NULL, 600, true),
    ('W12T', 'TORIN (FENN) W12T', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 150000.0, 7, 1920, 1.0, 0.8, 40.0, 3.0, NULL, 600, true),
    ('Z-11', 'TORIN (FENN) Z-11', (SELECT id FROM familias_maquina WHERE codigo = 'COILER'), 150000.0, 7, 1920, 1.0, 0.8, 40.0, 3.0, NULL, 600, true),
    ('GRINDER-A', 'Grinder A', (SELECT id FROM familias_maquina WHERE codigo = 'SECONDARY'), 150000.0, 7, 1920, 1.0, 0.6, 27.0, 1.0, NULL, NULL, true),
    ('GRINDER-B', 'Grinder B', (SELECT id FROM familias_maquina WHERE codigo = 'SECONDARY'), 140000.0, 7, 1920, 1.0, 0.6, 27.0, 1.0, NULL, NULL, true),
    ('GRINDER-C', 'Grinder C', (SELECT id FROM familias_maquina WHERE codigo = 'SECONDARY'), 130000.0, 7, 1920, 1.0, 0.6, 27.0, 1.0, NULL, NULL, true),
    ('GRINDER-D', 'Grinder D', (SELECT id FROM familias_maquina WHERE codigo = 'SECONDARY'), 120000.0, 7, 1920, 1.0, 0.6, 27.0, 1.0, NULL, NULL, true),
    ('GRINDER-PED', 'Grinder PED', (SELECT id FROM familias_maquina WHERE codigo = 'SECONDARY'), 80000.0, 7, 1920, 1.0, 0.6, 27.0, 1.0, NULL, NULL, true),
    ('STATIONARY-OVEN', 'Stationary Oven', (SELECT id FROM familias_maquina WHERE codigo = 'SECONDARY'), 120000.0, 7, 1920, 1.0, 0.6, 27.0, 3.0, NULL, NULL, true),
    ('LOOPING-HOOKS', 'Looping / Hooks', (SELECT id FROM familias_maquina WHERE codigo = 'SECONDARY'), NULL, 7, 1920, 1.0, 0.6, 27.0, 1.0, NULL, NULL, true),
    ('BENDING-KICK', 'Bending / Kick', (SELECT id FROM familias_maquina WHERE codigo = 'SECONDARY'), NULL, 7, 1920, 1.0, 0.6, 27.0, 1.0, NULL, NULL, true),
    ('ASSEMBLY', 'Assembly', (SELECT id FROM familias_maquina WHERE codigo = 'SECONDARY'), NULL, 7, 1920, 1.0, 0.6, 27.0, 1.0, NULL, NULL, true),
    ('INSPECTION-SORTING', 'Inspection / Sorting', (SELECT id FROM familias_maquina WHERE codigo = 'SECONDARY'), NULL, 7, 1920, 1.0, 0.6, 27.0, 1.0, NULL, NULL, true)
ON CONFLICT (nombre) DO UPDATE
    SET familia_id = EXCLUDED.familia_id, costo_compra = EXCLUDED.costo_compra,
        anios_amort = EXCLUDED.anios_amort, horas_anio = EXCLUDED.horas_anio,
        carga_pct = EXCLUDED.carga_pct, oee = EXCLUDED.oee,
        horas_labor = EXCLUDED.horas_labor, horas_setup = EXCLUDED.horas_setup,
        clase_setup = EXCLUDED.clase_setup, pph_default = EXCLUDED.pph_default;

-- ---------------------------------------------------------------------
-- Capacidades
-- NULL = no capturado (no descarta la máquina al elegirla);
-- false = la máquina NO hace ese tipo de resorte (sí la descarta).
-- ---------------------------------------------------------------------
INSERT INTO maquina_capacidades (maquina_id, alambre_min_mm, alambre_max_mm, od_max_mm,
                                 hace_compresion, hace_extension, hace_torsion, usos, riesgos) VALUES
    ((SELECT id FROM maquinas WHERE nombre = 'AIM 3000'), 0.8, 6.0, 80.0, true, true, true, 'High-capability CNC former. Complex geometries, all three spring types, medium-to-large wire.', 'Highest setup time and tooling cost; reserve for complex or higher-value parts.'),
    ((SELECT id FROM maquinas WHERE nombre = 'AIM AFM-3D2-T'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'NUCOIL CSF-200'), 0.15, 2.0, 25.0, true, true, false, 'Fine-wire compression / extension coiler. Efficient for small high-volume parts.', 'No torsion capability; restricted OD and wire range.'),
    ((SELECT id FROM maquinas WHERE nombre = 'NUCOIL CSF-400'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'NUCOIL HX-60'), 1.0, 6.0, 90.0, true, true, false, 'Heavy-duty coiler for larger compression and extension springs.', 'No torsion capability; limited for complex end forming.'),
    ((SELECT id FROM maquinas WHERE nombre = 'SIMPLEX MC 50'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'KMH-516'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'KMH-508'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'SLEEPER 1/2'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'SHINKO TF-45'), 0.5, 4.5, 55.0, true, true, true, 'Mid-range precision CNC former. Versatile for all types in the medium wire band.', 'Setup-intensive; over-capable (uneconomic) for simple high-volume parts.'),
    ((SELECT id FROM maquinas WHERE nombre = 'SHINKO TF-23'), 0.2, 2.3, 30.0, true, true, true, 'Fine-wire precision CNC former. Small intricate springs, tight tolerances, all types.', 'Not suitable for larger wire; setup-intensive for simple parts.'),
    ((SELECT id FROM maquinas WHERE nombre = 'ZX250'), 0.3, 2.5, 32.0, true, true, true, 'Compact CNC former. Good all-round machine for small / medium parts of all types.', 'Limited to small wire and OD; verify torsion tooling availability.'),
    ((SELECT id FROM maquinas WHERE nombre = 'AUTOLINK'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'TORIN (FENN) FZ-11'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'TORIN (FENN) W10A'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'TORIN (FENN) W115A'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'TORIN (FENN) W11A'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'TORIN (FENN) W11T'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'TORIN (FENN) W125'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'TORIN (FENN) W12T'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'TORIN (FENN) Z-11'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'Grinder A'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'Grinder B'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'Grinder C'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'Grinder D'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'Grinder PED'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'Stationary Oven'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'Looping / Hooks'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'Bending / Kick'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'Assembly'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
    ((SELECT id FROM maquinas WHERE nombre = 'Inspection / Sorting'), NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)
ON CONFLICT (maquina_id) DO UPDATE
    SET alambre_min_mm = EXCLUDED.alambre_min_mm, alambre_max_mm = EXCLUDED.alambre_max_mm,
        od_max_mm = EXCLUDED.od_max_mm, hace_compresion = EXCLUDED.hace_compresion,
        hace_extension = EXCLUDED.hace_extension, hace_torsion = EXCLUDED.hace_torsion,
        usos = EXCLUDED.usos, riesgos = EXCLUDED.riesgos;

-- ---------------------------------------------------------------------
-- Tarifas vigentes
--
-- Dos pasos, en este orden, para que reaplicar la migración no duplique nada:
--   1. Se borran las tarifas abiertas con fecha de HOY. Sólo pueden venir de
--      una ejecución anterior de esta misma migración el mismo día; si se
--      dejaran, la segunda pasada insertaría un juego idéntico al lado.
--   2. Se cierran las tarifas abiertas anteriores, para no dejar dos vigentes
--      a la vez (pricing/repository.py toma la más reciente, pero conviene que
--      sea única).
-- ---------------------------------------------------------------------
DELETE FROM maquina_tarifas
WHERE vigente_hasta IS NULL AND vigente_desde = CURRENT_DATE;

UPDATE maquina_tarifas SET vigente_hasta = CURRENT_DATE
WHERE vigente_hasta IS NULL AND vigente_desde < CURRENT_DATE;

INSERT INTO maquina_tarifas (maquina_id, costo_hora, ccv_objetivo_h, vigente_desde) VALUES
    ((SELECT id FROM maquinas WHERE nombre = 'AIM 3000'), 52.0833, 156.2499, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'AIM AFM-3D2-T'), 18.6012, 55.8036, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'NUCOIL CSF-200'), 14.881, 44.643, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'NUCOIL CSF-400'), 22.3214, 66.9642, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'NUCOIL HX-60'), 29.7619, 89.2857, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'SIMPLEX MC 50'), 48.3631, 145.0893, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'KMH-516'), 7.4405, 22.3215, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'KMH-508'), 7.4405, 22.3215, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'SLEEPER 1/2'), 7.4405, 22.3215, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'SHINKO TF-45'), 52.0833, 156.2499, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'SHINKO TF-23'), 29.7619, 89.2857, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'ZX250'), 18.6012, 55.8036, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'AUTOLINK'), 18.6012, 55.8036, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'TORIN (FENN) FZ-11'), 14.881, 44.643, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'TORIN (FENN) W10A'), 11.1607, 33.4821, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'TORIN (FENN) W115A'), 11.1607, 33.4821, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'TORIN (FENN) W11A'), 11.1607, 33.4821, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'TORIN (FENN) W11T'), 11.1607, 33.4821, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'TORIN (FENN) W125'), 11.1607, 33.4821, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'TORIN (FENN) W12T'), 11.1607, 33.4821, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'TORIN (FENN) Z-11'), 11.1607, 33.4821, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'Grinder A'), 11.1607, 55.8035, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'Grinder B'), 10.4167, 52.0835, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'Grinder C'), 9.6726, 48.363, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'Grinder D'), 8.9286, 44.643, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'Grinder PED'), 5.9524, 29.762, CURRENT_DATE),
    ((SELECT id FROM maquinas WHERE nombre = 'Stationary Oven'), 8.9286, 44.643, CURRENT_DATE);

-- ---------------------------------------------------------------------
-- Materiales
-- Densidad convertida de lb/pulg³ (WIRE_DENS del motor) a kg/m³.
-- ---------------------------------------------------------------------
INSERT INTO materiales (codigo, nombre, astm, densidad_kg_m3, lleva_surcharge, activo) VALUES
    ('316', 'Stainless Steel 316 (ASTM A313 Type 316)', 'A313 Type 316', 7916, true, true),
    ('BB', 'Round Bar Stock', NULL, 7861, false, true),
    ('BRASS', 'Brass Wire', NULL, 8525, false, true),
    ('CSI', 'Chrome Silicon (ASTM A401)', 'A401', 7861, false, true),
    ('GHD', 'Galvanized Hard Drawn', NULL, 7861, false, true),
    ('GMW', 'Galvanized Music Wire', NULL, 7861, false, true),
    ('HAST', 'Hastelloy C-276', NULL, 8885, false, true),
    ('HD', 'Hard Drawn (ASTM A227)', 'A227', 7861, false, true),
    ('MW', 'Music Wire (ASTM A228)', 'A228', 7861, false, true),
    ('OT', 'Oil Tempered (ASTM A229)', 'A229', 7861, false, true),
    ('PHOSB', 'Phosphor Bronze', NULL, 8858, false, true),
    ('SG', 'Soft Galvanized', NULL, 7861, false, true),
    ('SS', 'Stainless Steel 302/304 (ASTM A313)', 'A313', 7916, true, true),
    ('SS177', 'Stainless Steel 17-7 PH', NULL, 7916, true, true)
ON CONFLICT (codigo) DO UPDATE
    SET nombre = EXCLUDED.nombre, astm = EXCLUDED.astm,
        densidad_kg_m3 = EXCLUDED.densidad_kg_m3,
        lleva_surcharge = EXCLUDED.lleva_surcharge;

-- ---------------------------------------------------------------------
-- Empaques
-- ---------------------------------------------------------------------
INSERT INTO empaques (codigo, descripcion, precio, unidad, piezas_por_caja, vigente_desde, activo) VALUES
    ('COR100803', '10 X 8 X 3 BOX', 0.63, 'EACH', NULL, CURRENT_DATE, true),
    ('GAYLORD', 'GAYLORD — special packaging', 30.0, 'EACH', NULL, CURRENT_DATE, true)
ON CONFLICT (codigo) DO UPDATE
    SET descripcion = EXCLUDED.descripcion, precio = EXCLUDED.precio,
        unidad = EXCLUDED.unidad, piezas_por_caja = EXCLUDED.piezas_por_caja;

-- ---------------------------------------------------------------------
-- Parámetros del motor (juego vigente)
-- Eran las constantes DEFAULT_PARAMS de engine.js. Ahora se pueden cambiar sin
-- tocar código: se crea un juego nuevo con vigente_desde futuro y se cierra el
-- anterior. El histórico queda, así que una cotización vieja se puede
-- reconstruir con los parámetros que estaban vigentes ese día.
-- ---------------------------------------------------------------------
UPDATE param_juegos SET vigente_hasta = CURRENT_DATE
WHERE vigente_hasta IS NULL AND vigente_desde < CURRENT_DATE;

INSERT INTO param_juegos (nombre, vigente_desde, nota)
SELECT 'Parámetros base (migrados de engine.js)', CURRENT_DATE,
       'Generado por sql/migrations/007. Valores idénticos a DEFAULT_PARAMS del motor.'
WHERE NOT EXISTS (
    SELECT 1 FROM param_juegos
    WHERE nombre = 'Parámetros base (migrados de engine.js)'
      AND vigente_desde = CURRENT_DATE
);

INSERT INTO param_valores (param_juego_id, clave, valor) VALUES
    ((SELECT id FROM param_juegos WHERE nombre = 'Parámetros base (migrados de engine.js)' ORDER BY vigente_desde DESC LIMIT 1), 'matMk', '6'::jsonb),
    ((SELECT id FROM param_juegos WHERE nombre = 'Parámetros base (migrados de engine.js)' ORDER BY vigente_desde DESC LIMIT 1), 'compMk', '6'::jsonb),
    ((SELECT id FROM param_juegos WHERE nombre = 'Parámetros base (migrados de engine.js)' ORDER BY vigente_desde DESC LIMIT 1), 'consMk', '6'::jsonb),
    ((SELECT id FROM param_juegos WHERE nombre = 'Parámetros base (migrados de engine.js)' ORDER BY vigente_desde DESC LIMIT 1), 'subMk', '50'::jsonb),
    ((SELECT id FROM param_juegos WHERE nombre = 'Parámetros base (migrados de engine.js)' ORDER BY vigente_desde DESC LIMIT 1), 'contribution', '20'::jsonb),
    ((SELECT id FROM param_juegos WHERE nombre = 'Parámetros base (migrados de engine.js)' ORDER BY vigente_desde DESC LIMIT 1), 'hq', '5'::jsonb),
    ((SELECT id FROM param_juegos WHERE nombre = 'Parámetros base (migrados de engine.js)' ORDER BY vigente_desde DESC LIMIT 1), 'commissionNic', '5'::jsonb),
    ((SELECT id FROM param_juegos WHERE nombre = 'Parámetros base (migrados de engine.js)' ORDER BY vigente_desde DESC LIMIT 1), 'ohLadder', '[12, 16, 20, 24]'::jsonb),
    ((SELECT id FROM param_juegos WHERE nombre = 'Parámetros base (migrados de engine.js)' ORDER BY vigente_desde DESC LIMIT 1), 'ohSub', '28'::jsonb),
    ((SELECT id FROM param_juegos WHERE nombre = 'Parámetros base (migrados de engine.js)' ORDER BY vigente_desde DESC LIMIT 1), 'ohMin', '10'::jsonb),
    ((SELECT id FROM param_juegos WHERE nombre = 'Parámetros base (migrados de engine.js)' ORDER BY vigente_desde DESC LIMIT 1), 'ohMax', '35'::jsonb),
    ((SELECT id FROM param_juegos WHERE nombre = 'Parámetros base (migrados de engine.js)' ORDER BY vigente_desde DESC LIMIT 1), 'floorBase', '800'::jsonb),
    ((SELECT id FROM param_juegos WHERE nombre = 'Parámetros base (migrados de engine.js)' ORDER BY vigente_desde DESC LIMIT 1), 'floorPerOp', '200'::jsonb),
    ((SELECT id FROM param_juegos WHERE nombre = 'Parámetros base (migrados de engine.js)' ORDER BY vigente_desde DESC LIMIT 1), 'scrapDefault', '5'::jsonb),
    ((SELECT id FROM param_juegos WHERE nombre = 'Parámetros base (migrados de engine.js)' ORDER BY vigente_desde DESC LIMIT 1), 'wireMaxIn', '0.59'::jsonb)
ON CONFLICT (param_juego_id, clave) DO UPDATE SET valor = EXCLUDED.valor;

COMMIT;

-- =====================================================================
-- PENDIENTE DE CAPTURA (sin esto el costeo sale incompleto a propósito):
--
--   material_precios      precio por libra de cada calibre de alambre
--   aleacion_surcharges   sobreprecio vigente de los inoxidables (SS, SS177, 316)
--   subcontratistas       recubrimientos y servicios externos
--
-- Mientras falten, POST /api/price responde con completo=false y la lista de
-- lo que falta, en vez de devolver un precio que parezca cotizable.
-- =====================================================================
