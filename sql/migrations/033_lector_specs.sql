-- 033 · El JSON de ingeniería de cada lectura del plano, en la base
-- ---------------------------------------------------------------------------
-- El lector de planos (vendor/lector, del núcleo) escribe en disco tres cosas
-- por cada plano que lee: el fichero subido (`_uploads`), un PNG por página y
-- por cota (`_crops`) y el JSON de ingeniería (`_specs`). Son dibujos y datos
-- de clientes de ISC en el disco de quien corre el lector, y en Render ese
-- disco se vacía en cada despliegue: la cotización guarda `specUrl` y al día
-- siguiente apuntaba a un 404.
--
-- Desde 2026-10 Pohua se lleva la lectura entera a Neon nada más terminar
-- (api/lector.py): los PNG a `lector_recortes` (019) y el JSON aquí, y borra
-- los ficheros del disco. Lo que pida la calculadora después se sirve desde
-- la base.
--
-- Idempotente: se puede aplicar dos veces sin error.

CREATE TABLE IF NOT EXISTS lector_specs (
    job         text PRIMARY KEY,
    spec        jsonb NOT NULL,
    creado_en   timestamptz NOT NULL DEFAULT now(),
    ultimo_uso  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE lector_specs IS
    'JSON de ingeniería de cada lectura del plano (lo que el lector dejaba en vendor/lector/_specs). Sustituye al disco.';
