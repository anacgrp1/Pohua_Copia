-- Fuera el RFQ de pruebas «RFQ-1» que las pruebas dejaron en la base.
--
-- `tests/rfq/test_flow.py` ensayaba el recorrido completo de un correo con
-- un RFQ ficticio («RFQ-1», remitente de neogen.com, un «plano.pdf» que no
-- es un PDF) y tapaba el veredicto y los avisos, pero no el alta: cuando la
-- batería corría en una máquina con `.env` apuntando a Neon, el alta iba a
-- la base de verdad. Así apareció «Quote RFQ-1 · neogen.com» en la ventana
-- de revisión, con el plano ilegible y sin cantidades.
--
-- Las pruebas ya no pueden llegar a la base (tests/conftest.py fija una
-- conexión imposible salvo que se pida otra a propósito). Esto limpia lo que
-- quedó. Los RFQ de verdad se llaman INT-XXXXXXXX: «RFQ-1» sólo existe en
-- las pruebas.

DELETE FROM notificaciones        WHERE rfq_id = 'RFQ-1';
DELETE FROM recordatorios_revision WHERE rfq_id = 'RFQ-1';
DELETE FROM correos_salida        WHERE rfq_id = 'RFQ-1';
DELETE FROM resortes_cotizacion   WHERE rfq_id = 'RFQ-1';
DELETE FROM rfq_planos            WHERE rfq_id = 'RFQ-1';
DELETE FROM rfq_historial         WHERE rfq_id = 'RFQ-1';
DELETE FROM cotizaciones          WHERE rfq_id = 'RFQ-1';
DELETE FROM rfqs                  WHERE rfq_id = 'RFQ-1';   -- rfq_banderas cae en cascada
DELETE FROM correos_procesados    WHERE remitente = 'roberto.perez@neogen.com'
                                    AND asunto LIKE 'RFQ 4500%';
