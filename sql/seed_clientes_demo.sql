-- =====================================================================
-- Clientes de DEMOSTRACIÓN para el entorno local
--
-- Sustituye a sql/seed_clientes_top12.sql, que llevaba razones sociales,
-- condiciones de pago y dominios de correo de clientes reales. Esos datos ya
-- están cargados en Neon, así que en el repositorio sólo estorbaban: cualquiera
-- con acceso al código tenía la cartera comercial de la empresa.
--
-- Todo lo de aquí es inventado. Los dominios usan el TLD .example, reservado
-- por la RFC 2606 justamente para esto: no existe ni puede registrarse, así que
-- no hay forma de que un correo de prueba salga hacia una empresa real.
--
-- Se carga a mano, sólo contra la base local:
--     make db-demo
--
-- NO se aplica en producción: no está en sql/migrations/, así que ni
-- scripts/db_init.sh ni el workflow de Neon lo tocan.
-- =====================================================================

BEGIN;

INSERT INTO clientes (cliente_id, razon_social, rfc, correo_principal,
                      payment_terms, tax_state, origen_datos, estatus, es_estrella) VALUES
    ('DEMO-001', 'Resortes del Bajío S.A. de C.V.',   'RBA010203AB1', 'compras@bajio-demo.example',      'Net 30', 'GTO', 'demo', 'Activo',   true),
    ('DEMO-002', 'Manufacturas Altiplano S. de R.L.', 'MAL040506CD2', 'abastecimiento@altiplano.example','Net 45', 'SLP', 'demo', 'Activo',   true),
    ('DEMO-003', 'Northgate Industrial Supply Inc.',  NULL,           'purchasing@northgate.example',    'Net 60', 'TX',  'demo', 'Activo',   true),
    ('DEMO-004', 'Ensambles Rivera y Asociados',      'ERA070809EF3', 'ana.compras@rivera-demo.example', 'Net 30', 'NLE', 'demo', 'Activo',   false),
    ('DEMO-005', 'Componentes Sierra Verde S.A.',     'CSV101112GH4', 'rfq@sierraverde.example',         'Contado','QRO', 'demo', 'Activo',   false),
    ('DEMO-006', 'Talleres Peninsular',               'TPE131415IJ5', 'cotizaciones@peninsular.example', 'Net 15', 'YUC', 'demo', 'Inactivo', false)
ON CONFLICT (cliente_id) DO NOTHING;

-- El mapeo dominio → cliente es lo que usa app/clients/mapper.py para saber de
-- qué cliente viene un correo entrante. Sin al menos una fila aquí, ese paso
-- del flujo no se puede probar en local.
INSERT INTO cliente_dominios (cliente_id, dominio) VALUES
    ('DEMO-001', 'bajio-demo.example'),
    ('DEMO-002', 'altiplano.example'),
    ('DEMO-003', 'northgate.example'),
    ('DEMO-004', 'rivera-demo.example'),
    ('DEMO-005', 'sierraverde.example'),
    ('DEMO-006', 'peninsular.example')
ON CONFLICT (dominio) DO NOTHING;

COMMIT;
