-- =====================================================================
-- DOWN de 005_extension_costeo.sql
-- =====================================================================
-- Revierte la extensión de costeo: elimina las 2 vistas, las 2 funciones
-- (y sus triggers vía CASCADE), la restricción UNIQUE nombrada que se agregó
-- a rfqs, y las 36 tablas de costeo.
--
-- NO toca las tablas base (clientes, rfqs, resortes, resortes_cotizacion,
-- cliente_dominios, correos_procesados, rfq_historial): las columnas que
-- comparten con la migración 004 se revierten con el down de 004, no aquí.
-- El DROP TABLE ... CASCADE elimina automáticamente las FKs que apuntaban a
-- estas tablas desde las tablas base (fk_clientes_condicion, fk_clientes_rep,
-- fk_resortes_material).
-- =====================================================================

BEGIN;

-- Vistas
DROP VIEW IF EXISTS v_material_precio_vigente;
DROP VIEW IF EXISTS v_material_precio_stats;

-- Funciones de "toca actualizado" (CASCADE elimina sus triggers, incluido
-- tg_clientes_toca sobre la tabla base clientes)
DROP FUNCTION IF EXISTS toca_actualizado() CASCADE;
DROP FUNCTION IF EXISTS toca_actualizada() CASCADE;

-- Restricción UNIQUE nombrada que 005 agregó a rfqs (la de schema.sql queda)
ALTER TABLE rfqs DROP CONSTRAINT IF EXISTS uq_rfqs_rfq_version;

-- Las 36 tablas de costeo (CASCADE resuelve las FKs internas y las que
-- apuntan a ellas desde tablas base)
DROP TABLE IF EXISTS
    acabado_alias, acabados, aleacion_surcharges, bitacora,
    cliente_contactos, cliente_direcciones, condiciones_pago,
    cotizacion_documentos, cotizacion_escalones, cotizacion_partidas,
    cotizacion_secuencias, cotizaciones, empaques, escalon_ruta,
    familias_maquina, historial_plating, maquina_capacidades,
    maquina_tarifas, maquinas, material_precio_proveedores, material_precios,
    materiales, orden_compra_lineas, ordenes_compra, param_juegos,
    param_valores, partida_costos, permisos, proveedores,
    resortes_cotizacion_campos, rfq_banderas, rol_permisos, roles,
    subcontratistas, subcontratista_servicios, usuarios
CASCADE;

COMMIT;
