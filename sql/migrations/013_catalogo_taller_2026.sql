-- =====================================================================
-- 013 — Lo que faltaba para elegir máquina como la elige Rodea
--
-- El extracto del taller (datos validados por Miguel Rodea el 2026-09-03)
-- trae tres datos por máquina que este esquema no tenía dónde guardar. No son
-- adornos: sin los tres, la elección de máquina de Neon y la de la calculadora
-- pueden dar máquinas distintas para la misma pieza.
--
--   hace_wireform  `maquina_capacidades` sabía de compresión, extensión y
--                  torsión, pero no de wire forms. Sin esta columna, para una
--                  pieza doblada no hay ninguna máquina que se declare capaz.
--
--   orden_uso      El orden de preferencia de Rodea por tipo de resorte. Es
--                  LA regla que decide quién gana entre las máquinas capaces.
--                  Sin ella se ordena por coste, que es otra regla y da otro
--                  resultado.
--
--   scrap_pct      Merma por máquina. Hoy sólo existe el `scrapDefault`
--                  global del juego de parámetros, igual para todas.
--
-- Las tres admiten null: mientras no se carguen, el costeo sigue funcionando
-- exactamente como hoy y quien consulte sabe que no se pudo comprobar. Null
-- aquí significa "no lo sabemos", que es distinto de un cero.
--
-- Idempotente: se puede aplicar las veces que haga falta.
-- =====================================================================

BEGIN;

ALTER TABLE maquina_capacidades
    ADD COLUMN IF NOT EXISTS hace_wireform boolean;

ALTER TABLE maquinas
    ADD COLUMN IF NOT EXISTS orden_uso integer;

ALTER TABLE maquinas
    ADD COLUMN IF NOT EXISTS scrap_pct numeric(6,3);

COMMENT ON COLUMN maquina_capacidades.hace_wireform IS
    'Si la máquina hace wire forms. Null = no se ha capturado, no "no puede".';
COMMENT ON COLUMN maquinas.orden_uso IS
    'Orden de preferencia de Rodea entre las máquinas capaces. Menor = antes.';
COMMENT ON COLUMN maquinas.scrap_pct IS
    'Merma de esta máquina en %. Null = usar el scrapDefault del juego vigente.';

COMMIT;
