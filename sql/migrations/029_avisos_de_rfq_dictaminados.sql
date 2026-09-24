-- Los avisos de los RFQ que ya se aprobaron o declinaron, por atendidos.
--
-- Desde ahora el dictamen del PM cierra solo los avisos de su RFQ
-- (app/feasibility/pm_decision.py → notifications.repository.cerrar_del_rfq).
-- Los que se dictaminaron ANTES seguían en la campana pidiendo algo que ya se
-- hizo. Esto los pone al día una vez. No se borran: quedan como leídos, que
-- es la constancia de que se atendieron.

UPDATE notificaciones
   SET leida_en = now(), leida_por_correo = 'dictamen'
 WHERE leida_en IS NULL
   AND rfq_id IN (
        SELECT rfq_id FROM rfqs
         GROUP BY rfq_id
        HAVING bool_and(estado IN ('Approved', 'Declined')));
