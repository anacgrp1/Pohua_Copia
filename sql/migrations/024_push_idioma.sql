-- El idioma de cada dispositivo suscrito a las notificaciones.
--
-- Por qué: una notificación push la pinta el sistema operativo con el texto
-- que el servidor le mandó. Cuando llega al teléfono ya no hay dónde
-- traducirla, así que hay que mandarla bien escrita de origen — y "de origen"
-- son varios idiomas a la vez, porque el mismo aviso va a todos los
-- dispositivos y dos personas pueden tener Pohua en idiomas distintos.
--
-- Va en la suscripción y no en el usuario porque es del DISPOSITIVO: es el
-- navegador el que dice en qué idioma está Pohua cuando se suscribe, y la
-- misma persona puede tener la computadora en inglés y el teléfono en español.
--
-- 'en' por defecto: es con lo que arranca la aplicación, y las suscripciones
-- que ya existen no saben decir su idioma hasta que el navegador las renueve.

ALTER TABLE push_suscripciones
    ADD COLUMN IF NOT EXISTS idioma VARCHAR(5) NOT NULL DEFAULT 'en';
