-- Seed de clientes — Top 12 (COT-71). Fuente: Customer_Contacts_Merged.xlsx (Rodea).
-- Modelo DER (COT-86/87): datos maestros en 'clientes', dominios en 'cliente_dominios'.
-- Verificado a mano. Los Top 12 representan ~50% de las ventas.
-- Se excluyen dominios de matriz compartidos (dovercorp.com, jci.com, hubbell.com).
-- USF Fabrication (rank 3) queda pendiente: no se ubicó su dominio (fase 2).
-- Idempotente.

-- 1) Datos maestros del cliente
INSERT INTO clientes (cliente_id, razon_social, payment_terms, es_estrella) VALUES
  ('CLI-001', 'RD Industries Inc', 'Net 30 Days', TRUE),
  ('CLI-002', 'Toro', '2% 15 Net 60', TRUE),
  ('CLI-004', 'B & W Custom Truck Beds, Inc.', 'Net 30 Days', TRUE),
  ('CLI-005', 'Stone Manufacturing & Supply Company', 'Net 30 Days', TRUE),
  ('CLI-006', 'Safe Fleet (ROM)', 'Net 30 Days', TRUE),
  ('CLI-007', 'Knappco Corporation', '2%-10 Net 30', TRUE),
  ('CLI-008', 'Milbank Mfg. Company', '1%-10 Net 30', TRUE),
  ('CLI-009', 'Ruskin - Air Distribution Technologies', 'Net 90 Days', TRUE),
  ('CLI-010', 'Great Plains Industries', 'Net 30 Days', TRUE),
  ('CLI-011', 'Hubbell Power Systems Inc', 'NET 75', TRUE),
  ('CLI-012', 'Neogen Corporation', 'Credit Card @ 30 Day', TRUE)
ON CONFLICT (cliente_id) DO UPDATE SET es_estrella = TRUE;

-- 2) Dominios de correo por cliente (multi-dominio)
INSERT INTO cliente_dominios (cliente_id, dominio) VALUES
  ('CLI-001', 'rdindustries.com'),
  ('CLI-001', 'rdi3.com'),
  ('CLI-001', 'wernervas.com'),
  ('CLI-002', 'toro.com'),
  ('CLI-002', 'exmark.com'),
  ('CLI-002', 'ditchwitch.com'),
  ('CLI-004', 'turnoverball.com'),
  ('CLI-005', 'stonemfg.net'),
  ('CLI-006', 'safefleet.net'),
  ('CLI-006', 'romcorp.com'),
  ('CLI-007', 'opwglobal.com'),
  ('CLI-007', 'civacon.com'),
  ('CLI-007', 'opwftg.com'),
  ('CLI-008', 'milbankmfg.com'),
  ('CLI-008', 'milbankworks.com'),
  ('CLI-009', 'ruskin.com'),
  ('CLI-009', 'airdistribution.com'),
  ('CLI-009', 'adticorp.com'),
  ('CLI-010', 'gplains.com'),
  ('CLI-011', 'hps.hubbell.com'),
  ('CLI-012', 'neogen.com'),
  ('CLI-012', 'primatechusa.com')
ON CONFLICT (dominio) DO NOTHING;
