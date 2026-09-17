-- =====================================================================
-- 017 — El quoter puede usar las calculadoras
--
-- La 010 dejó al rol `quoter` en sólo lectura (`rfq:leer`), y con eso la
-- pantalla Quoting se le quedaba en blanco: las calculadoras de ISC se sirven
-- detrás de `precio:calcular`, y sin ese permiso el diagnóstico contestaba
-- 403 y la pantalla enseñaba un aviso que hablaba de otra cosa ("el HTML se
-- genera desde el núcleo…"). Un quoter que no puede cotizar no es un quoter.
--
-- Se le concede `precio:calcular` y nada más: sigue sin dictaminar RFQs (eso
-- manda correo al cliente), sin operar el worker y sin ver el Monitor.
--
-- Idempotente: se rehace sólo esta concesión, con WHERE explícito.
-- =====================================================================

BEGIN;

INSERT INTO rol_permisos (rol_id, permiso_id)
SELECT r.id, p.id
FROM roles r
JOIN permisos p ON p.codigo = 'precio:calcular'
WHERE r.codigo = 'quoter'
ON CONFLICT DO NOTHING;

COMMIT;
