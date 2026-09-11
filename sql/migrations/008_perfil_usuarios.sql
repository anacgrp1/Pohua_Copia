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
