-- Un correo, una fila: el EntryID de Outlook va en su columna, no en otra fila.
--
-- Desde 2026-09-24 el control de duplicados reconoce un correo por su
-- Message-ID y también por el EntryID de Outlook (cuando el guardián de
-- Outlook no deja leer la cabecera, el correo sólo se conoce por el
-- EntryID). La primera versión apuntaba el EntryID como una SEGUNDA fila en
-- `correos_procesados`, y el recorrido del correo («Customer email» en la
-- pantalla Mail) cuenta filas: un correo salía como dos.
--
-- Aquí el EntryID pasa a una columna de la misma fila. Las filas de más que
-- dejó aquella versión se reconocen sin ambigüedad: un EntryID no lleva «@»
-- y un Message-ID sí, y las dos filas del mismo correo comparten remitente,
-- asunto y fecha. Se funden: el EntryID se guarda en la fila del Message-ID
-- y la fila sobrante se borra.

ALTER TABLE correos_procesados ADD COLUMN IF NOT EXISTS entry_id TEXT;
CREATE INDEX IF NOT EXISTS idx_correos_entry_id ON correos_procesados (entry_id);

UPDATE correos_procesados c
   SET entry_id = e.message_id
  FROM correos_procesados e
 WHERE c.message_id LIKE '%@%'
   AND e.message_id NOT LIKE '%@%'
   AND e.id <> c.id
   AND e.remitente IS NOT DISTINCT FROM c.remitente
   AND e.asunto IS NOT DISTINCT FROM c.asunto
   AND e.fecha_correo IS NOT DISTINCT FROM c.fecha_correo
   AND c.entry_id IS NULL;

DELETE FROM correos_procesados e
 WHERE e.message_id NOT LIKE '%@%'
   AND EXISTS (SELECT 1 FROM correos_procesados c
                WHERE c.entry_id = e.message_id AND c.id <> e.id);
