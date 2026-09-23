-- 026_catalogo_compra.sql
--
-- GENERADO por scripts/generar_catalogo.py desde
-- pricing/nucleo/catalogo.json. No editar a mano: se regenera.
--
-- Qué llena y por qué faltaba
-- ---------------------------
-- `material_precios` estaba VACÍA —cero filas— y `empaques` tenía dos
-- de las dieciséis cajas. No fallaba nada: se cotizaba sin precio de
-- alambre y sin empaque, que son dos líneas del P&L.
--
-- Los precios van por CALIBRE, no por material: el mismo Music Wire
-- vale 2.80 $/lb a .020" y 1.80 a .039". El 004-222 es .039", y 1.80
-- es el número que sale en la pantalla correcta.
--
-- La caja de ese tramo es la COR11050, que en Pohua no existía.
--
-- 186 precios, 15 empaques.

BEGIN;

-- Las cajas. Se reemplazan por código: el catálogo manda.
DELETE FROM empaques WHERE codigo = 'COR100803';
INSERT INTO empaques (codigo, descripcion, precio, unidad, activo)
  VALUES ('COR100803', '10 X 8 X 3 BOX', 0.63, 'EACH', true);
DELETE FROM empaques WHERE codigo = 'COR08010';
INSERT INTO empaques (codigo, descripcion, precio, unidad, activo)
  VALUES ('COR08010', '8X6X6 RSC STOCK CARTON', 0.4, 'EACH', true);
DELETE FROM empaques WHERE codigo = 'COR08030';
INSERT INTO empaques (codigo, descripcion, precio, unidad, activo)
  VALUES ('COR08030', '8x8x8  RSC-Glued 32ECT KFT PLN*', 0.48, 'EACH', true);
DELETE FROM empaques WHERE codigo = 'COR18002';
INSERT INTO empaques (codigo, descripcion, precio, unidad, activo)
  VALUES ('COR18002', '18X8X4 RSC STOCK CARTON (Sportworks)', 0.69, 'EACH', true);
DELETE FROM empaques WHERE codigo = 'CHP12012';
INSERT INTO empaques (codigo, descripcion, precio, unidad, activo)
  VALUES ('CHP12012', '12" X 12" 22 pt. Chipboard Pad', 0.16, 'EACH', true);
DELETE FROM empaques WHERE codigo = 'COR11050';
INSERT INTO empaques (codigo, descripcion, precio, unidad, activo)
  VALUES ('COR11050', '11-1/4X8-3/4X12 RSC STK CTN  (Common Boxes)', 0.83, 'EACH', true);
DELETE FROM empaques WHERE codigo = 'COR121212U';
INSERT INTO empaques (codigo, descripcion, precio, unidad, activo)
  VALUES ('COR121212U', '12x12x12 (10,8,6) RSC Stock Carton Boxes', 0.73, 'EACH', true);
DELETE FROM empaques WHERE codigo = 'COR14040';
INSERT INTO empaques (codigo, descripcion, precio, unidad, activo)
  VALUES ('COR14040', '14x14x14 RSC Stock Carton Boxes', 1.33, 'EACH', true);
DELETE FROM empaques WHERE codigo = 'COR24027A';
INSERT INTO empaques (codigo, descripcion, precio, unidad, activo)
  VALUES ('COR24027A', '24" X 12" X 12" Double Wall Box', 1.95, 'EACH', true);
DELETE FROM empaques WHERE codigo = 'COR_ROW_11';
INSERT INTO empaques (codigo, descripcion, precio, unidad, activo)
  VALUES ('COR_ROW_11', 'DOUBLE WALL 12 x 12 x 12 rsc 48ect plain kraft', 1.67, 'EACH', true);
DELETE FROM empaques WHERE codigo = 'COR11812HD /-NON-INVETORY';
INSERT INTO empaques (codigo, descripcion, precio, unidad, activo)
  VALUES ('COR11812HD /-NON-INVETORY', '11 1/4 x 8 3/4 x 12 BOX HEAVY DUTY (US POSTAL & Toro MEXICO', 1.28, 'EACH', true);
DELETE FROM empaques WHERE codigo = 'COR240606';
INSERT INTO empaques (codigo, descripcion, precio, unidad, activo)
  VALUES ('COR240606', '24" x 6" x 6" Stock Carton Boxes (Sportworks)', 0.72, 'EACH', true);
