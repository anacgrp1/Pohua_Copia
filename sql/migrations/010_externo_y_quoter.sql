-- =====================================================================
-- 010 — La marca "externo", quoter en sólo lectura y el Monitor para admin
--
-- TRES COSAS, y conviene no confundir las dos primeras:
--
-- 1. `usuarios.externo` es una MARCA, no un rol. Dice de qué lado de ISC está
--    la persona: hay quien entra al cotizador sin ser de casa —el caso que lo
--    motivó es una cuenta de Gmail, no del dominio de CGR— y en la lista de
--    usuarios eso se tiene que ver de un vistazo. Un rol contesta "qué hace";
--    esta marca contesta "de dónde es", y son preguntas distintas: puede haber
--    un pm externo igual que un quoter externo.
--
--    La marca NO cambia permisos por sí sola. Quien decide lo que se puede
--    hacer sigue siendo el rol, en un único sitio, que es lo que permite
--    contestar "¿qué puede hacer este usuario?" mirando una sola cosa.
--
-- 2. El rol `quoter` pasa a SÓLO LECTURA (`rfq:leer`). Antes llevaba los
--    mismos cuatro permisos que `pm` —incluidos aprobar/declinar, que dispara
--    un correo al cliente, y arrancar o detener el worker—. Decisión de ISC.
--
--    CONSECUENCIA, que conviene tener presente: a partir de aquí el ÚNICO rol
--    no-admin que puede dictaminar un RFQ, calcular precios y operar el worker
--    es `pm`. Si alguien que hoy es quoter necesita seguir haciendo eso, hay
--    que pasarlo a pm desde Perfil → Usuarios.
--
-- 3. El Monitor —el registro del servicio— pasa a ser sólo de admin. Antes lo
--    veía cualquiera con `worker:operar`, que era pm y quoter. El registro
--    lleva rutas del servidor, correos de clientes y mensajes de error con
--    detalles internos: es material de administración, no de trabajo diario.
--
--    Se hace con un permiso propio, `monitor:ver`, y no comprobando
--    `rol = 'admin'` en el código: si mañana ISC quiere que un puesto concreto
--    vea el registro, se le concede el permiso desde la base y no hay que tocar
--    nada. El comodín `admin` ya lo concede todo, así que basta con NO dárselo
--    a nadie más.
--
-- Idempotente: se puede aplicar tantas veces como haga falta.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. La marca
-- ---------------------------------------------------------------------
ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS externo boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN usuarios.externo IS
    'La persona no es de ISC/CGR. Marca informativa: no concede ni quita '
    'permisos, eso lo decide el rol.';

-- ---------------------------------------------------------------------
-- 2. quoter en sólo lectura
--
-- Se rehace SÓLO el reparto de quoter, con un WHERE explícito. La 006 hace lo
-- mismo para admin/pm/quoter, y se aplica ANTES que este archivo (van por
-- número), así que esto queda por encima. Si algún día se vuelven a aplicar
-- todas desde cero, el orden se mantiene y el resultado también.
-- ---------------------------------------------------------------------
DELETE FROM rol_permisos
WHERE rol_id IN (SELECT id FROM roles WHERE codigo = 'quoter');

INSERT INTO rol_permisos (rol_id, permiso_id)
SELECT r.id, p.id
FROM roles r
JOIN permisos p ON p.codigo = 'rfq:leer'
WHERE r.codigo = 'quoter'
ON CONFLICT DO NOTHING;

UPDATE roles
SET descripcion = 'Consulta los RFQ. Sólo lectura: no dictamina, no calcula '
                  'precios y no opera el servicio de correo.'
WHERE codigo = 'quoter';

-- ---------------------------------------------------------------------
-- 3. El Monitor, sólo para admin
-- ---------------------------------------------------------------------
INSERT INTO permisos (codigo, descripcion) VALUES
    ('monitor:ver', 'Ver el registro del servicio (Monitor).')
ON CONFLICT (codigo) DO UPDATE
    SET descripcion = EXCLUDED.descripcion;

-- A nadie más: el comodín `admin` ya se lo concede al rol admin. Y si alguna
-- vez se concedió a mano a otro rol, esto lo retira.
DELETE FROM rol_permisos
WHERE permiso_id = (SELECT id FROM permisos WHERE codigo = 'monitor:ver');

COMMIT;
