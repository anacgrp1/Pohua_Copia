-- =====================================================================
-- 009 — Retirar los roles que ISC no usa
--
-- Una versión anterior de 006 sembró los roles 'ventas' y 'consulta'. No
-- existen como puestos en ISC: los inventé yo. La 006 ya no los siembra, pero
-- una migración que sólo hace INSERT no borra lo que sembró antes, así que en
-- cualquier base creada con aquella versión siguen ahí — y ahora que el alta
-- de usuarios lee los roles de la base, aparecerían en el desplegable.
--
-- Se borran SÓLO si no hay ningún usuario con ellos. Si alguien los tiene
-- asignados, la migración no los toca y avisa: reasignar a una persona a otro
-- rol es una decisión de ISC, no de un script.
--
-- Idempotente: se puede aplicar tantas veces como haga falta.
-- =====================================================================

BEGIN;

DO $$
DECLARE
    sobrantes text[] := ARRAY['ventas', 'consulta'];
    rol       text;
    en_uso    int;
BEGIN
    FOREACH rol IN ARRAY sobrantes LOOP
        SELECT COUNT(*) INTO en_uso
        FROM usuarios u
        JOIN roles r ON r.id = u.rol_id
        WHERE r.codigo = rol;

        IF en_uso > 0 THEN
            RAISE NOTICE
                'El rol "%" tiene % usuario(s) asignado(s): NO se borra. '
                'Cámbialos de rol desde Perfil → Usuarios y vuelve a aplicar esta migración.',
                rol, en_uso;
        ELSE
            -- rol_permisos no tiene ON DELETE CASCADE hacia roles en todas las
            -- versiones del esquema: se limpia a mano antes de borrar el rol.
            DELETE FROM rol_permisos
            WHERE rol_id IN (SELECT id FROM roles WHERE roles.codigo = rol);

            DELETE FROM roles WHERE roles.codigo = rol;
        END IF;
    END LOOP;
END $$;

COMMIT;
