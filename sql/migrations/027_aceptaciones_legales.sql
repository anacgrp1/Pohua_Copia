-- Quién aceptó el aviso de privacidad y los términos de uso, y qué versión.
--
-- Por qué: aceptar "al entrar" sin dejar constancia no prueba nada. Con esto
-- se puede decir qué versión de los documentos tenía delante cada persona y
-- cuándo la aceptó, que es justo lo que se pregunta si algún día hay que
-- demostrarlo. Cuando cambia la versión (frontend/legal/responsable.js y
-- app/legal.py), Pohua pide aceptarla otra vez y queda una fila nueva: las
-- anteriores se conservan como historial.
--
-- Sin IP ni navegador a propósito: no hacen falta para acreditar la
-- aceptación de una cuenta que ya entró con su contraseña, y guardar de más
-- también es un incumplimiento (minimización).

CREATE TABLE IF NOT EXISTS aceptaciones_legales (
    id          BIGSERIAL PRIMARY KEY,
    usuario_id  BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    version     VARCHAR(20) NOT NULL,
    aceptado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (usuario_id, version)
);

CREATE INDEX IF NOT EXISTS aceptaciones_legales_usuario
    ON aceptaciones_legales (usuario_id, aceptado_en DESC);
