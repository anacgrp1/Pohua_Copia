-- =====================================================================
-- 006 — Roles y permisos para el login de la API  (COT-100)
--
-- Las tablas usuarios / roles / permisos / rol_permisos ya las crea la
-- migración 005. Esta sólo las siembra y añade el índice que falta.
--
-- CRITERIO: aquí sólo van los roles que ISC maneja de verdad.
--
--   pm      El Plant Manager, figura que ya existe en todo el sistema:
--           app/feasibility/pm_decision.py, el flujo de aprobar/declinar, los
--           avisos de "que lo vea el PM" del extractor de correo.
--   quoter  Quien cotiza. Mismos permisos que el PM.
--   admin   No es un puesto de la planta, es una necesidad técnica: alguien
--           tiene que poder dar de alta a los demás y operar el worker.
--
-- pm y quoter comparten permisos pero son DOS roles separados a propósito: el
-- rol viaja en el token de sesión y queda en la bitácora, así que al ver quién
-- aprobó o declinó un RFQ se distingue si lo hizo Planta o quien cotiza. Si
-- fueran un solo rol, esa distinción se perdería.
--
-- No se siembra ningún rol más. Si en ISC hay otros puestos que deban entrar
-- al cotizador (compras, ingeniería, calidad...), se añaden abajo con sus
-- permisos reales; el mecanismo ya está y no hay que tocar código.
--
-- Idempotente: se puede aplicar tantas veces como haga falta.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- Roles
-- ---------------------------------------------------------------------
INSERT INTO roles (codigo, nombre, descripcion) VALUES
    ('admin',  'Administrador', 'Acceso total. Da de alta usuarios y opera el worker de correo.'),
    ('pm',     'Plant Manager', 'Dictamina la factibilidad de los RFQ: aprueba o declina.'),
    ('quoter', 'Quoter',        'Cotiza los RFQ. Mismos permisos que el Plant Manager.')
ON CONFLICT (codigo) DO UPDATE
    SET nombre = EXCLUDED.nombre,
        descripcion = EXCLUDED.descripcion;

-- ---------------------------------------------------------------------
-- Permisos
-- Uno por acción con consecuencias, no más granular de lo necesario.
-- ---------------------------------------------------------------------
INSERT INTO permisos (codigo, descripcion) VALUES
    ('admin',             'Comodín: concede cualquier permiso.'),
    ('rfq:leer',          'Ver la lista y el detalle de RFQs.'),
    ('rfq:dictaminar',    'Aprobar o declinar un RFQ (dispara correo al cliente).'),
    ('precio:calcular',   'Ejecutar el motor de costeo.'),
    ('worker:operar',     'Arrancar, detener y ejecutar a mano el ciclo de correo.'),
    ('usuario:gestionar', 'Alta, baja y cambio de rol de usuarios.')
ON CONFLICT (codigo) DO UPDATE
    SET descripcion = EXCLUDED.descripcion;

-- ---------------------------------------------------------------------
-- Reparto rol → permisos
--
-- Se borra y se reconstruye SÓLO para los roles que declara este archivo, con
-- un WHERE explícito: si mañana se crea un rol nuevo a mano en la base, esta
-- migración no se lo lleva por delante al volver a aplicarse.
-- ---------------------------------------------------------------------
DELETE FROM rol_permisos
WHERE rol_id IN (SELECT id FROM roles WHERE codigo IN ('admin', 'pm', 'quoter'));

INSERT INTO rol_permisos (rol_id, permiso_id)
SELECT r.id, p.id
FROM roles r
JOIN permisos p ON (
        (r.codigo = 'admin')
        -- pm y quoter llevan el mismo juego de permisos.
     OR (r.codigo IN ('pm', 'quoter')
         AND p.codigo IN ('rfq:leer', 'rfq:dictaminar',
                          'precio:calcular', 'worker:operar'))
)
WHERE r.codigo IN ('admin', 'pm', 'quoter')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------
-- El login busca por correo sin distinguir mayúsculas: sin este índice la
-- consulta hace un recorrido completo de la tabla.
-- ---------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS ux_usuarios_correo_lower
    ON usuarios (lower(correo));

COMMIT;

-- =====================================================================
-- CÓMO AÑADIR UN ROL REAL
--
-- Ejemplo, un puesto que consulta y cotiza pero NO dictamina:
--
--   INSERT INTO roles (codigo, nombre, descripcion)
--   VALUES ('compras', 'Compras', 'Consulta RFQs y calcula precios.');
--
--   INSERT INTO rol_permisos (rol_id, permiso_id)
--   SELECT r.id, p.id FROM roles r, permisos p
--   WHERE r.codigo = 'compras'
--     AND p.codigo IN ('rfq:leer', 'precio:calcular');
--
-- Y añade el código a la lista ROLES de scripts/crear_usuario.py para poder
-- asignarlo desde la consola.
-- =====================================================================
