-- 034 · Limpieza de Neon: el rol `web_anon` y el plano huérfano de «RFQ-1»
-- ---------------------------------------------------------------------------
-- 1. `web_anon`. Hasta 2026-10 `sql/schema.sql` creaba este rol para un
--    PostgREST de desarrollo que la aplicación nunca usó, y le daba SELECT,
--    INSERT, UPDATE y DELETE sobre TODAS las tablas. Como schema.sql también se
--    aplica en Neon, allí acabó con acceso a 48 tablas, `usuarios` (hashes de
--    contraseña) incluida (scripts/revisar_permisos_bd.py, 2026-10-07). Era
--    NOLOGIN y no había ningún PostgREST conectado, pero bastaba con conectar
--    uno —o la Data API de Neon— para dejarlo todo abierto sin contraseña.
--    schema.sql ya no lo crea; esto lo quita de donde ya existe.
--
--    El rol se intenta borrar, pero si Neon no deja (p. ej. tiene permisos en
--    otra base del mismo proyecto), se queda SIN NINGÚN permiso aquí y la
--    migración sigue: un fallo aquí no puede atascar las migraciones de detrás.
--
-- 2. «RFQ-1». El RFQ de pruebas que borró la 032 tenía su carpeta en el disco
--    de una computadora, y `scripts/subir_planos.py` la volvió a subir: un
--    plano de 9 bytes de un RFQ que no existe. El script ya sólo sube carpetas
--    INT-XXXXXXXX.
--
-- Idempotente: se puede aplicar dos veces sin error.

DELETE FROM rfq_planos WHERE rfq_id = 'RFQ-1';

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'web_anon') THEN
    REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM web_anon;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM web_anon;
    REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM web_anon;
    REVOKE ALL ON SCHEMA public FROM web_anon;
    -- Sin DROP OWNED: desde PostgreSQL 16 quien crea un rol sólo puede
    -- ADMINISTRARLO, no actuar como él, y DROP OWNED lo exige ("permission
    -- denied to drop objects"). Con los REVOKE de arriba ya no le queda nada
    -- en esta base, y DROP ROLE sólo pide CREATEROLE + administrarlo.
    BEGIN
      DROP ROLE web_anon;
      RAISE NOTICE 'Rol web_anon borrado.';
    EXCEPTION WHEN OTHERS THEN
      RAISE NOTICE 'web_anon se queda sin permisos en esta base, pero no se pudo borrar: %', SQLERRM;
    END;
  END IF;
END
$$;
