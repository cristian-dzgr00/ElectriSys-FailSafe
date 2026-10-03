-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 07. Vistas (incluye vw_totales_documento)
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
 WHERE r.activo = 1
   AND r.stock <= r.stock_minimo;

-- ── Total vendido por vendedor y mes (reporte gerencial) ─────────
CREATE OR REPLACE VIEW vw_ventas_por_vendedor AS
SELECT u.id AS usuario_id, u.nombre AS vendedor,
       TRUNC(fn_fecha_local(v.creado_en), 'MM') AS mes,
       COUNT(*) AS num_ventas,
       SUM(v.total) AS total_vendido
  FROM ventas v
  JOIN usuarios u ON u.id = v.usuario_id
 WHERE v.estado != 'anulada'
 GROUP BY u.id, u.nombre, TRUNC(fn_fecha_local(v.creado_en), 'MM');

-- ── Repuestos con su compatibilidad de vehículo (soporte al asistente NLP) ──
-- Ampliada con descripcion/precio_venta/categoria/proveedor: son las
-- columnas que ya devuelve GET /api/repuestos/buscar-compatibles
-- (backend/src/routes/repuestos.php) y que la versión original de esta
-- vista no traía.
CREATE OR REPLACE VIEW vw_repuestos_compatibles AS
SELECT r.id AS repuesto_id, r.codigo, r.nombre AS repuesto, r.descripcion,
       r.stock, r.precio_venta, cat.nombre AS categoria, p.nombre AS proveedor,
       v.marca, v.modelo, v.anio_desde, v.anio_hasta, v.motor, v.combustible
  FROM repuesto_compatibilidad rc
  JOIN repuestos r          ON r.id = rc.repuesto_id
  JOIN vehiculos v          ON v.id = rc.vehiculo_id
  LEFT JOIN categorias cat  ON cat.id = r.categoria_id
  LEFT JOIN proveedores p   ON p.id = r.proveedor_id
 WHERE r.activo = 1;

-- ── Totales de cada documento calculados desde sus detalles ──────
-- Une ventas, cotizaciones y pedidos. El subtotal sale de SUMAR los
-- detalles (no de lo que diga la cabecera) y el total se recalcula con
-- el descuento y el impuesto de la cabecera. La columna DIFERENCIA
-- compara ese total con el guardado: debe ser 0. Sirve para:
--   1) detectar cabeceras que no cuadran con sus líneas, y
--   2) preparar la 3FN: cuando el backend lea de acá, se podrán quitar
--      las columnas derivadas de las cabeceras (ver 15_normalizacion_3fn.sql).
-- Los pedidos no llevan descuento ni IVA, por eso van en 0.
CREATE OR REPLACE VIEW vw_totales_documento AS
SELECT 'venta' AS tipo, v.id AS documento_id, v.numero, v.estado,
       NVL(d.subtotal_detalle, 0)                                     AS subtotal_detalle,
       v.descuento                                                    AS descuento,
       v.impuesto                                                     AS impuesto,
       NVL(d.subtotal_detalle, 0) - v.descuento + v.impuesto          AS total_calculado,
       v.total                                                        AS total_guardado,
       v.total - (NVL(d.subtotal_detalle, 0) - v.descuento + v.impuesto) AS diferencia
  FROM ventas v
  LEFT JOIN (SELECT venta_id, SUM(subtotal) AS subtotal_detalle
               FROM detalle_ventas GROUP BY venta_id) d ON d.venta_id = v.id
UNION ALL
SELECT 'cotizacion', c.id, c.numero, c.estado,
       NVL(d.subtotal_detalle, 0), c.descuento, c.impuesto,
       NVL(d.subtotal_detalle, 0) - c.descuento + c.impuesto,
       c.total,
       c.total - (NVL(d.subtotal_detalle, 0) - c.descuento + c.impuesto)
  FROM cotizaciones c
  LEFT JOIN (SELECT cotizacion_id, SUM(subtotal) AS subtotal_detalle
               FROM detalle_cotizaciones GROUP BY cotizacion_id) d ON d.cotizacion_id = c.id
UNION ALL
SELECT 'pedido', p.id, p.numero, p.estado,
       NVL(d.subtotal_detalle, 0), 0, 0,
       NVL(d.subtotal_detalle, 0),
       p.total,
       p.total - NVL(d.subtotal_detalle, 0)
  FROM pedidos p
  LEFT JOIN (SELECT pedido_id, SUM(subtotal) AS subtotal_detalle
               FROM pedido_detalle GROUP BY pedido_id) d ON d.pedido_id = p.id;

PROMPT Vistas creadas correctamente.
