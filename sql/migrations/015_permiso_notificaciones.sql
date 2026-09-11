-- =====================================================================
-- 015 — El permiso de las notificaciones (COT-77)
--
-- Quién puede ver el buzón de avisos. Va con permiso propio, por lo mismo que
-- `resumen:ver` (migración 011): el día que ISC quiera que otro puesto reciba
-- los avisos, se concede desde la base y no hay que tocar ni desplegar nada.
--
-- Se concede a `pm`, que es a quien van dirigidos, y a `admin` por el comodín
-- que ya tiene. `quoter` no lo recibe: quedó en sólo lectura de RFQs
-- (migración 010) y atender la cola de dictamen no es parte de eso.
--
-- Idempotente.
-- =====================================================================

BEGIN;

INSERT INTO permisos (codigo, descripcion) VALUES
    ('notificaciones:ver',
     'Ver y marcar como leídos los avisos de RFQ que esperan dictamen.')
ON CONFLICT (codigo) DO UPDATE
    SET descripcion = EXCLUDED.descripcion;

DELETE FROM rol_permisos
WHERE permiso_id = (SELECT id FROM permisos WHERE codigo = 'notificaciones:ver');

INSERT INTO rol_permisos (rol_id, permiso_id)
SELECT r.id, p.id
FROM roles r
JOIN permisos p ON p.codigo = 'notificaciones:ver'
WHERE r.codigo = 'pm'
ON CONFLICT DO NOTHING;

COMMIT;
