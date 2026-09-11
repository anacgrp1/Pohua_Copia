-- =====================================================================
-- 011 — El permiso del Resumen
--
-- El Resumen es la pantalla de "cómo va todo": las cifras de la base, lo que
-- está esperando a una persona, el reparto por estado y los materiales más
-- pedidos. Está pensada para el Plant Manager, que necesita la foto completa
-- para decidir, y la ve también admin por el comodín.
--
-- NO la ve `quoter`: ese rol quedó en sólo lectura de RFQs (migración 010) y
-- una pantalla de mando no es parte de consultar un RFQ concreto.
--
-- Va con permiso propio y no comprobando `rol IN ('admin','pm')` en el código,
-- por lo mismo que `monitor:ver`: si mañana ISC quiere que otro puesto vea el
-- resumen, se le concede desde la base y no hay que tocar ni desplegar nada.
--
-- Idempotente: se puede aplicar tantas veces como haga falta.
-- =====================================================================

BEGIN;

INSERT INTO permisos (codigo, descripcion) VALUES
    ('resumen:ver', 'Ver el Resumen: cifras generales y cola de revisión.')
ON CONFLICT (codigo) DO UPDATE
    SET descripcion = EXCLUDED.descripcion;

-- Se rehace sólo esta concesión, con un WHERE explícito: así no se lleva por
-- delante ningún otro permiso de pm si alguien se lo dio a mano.
DELETE FROM rol_permisos
WHERE permiso_id = (SELECT id FROM permisos WHERE codigo = 'resumen:ver');

INSERT INTO rol_permisos (rol_id, permiso_id)
SELECT r.id, p.id
FROM roles r
JOIN permisos p ON p.codigo = 'resumen:ver'
WHERE r.codigo = 'pm'
ON CONFLICT DO NOTHING;

COMMIT;
