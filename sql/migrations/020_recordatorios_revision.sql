-- Constancia de que se mandó el recordatorio por correo de un caso que
-- llevaba demasiado tiempo esperando dictamen.
--
-- El aviso principal es la campana de Pohua y la notificación del teléfono;
-- el correo es el respaldo para cuando nadie entró a mirarlo. Esta tabla es
-- lo que impide que ese respaldo se convierta en una lluvia: una fila por
-- RFQ, y si ya está, no se vuelve a escribir.
CREATE TABLE IF NOT EXISTS recordatorios_revision (
    rfq_id        TEXT PRIMARY KEY,
    estado        TEXT,
    destinatarios TEXT,
    enviado_en    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