DELETE FROM empaques WHERE codigo = 'TACKY BOARD 11 7/8" X 11 7/8"';
INSERT INTO empaques (codigo, descripcion, precio, unidad, activo)
  VALUES ('TACKY BOARD 11 7/8" X 11 7/8"', 'TACKY BOARD 11 7/8" X 11 7/8"', 0.52634, 'EACH', true);
DELETE FROM empaques WHERE codigo = 'barrels no lids';
INSERT INTO empaques (codigo, descripcion, precio, unidad, activo)
  VALUES ('barrels no lids', '30 gallon drums unlined', 5.5, 'EACH', true);
DELETE FROM empaques WHERE codigo = 'GAYLORD';
INSERT INTO empaques (codigo, descripcion, precio, unidad, activo)
  VALUES ('GAYLORD', 'GAYLORD — special packaging', 30, 'EACH', true);

-- Los precios de alambre, por material y calibre. Se borra el calibre
-- entero antes de meterlo: si no, al regenerar quedarían dos precios
-- para el mismo alambre y ganaría el que saliera primero.
DELETE FROM material_precios WHERE diam_pulg = 0.187 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'BB');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.187, 0.81, 1600, '2026-03-25', 'ISW' FROM materiales WHERE codigo = 'BB';
DELETE FROM material_precios WHERE diam_pulg = 0.05 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'BRASS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.05, 15.78, 25, '2026-04-15', 'ISW' FROM materiales WHERE codigo = 'BRASS';
DELETE FROM material_precios WHERE diam_pulg = 0.148 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'CSI');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.148, 1.4, 600, '2026-04-09', 'GIBBS' FROM materiales WHERE codigo = 'CSI';
DELETE FROM material_precios WHERE diam_pulg = 0.025 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GHD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.025, 5.81, 275, '2026-02-25', 'ISW' FROM materiales WHERE codigo = 'GHD';
DELETE FROM material_precios WHERE diam_pulg = 0.047 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GHD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.047, 2.34, 3750, '2026-04-09', 'GIBBS, ISW' FROM materiales WHERE codigo = 'GHD';
DELETE FROM material_precios WHERE diam_pulg = 0.051 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GHD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.051, 1.64, 51300, '2026-03-18', 'GIBBS, ISW' FROM materiales WHERE codigo = 'GHD';
DELETE FROM material_precios WHERE diam_pulg = 0.054 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GHD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.054, 2.25, 75, '2026-01-14', 'ISW' FROM materiales WHERE codigo = 'GHD';
DELETE FROM material_precios WHERE diam_pulg = 0.062 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GHD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.062, 1.97, 350, '2026-01-07', 'ISW' FROM materiales WHERE codigo = 'GHD';
DELETE FROM material_precios WHERE diam_pulg = 0.08 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GHD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.08, 1.43, 1100, '2026-02-11', 'ISW' FROM materiales WHERE codigo = 'GHD';
DELETE FROM material_precios WHERE diam_pulg = 0.091 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GHD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.091, 1.07, 3250, '2026-04-09', 'GIBBS, ISW' FROM materiales WHERE codigo = 'GHD';
DELETE FROM material_precios WHERE diam_pulg = 0.099 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GHD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.099, 1.1, 3426, '2026-04-09', 'GIBBS, ISW' FROM materiales WHERE codigo = 'GHD';
DELETE FROM material_precios WHERE diam_pulg = 0.12 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GHD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.12, 1.13, 650, '2026-04-15', 'ISW' FROM materiales WHERE codigo = 'GHD';
DELETE FROM material_precios WHERE diam_pulg = 0.148 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GHD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.148, 1.13, 1500, '2026-04-15', 'ISW' FROM materiales WHERE codigo = 'GHD';
DELETE FROM material_precios WHERE diam_pulg = 0.192 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GHD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.192, 1.22, 550, '2026-01-07', 'ISW' FROM materiales WHERE codigo = 'GHD';
DELETE FROM material_precios WHERE diam_pulg = 0.016 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GMW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.016, 5.79, 100, '2026-04-22', 'ISW' FROM materiales WHERE codigo = 'GMW';
DELETE FROM material_precios WHERE diam_pulg = 0.025 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GMW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.025, 4.8, 50, '2026-03-11', 'ISW' FROM materiales WHERE codigo = 'GMW';
DELETE FROM material_precios WHERE diam_pulg = 0.03 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GMW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.03, 6.97, 25, '2026-03-11', 'ISW' FROM materiales WHERE codigo = 'GMW';
DELETE FROM material_precios WHERE diam_pulg = 0.041 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GMW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.041, 2.75, 100, '2026-04-15', 'GIBBS' FROM materiales WHERE codigo = 'GMW';
DELETE FROM material_precios WHERE diam_pulg = 0.047 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GMW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.047, 2.74, 500, '2026-03-18', 'ISW' FROM materiales WHERE codigo = 'GMW';
DELETE FROM material_precios WHERE diam_pulg = 0.054 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GMW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.054, 2.54, 125, '2026-04-09', 'ISW' FROM materiales WHERE codigo = 'GMW';
DELETE FROM material_precios WHERE diam_pulg = 0.105 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GMW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.105, 2, 3650, '2026-01-28', 'GIBBS, INTER' FROM materiales WHERE codigo = 'GMW';
DELETE FROM material_precios WHERE diam_pulg = 0.125 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'GMW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.125, 1.91, 1500, '2026-02-04', 'ISW' FROM materiales WHERE codigo = 'GMW';
DELETE FROM material_precios WHERE diam_pulg = 0.032 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HAST');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.032, 50.04, 2100, '2026-03-11', 'ALLOY WIRE, ELGILOY' FROM materiales WHERE codigo = 'HAST';
DELETE FROM material_precios WHERE diam_pulg = 0.038 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HAST');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.038, 76.71, 50, '2026-03-04', 'ALLOY WIRE' FROM materiales WHERE codigo = 'HAST';
DELETE FROM material_precios WHERE diam_pulg = 0.028 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.028, 1.95, 100, '2026-04-15', 'ISW' FROM materiales WHERE codigo = 'HD';
DELETE FROM material_precios WHERE diam_pulg = 0.031 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.031, 1.54, 450, '2026-02-11', 'ISW' FROM materiales WHERE codigo = 'HD';
DELETE FROM material_precios WHERE diam_pulg = 0.035 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.035, 1.56, 625, '2026-03-25', 'ISW' FROM materiales WHERE codigo = 'HD';
DELETE FROM material_precios WHERE diam_pulg = 0.047 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.047, 4.28, 25, '2026-04-22', 'ISW' FROM materiales WHERE codigo = 'HD';
DELETE FROM material_precios WHERE diam_pulg = 0.054 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.054, 1.08, 750, '2026-02-04', 'ISW' FROM materiales WHERE codigo = 'HD';
DELETE FROM material_precios WHERE diam_pulg = 0.062 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.062, 0.85, 375, '2026-04-09', 'GIBBS, ISW' FROM materiales WHERE codigo = 'HD';
DELETE FROM material_precios WHERE diam_pulg = 0.072 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.072, 1.02, 1560, '2026-03-04', 'GIBBS' FROM materiales WHERE codigo = 'HD';
DELETE FROM material_precios WHERE diam_pulg = 0.08 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.08, 0.91, 275, '2026-02-11', 'ISW' FROM materiales WHERE codigo = 'HD';
DELETE FROM material_precios WHERE diam_pulg = 0.091 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.091, 0.85, 1300, '2026-04-09', 'GIBBS, ISW' FROM materiales WHERE codigo = 'HD';
DELETE FROM material_precios WHERE diam_pulg = 0.099 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.099, 0.94, 3500, '2026-04-29', 'GIBBS, ISW' FROM materiales WHERE codigo = 'HD';
DELETE FROM material_precios WHERE diam_pulg = 0.105 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.105, 0.91, 2525, '2026-01-28', 'GIBBS, ISW' FROM materiales WHERE codigo = 'HD';
DELETE FROM material_precios WHERE diam_pulg = 0.125 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.125, 0.91, 950, '2026-02-11', 'GIBBS, ISW' FROM materiales WHERE codigo = 'HD';
DELETE FROM material_precios WHERE diam_pulg = 0.177 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.177, 0.87, 200, '2026-04-22', 'GIBBS' FROM materiales WHERE codigo = 'HD';
DELETE FROM material_precios WHERE diam_pulg = 0.192 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.192, 0.92, 4000, '2026-04-15', 'ISW' FROM materiales WHERE codigo = 'HD';
DELETE FROM material_precios WHERE diam_pulg = 0.207 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.207, 1.18, 8000, '2026-04-29', 'GIBBS' FROM materiales WHERE codigo = 'HD';
DELETE FROM material_precios WHERE diam_pulg = 0.25 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'HD');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.25, 0.91, 2250, '2026-01-28', 'ISW' FROM materiales WHERE codigo = 'HD';
DELETE FROM material_precios WHERE diam_pulg = 0.02 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.02, 2.8, 1000, '2026-01-28', 'GIBBS, ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.023 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.023, 4.3, 25, '2026-04-15', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.026 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.026, 4.8, 150, '2026-04-20', 'GIBBS, ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.03 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.03, 2.26, 100, '2026-04-22', 'GIBBS' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.031 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.031, 3.95, 25, '2026-04-15', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.032 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.032, 2.2, 100, '2026-03-11', 'GIBBS' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.034 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.034, 2.44, 300, '2026-03-26', 'GIBBS, ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.035 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.035, 3.19, 75, '2026-02-25', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.036 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.036, 2.15, 75, '2026-01-28', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.037 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.037, 1.99, 750, '2026-01-07', 'INTER' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.038 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.038, 2.03, 25, '2026-01-14', 'GIBBS' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.039 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.039, 1.8, 150, '2026-01-07', 'INTER' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.041 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.041, 1.93, 825, '2026-04-10', 'GIBBS, ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.042 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.042, 4.24, 50, '2026-02-11', 'GIBBS, ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.043 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.043, 2.76, 50, '2026-04-09', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.045 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.045, 2.15, 75, '2026-01-07', 'INTER' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.047 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.047, 1.84, 50, '2026-02-11', 'GIBBS' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.048 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.048, 2.08, 75, '2026-02-04', 'GIBBS' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.051 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.051, 2.05, 25, '2026-01-07', 'INTER' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.054 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.054, 1.94, 1500, '2026-02-04', 'GIBBS' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.055 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.055, 5.33, 175, '2026-04-29', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.058 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.058, 2.05, 25, '2026-01-07', 'INTER' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.062 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.062, 1.39, 1500, '2026-02-18', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.063 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.063, 3.24, 50, '2026-04-15', 'GIBBS, ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.067 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.067, 1.05, 150, '2026-04-29', 'GIBBS' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.07 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.07, 1.1, 8000, '2026-02-18', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.072 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.072, 1.2, 2700, '2026-03-11', 'GIBBS, ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.075 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.075, 1.12, 4500, '2026-01-07', 'INTER' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.078 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.078, 1.08, 150, '2026-04-22', 'GIBBS' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.08 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.08, 1.03, 1500, '2026-04-09', 'GIBBS, ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.087 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.087, 0.98, 200, '2026-01-28', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.088 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.088, 1.78, 100, '2026-01-07', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.09 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.09, 0.99, 6000, '2026-01-14', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.091 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.091, 1.05, 1100, '2026-04-22', 'GIBBS, ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.092 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.092, 2.17, 75, '2026-04-22', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.095 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.095, 1.01, 2500, '2026-01-14', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.098 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.098, 1.03, 300, '2026-03-25', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.105 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.105, 1.04, 1775, '2026-04-15', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.106 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.106, 1.01, 450, '2026-01-14', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.112 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.112, 0.98, 750, '2026-01-07', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.115 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.115, 0.98, 1250, '2026-01-07', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.118 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.118, 1.01, 100, '2026-01-28', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.12 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.12, 1.03, 2700, '2026-04-09', 'GIBBS, ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.125 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.125, 1.04, 3750, '2026-04-22', 'GIBBS, ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.135 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.135, 1.03, 675, '2026-04-01', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.142 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.142, 1.01, 2000, '2026-03-11', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.148 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.148, 1.01, 34800, '2026-04-15', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.156 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.156, 1.02, 2600, '2026-04-29', 'GIBBS, ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.162 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.162, 1.01, 3500, '2026-02-04', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.165 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.165, 1.04, 125, '2026-04-15', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.172 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.172, 1.04, 550, '2026-04-15', 'GIBBS, ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.177 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.177, 1.03, 9500, '2026-04-22', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.187 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.187, 1.01, 3100, '2026-04-29', 'GIBBS, ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.192 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.192, 0.99, 4750, '2026-02-04', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.2 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.2, 1.01, 100, '2026-01-14', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.218 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.218, 0.99, 20000, '2026-01-14', 'GIBBS, ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.283 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'MW');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.283, 1.01, 200, '2026-02-04', 'ISW' FROM materiales WHERE codigo = 'MW';
DELETE FROM material_precios WHERE diam_pulg = 0.072 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'OT');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.072, 1.62, 700, '2026-01-08', 'GIBBS' FROM materiales WHERE codigo = 'OT';
DELETE FROM material_precios WHERE diam_pulg = 0.148 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'OT');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.148, 1.35, 3000, '2026-02-18', 'ISW' FROM materiales WHERE codigo = 'OT';
DELETE FROM material_precios WHERE diam_pulg = 0.162 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'OT');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.162, 1.35, 5000, '2026-01-07', 'ISW' FROM materiales WHERE codigo = 'OT';
DELETE FROM material_precios WHERE diam_pulg = 0.177 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'OT');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.177, 1.34, 32500, '2026-03-25', 'GIBBS, ISW' FROM materiales WHERE codigo = 'OT';
DELETE FROM material_precios WHERE diam_pulg = 0.187 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'OT');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.187, 1.34, 19712, '2026-04-01', 'GIBBS, ISW' FROM materiales WHERE codigo = 'OT';
DELETE FROM material_precios WHERE diam_pulg = 0.207 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'OT');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.207, 1.1, 14000, '2026-01-14', 'GIBBS' FROM materiales WHERE codigo = 'OT';
DELETE FROM material_precios WHERE diam_pulg = 0.218 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'OT');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.218, 1.19, 4250, '2026-03-04', 'ISW' FROM materiales WHERE codigo = 'OT';
DELETE FROM material_precios WHERE diam_pulg = 0.375 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'OT');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.375, 1.2, 12000, '2026-04-15', 'GIBBS, ISW' FROM materiales WHERE codigo = 'OT';
DELETE FROM material_precios WHERE diam_pulg = 0.036 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'PHOSB');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.036, 19.47, 500, '2026-03-11', 'ISW' FROM materiales WHERE codigo = 'PHOSB';
DELETE FROM material_precios WHERE diam_pulg = 0.12 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SG');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.12, 1.06, 375, '2026-04-29', 'ISW' FROM materiales WHERE codigo = 'SG';
DELETE FROM material_precios WHERE diam_pulg = 0.011 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.011, 10.59, 25, '2026-04-22', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.012 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.012, 7.98, 25, '2026-03-04', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.013 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.013, 5.6, 50, '2026-04-22', 'GIBBS' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.014 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.014, 7.16, 25, '2026-01-28', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.016 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.016, 6.17, 25, '2026-04-29', 'GIBBS' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.02 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.02, 4.84, 25, '2026-03-18', 'GIBBS' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.022 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.022, 3.89, 50, '2026-01-28', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.023 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.023, 3.67, 50, '2026-03-25', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.024 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.024, 4.71, 150, '2026-04-29', 'GIBBS, ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.025 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.025, 3.54, 175, '2026-02-11', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.026 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.026, 5.14, 250, '2026-04-02', 'INTER, ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.028 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.028, 3.66, 150, '2026-03-11', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.029 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.029, 1.98, 75, '2026-02-25', 'GIBBS' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.031 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.031, 2.77, 175, '2026-04-09', 'GIBBS, ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.032 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.032, 3.05, 4500, '2026-03-11', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.035 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.035, 2.96, 200, '2026-02-04', 'INTER, ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.036 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.036, 2.96, 250, '2026-02-04', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.038 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.038, 3.05, 150, '2026-03-04', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.039 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.039, 2.77, 525, '2026-04-15', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.041 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.041, 2.61, 75, '2026-03-25', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.042 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.042, 2.87, 100, '2026-03-11', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.044 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.044, 2.75, 75, '2026-04-09', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.047 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.047, 2.61, 1675, '2026-04-09', 'GIBBS, ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.05 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.05, 4.07, 75, '2026-04-29', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.054 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.054, 2.79, 500, '2026-01-07', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.055 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.055, 2.59, 200, '2026-04-01', 'GIBBS, ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.058 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.058, 2.9, 50, '2026-01-07', 'INTER' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.06 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.06, 2.52, 200, '2026-04-29', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.062 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.062, 2.52, 275, '2026-04-22', 'GIBBS, ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.063 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.063, 2.52, 455, '2026-04-09', 'GIBBS, INTER, ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.067 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.067, 3, 75, '2026-02-04', 'GIBBS, INTER' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.068 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.068, 2.45, 75, '2026-03-18', 'GIBBS' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.07 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.07, 2.39, 350, '2026-04-09', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.072 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.072, 2.03, 50, '2026-01-08', 'GIBBS' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.08 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.08, 2.96, 3175, '2026-03-25', 'GIBBS, INTER, ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.085 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.085, 1.85, 275, '2026-01-14', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.086 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.086, 1.85, 250, '2026-04-22', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.091 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.091, 1.85, 200, '2026-03-25', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.093 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.093, 1.85, 525, '2026-03-30', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.095 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.095, 1.85, 200, '2026-02-26', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.098 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.098, 1.85, 225, '2026-04-15', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.1 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.1, 1.85, 200, '2026-04-09', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.105 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.105, 1.85, 1250, '2026-04-09', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.112 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.112, 1.85, 350, '2026-02-04', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.116 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.116, 1.85, 850, '2026-01-28', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.118 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.118, 3.48, 25, '2026-04-15', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.125 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.125, 1.85, 700, '2026-04-15', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.135 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.135, 3.64, 600, '2026-01-28', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.148 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.148, 1.85, 1000, '2026-03-25', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.156 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.156, 1.85, 675, '2026-04-09', 'GIBBS, ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.162 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.162, 1.85, 3900, '2026-01-28', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.177 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.177, 1.85, 1500, '2026-01-28', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.187 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.187, 1.85, 475, '2026-04-09', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.192 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.192, 1.85, 2600, '2026-01-07', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.207 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.207, 1.85, 850, '2026-03-25', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.234 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.234, 1.85, 300, '2026-01-07', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.25 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.25, 1.85, 3000, '2026-04-09', 'ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.312 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.312, 2.04, 15250, '2026-04-15', 'GIBBS, ISW' FROM materiales WHERE codigo = 'SS';
DELETE FROM material_precios WHERE diam_pulg = 0.032 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.032, 4.75, 25, '2026-01-07', 'INTER' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.042 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.042, 4.59, 100, '2026-04-09', 'ISW' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.045 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.045, 4.49, 150, '2026-04-09', 'ISW' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.047 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.047, 4.52, 500, '2026-02-04', 'GIBBS' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.051 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.051, 4.88, 50, '2026-01-07', 'ISW' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.06 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.06, 4.39, 400, '2026-01-21', 'GIBBS' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.062 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.062, 1.63, 100, '2026-03-18', 'ISW' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.065 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.065, 5.22, 75, '2026-03-26', 'GIBBS, INTER, ISW' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.067 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.067, 4.22, 100, '2026-04-15', 'ISW' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.105 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.105, 3.73, 675, '2026-04-22', 'ISW' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.12 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.12, 3.67, 150, '2026-03-26', 'GIBBS, ISW' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.125 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.125, 3.43, 1250, '2026-04-15', 'GIBBS' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.13 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.13, 3.53, 350, '2026-03-25', 'GIBBS' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.148 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.148, 3.48, 500, '2026-03-25', 'GIBBS' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.156 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.156, 3.67, 75, '2026-04-09', 'ISW' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.162 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.162, 3.6, 550, '2026-04-15', 'GIBBS' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.177 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.177, 3.67, 4250, '2026-02-18', 'GIBBS, ISW' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.192 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.192, 3.36, 350, '2026-02-25', 'GIBBS' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.207 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.207, 3.59, 750, '2026-01-21', 'GIBBS' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.262 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.262, 3.67, 1750, '2026-04-15', 'ISW' FROM materiales WHERE codigo = 'SS177';
DELETE FROM material_precios WHERE diam_pulg = 0.362 AND material_id IN
       (SELECT id FROM materiales WHERE codigo = 'SS177');
INSERT INTO material_precios
       (material_id, diam_pulg, precio_lb, cantidad_lb, fecha_cotizado, origen)
  SELECT id, 0.362, 3.81, 2500, '2026-04-09', 'GIBBS, ISW' FROM materiales WHERE codigo = 'SS177';

COMMIT;
