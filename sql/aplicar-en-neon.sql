-- =====================================================================
--  APLICAR EN NEON  ·  migraciones 008 y 009
-- =====================================================================
--  Esto es lo que le falta a la base de producción y por lo que Perfil →
--  Usuarios responde "Could not load users: HTTP 500". El error exacto que
--  devuelve Postgres ahora mismo es:
--
--      column u.foto does not exist
--
--  La consulta que lista los usuarios pide u.foto y u.foto_actualizada, y esas
--  columnas las añade la migración 008, que nunca se aplicó en Neon.
--
--  CÓMO APLICARLO
--    Neon → tu proyecto → SQL Editor → pega TODO este archivo → Run.
--    Se puede ejecutar más de una vez sin miedo: las dos migraciones son
--    idempotentes (IF NOT EXISTS / comprobaciones previas).
--
--  Es exactamente el contenido de:
--    sql/migrations/008_perfil_usuarios.sql
--    sql/migrations/009_limpiar_roles.sql
--  No hay nada aquí que no esté ya en el repositorio.
-- =====================================================================


-- ─────────────  008_perfil_usuarios.sql  ─────────────
-- =====================================================================
-- 008 — Foto de perfil  (Perfil y gestión de usuarios)
--
-- La foto se guarda EN LA BASE DE DATOS, no en disco, y no es por comodidad:
-- en Render el sistema de ficheros es efímero —se borra en cada despliegue—,
-- así que una carpeta de subidas perdería todas las fotos cada vez que se
-- publica una versión. Neon es lo único que persiste.
--
-- El navegador recorta y reescala a 256x256 antes de subir, así que cada foto
-- ronda los 30 KB. Con la plantilla de ISC eso son unos pocos cientos de KB en
-- total: irrelevante para la base, y evita montar almacenamiento aparte.
--
-- `foto_actualizada` existe para poder cachear: el frontend pide la foto con
-- ese sello en la URL, así el navegador la reutiliza hasta que cambia de
-- verdad en vez de descargarla en cada pantalla.
--
-- Idempotente: se puede aplicar tantas veces como haga falta.
-- =====================================================================

BEGIN;

ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS foto             bytea,
    ADD COLUMN IF NOT EXISTS foto_tipo        text,
    ADD COLUMN IF NOT EXISTS foto_actualizada timestamptz;

-- Sólo se admiten los formatos que el navegador genera al recortar.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_usuarios_foto_tipo'
    ) THEN
        ALTER TABLE usuarios
            ADD CONSTRAINT chk_usuarios_foto_tipo
            CHECK (foto_tipo IS NULL OR foto_tipo IN ('image/png', 'image/jpeg', 'image/webp'));
    END IF;
END $$;

COMMIT;

-- ─────────────  009_limpiar_roles.sql  ─────────────
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
