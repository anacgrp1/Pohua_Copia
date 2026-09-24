-- El tope por material de cada máquina.
--
-- Hay alambres que una máquina sólo enrolla hasta un diámetro MENOR que su
-- máximo. Lo contestó Miguel Rodea y hoy afecta a una: la SIMPLEX MC 50 llega a
-- .198" de alambre, pero en temple en aceite (Oil Tempered) sólo a .165"
-- (4.191 mm). Ponerla en un alambre más grueso de ese material cotiza la pieza
-- en una máquina que no puede hacerla.
--
-- `pricing/repository.tope_de_maquina` ya leía estas dos columnas, pero
-- ninguna migración las creaba: el costeo decía en CADA RFQ «No se pudo
-- comprobar el tope por material». NULL en las dos = la máquina no tiene tope.
--
-- `tope_material` es el NOMBRE del material tal como está en `materiales`
-- ("Oil Tempered"): es lo que compara la regla `topeDeMaterial` del núcleo.

ALTER TABLE maquinas ADD COLUMN IF NOT EXISTS tope_material TEXT;
ALTER TABLE maquinas ADD COLUMN IF NOT EXISTS tope_alambre_max_mm NUMERIC;

UPDATE maquinas
   SET tope_material = 'Oil Tempered', tope_alambre_max_mm = 4.191
 WHERE nombre = 'SIMPLEX MC 50' AND tope_material IS NULL;
