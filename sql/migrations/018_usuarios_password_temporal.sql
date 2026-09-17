-- =====================================================================
-- 018 — Contraseña temporal: quién tiene que cambiarla al entrar
--
-- El alta de un usuario y el restablecimiento por parte del administrador
-- ya no piden que alguien invente una contraseña: el servidor genera una
-- temporal, se la enseña al administrador (que la copia o la manda al
-- teléfono de la persona) y deja marcado que ESA persona tiene que
-- cambiarla en cuanto entre. La marca la ve la aplicación al iniciar sesión
-- (login y /api/auth/me) y se borra sola cuando la persona pone la suya.
--
-- También la usa scripts/contrasena_temporal.py para poner a todos los
-- usuarios actuales una contraseña provisional conocida sin saltarse el
-- "cámbiala al entrar".
--
-- Idempotente: ADD COLUMN IF NOT EXISTS.
-- =====================================================================

BEGIN;

ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS debe_cambiar_password boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN usuarios.debe_cambiar_password IS
    'true mientras la persona entre con una contraseña temporal que puso el administrador (o el alta). Se apaga cuando cambia la suya.';

COMMIT;
