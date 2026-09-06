-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 07. Vistas
-- Ejecutar conectado como ELECTRISYS.
-- ============================================================

-- ── Ventas con nombre de cliente y vendedor (evita repetir el JOIN en cada reporte) ──
CREATE OR REPLACE VIEW vw_ventas_detalle AS
SELECT v.id, v.numero, v.creado_en, v.estado, v.metodo_pago,
       v.subtotal, v.descuento, v.impuesto, v.total,
       c.nombre AS cliente, c.identificacion AS cliente_identificacion,
       u.nombre AS vendedor
  FROM ventas v
  LEFT JOIN clientes c ON c.id = v.cliente_id
  JOIN usuarios u       ON u.id = v.usuario_id;

-- ── Repuestos con stock en o por debajo del mínimo (alerta de reabastecimiento) ──
CREATE OR REPLACE VIEW vw_repuestos_stock_bajo AS
SELECT r.id, r.codigo, r.nombre, r.stock, r.stock_minimo,
       c.nombre AS categoria, p.nombre AS proveedor
  FROM repuestos r
  LEFT JOIN categorias c  ON c.id = r.categoria_id
  LEFT JOIN proveedores p ON p.id = r.proveedor_id
 WHERE r.activo = TRUE
   AND r.stock <= r.stock_minimo;

-- ── Total vendido por vendedor y mes (reporte gerencial) ─────────
CREATE OR REPLACE VIEW vw_ventas_por_vendedor AS
SELECT u.id AS usuario_id, u.nombre AS vendedor,
       TRUNC(v.creado_en, 'MM') AS mes,
       COUNT(*) AS num_ventas,
       SUM(v.total) AS total_vendido
  FROM ventas v
  JOIN usuarios u ON u.id = v.usuario_id
 WHERE v.estado != 'anulada'
 GROUP BY u.id, u.nombre, TRUNC(v.creado_en, 'MM');

-- ── Repuestos con su compatibilidad de vehículo (soporte al asistente NLP) ──
CREATE OR REPLACE VIEW vw_repuestos_compatibles AS
SELECT r.id AS repuesto_id, r.codigo, r.nombre AS repuesto, r.stock,
       v.marca, v.modelo, v.anio_desde, v.anio_hasta, v.motor, v.combustible
  FROM repuesto_compatibilidad rc
  JOIN repuestos r ON r.id = rc.repuesto_id
  JOIN vehiculos v ON v.id = rc.vehiculo_id;

PROMPT Vistas creadas correctamente.
