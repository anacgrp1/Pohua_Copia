-- 022 · Las banderas del dictamen, con su código y sus datos
-- ---------------------------------------------------------------------------
-- `rfq_banderas` guardaba sólo el TÍTULO, ya escrito en español ("Falta
-- diámetro de alambre para dictaminar."). Esa frase se pinta tal cual en la
-- ficha del RFQ y en la ventana de revisión, así que con Pohua en inglés la
-- pantalla salía mitad y mitad.
--
-- El motor de factibilidad ya razona con un CÓDIGO (`dato_ausente`,
-- `fuera_de_rango`…) y con el campo, el valor y el límite; lo que se perdía
-- era todo eso al guardar. Con el código y sus datos, la frase se arma en el
-- navegador en el idioma que toque, y el título se queda como respaldo para
-- las banderas de antes y para cualquier versión de la web que no conozca un
-- código nuevo.

ALTER TABLE rfq_banderas ADD COLUMN IF NOT EXISTS codigo TEXT;
ALTER TABLE rfq_banderas ADD COLUMN IF NOT EXISTS datos  JSONB;
