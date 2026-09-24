-- Fuera los parámetros de la calculadora V5; sólo quedan los de la V7.
--
-- La migración 007 sembró en su día el juego «Parámetros base (migrados de
-- engine.js)» con los valores del motor de ENTONCES, la V5: escalera de
-- overheads 12/16/20/24 según el número de operaciones y 28 % con
-- subcontratación. La calculadora que usa la planta es la V7 (el núcleo):
-- 30 % plano y 35 % con subcontratación, y el motor de Pohua es hoy ese
-- mismo. Con el juego de la V5 la ventana del RFQ daba $0.3223 donde la
-- calculadora da $0.3946: dos precios del mismo resorte por un 20 % frente
-- a un 30 %.
--
-- La V5 ya no existe en ninguna otra parte del proyecto (su motor se quitó
-- en 2026-09 y la 007 siembra ahora los valores de la V7), así que su juego
-- de parámetros se BORRA, no se cierra: no fue una decisión del taller que
-- haya que conservar fechada, era un marcador del motor viejo. Se reconoce
-- por su escalera, que ningún juego de la V7 tiene. Las cotizaciones ya
-- hechas guardan su precio en el RFQ y no cambian.
--
-- Después, si no queda un juego vigente con la escalera de la V7, se crea
-- con DEFAULT_PARAMS de pricing/nucleo/engine.js más el transporte del
-- alambre (constante de ISC, la misma del extracto del taller). Una prueba
-- comprueba que los valores coinciden con el motor.

DO $$
DECLARE
    nuevo bigint;
BEGIN
    DELETE FROM param_juegos
     WHERE id IN (
        SELECT pj.id
          FROM param_juegos pj
          JOIN param_valores pv ON pv.param_juego_id = pj.id
         WHERE pv.clave = 'ohLadder'
           AND pv.valor = '[12, 16, 20, 24]'::jsonb
     );

    IF EXISTS (
        SELECT 1
          FROM param_valores pv
          JOIN param_juegos pj ON pj.id = pv.param_juego_id
         WHERE pj.vigente_desde <= CURRENT_DATE
           AND (pj.vigente_hasta IS NULL OR pj.vigente_hasta > CURRENT_DATE)
           AND pv.clave = 'ohLadder'
           AND pv.valor = '[30, 30, 30, 30]'::jsonb
    ) THEN
        RETURN;
    END IF;

    UPDATE param_juegos
       SET vigente_hasta = CURRENT_DATE
     WHERE vigente_hasta IS NULL OR vigente_hasta > CURRENT_DATE;

    INSERT INTO param_juegos (nombre, vigente_desde, nota)
    VALUES ('Parámetros de la calculadora (V7)', CURRENT_DATE,
            'sql/migrations/030. DEFAULT_PARAMS de pricing/nucleo/engine.js: '
            'overheads 30 % plano y 35 % con subcontratación, como la '
            'calculadora de la planta, más el transporte del alambre.')
    RETURNING id INTO nuevo;

    INSERT INTO param_valores (param_juego_id, clave, valor) VALUES
        (nuevo, 'matMk',         '6'::jsonb),
        (nuevo, 'compMk',        '6'::jsonb),
        (nuevo, 'consMk',        '6'::jsonb),
        (nuevo, 'subMk',         '50'::jsonb),
        (nuevo, 'contribution',  '20'::jsonb),
        (nuevo, 'hq',            '5'::jsonb),
        (nuevo, 'commissionNic', '5'::jsonb),
        (nuevo, 'ohLadder',      '[30, 30, 30, 30]'::jsonb),
        (nuevo, 'ohSub',         '35'::jsonb),
        (nuevo, 'ohMin',         '10'::jsonb),
        (nuevo, 'ohMax',         '35'::jsonb),
        (nuevo, 'floorBase',     '800'::jsonb),
        (nuevo, 'floorPerOp',    '200'::jsonb),
        (nuevo, 'scrapDefault',  '5'::jsonb),
        (nuevo, 'wireMaxIn',     '0.59'::jsonb),
        (nuevo, 'transpPerLb',   '0.3'::jsonb);
END
$$;
