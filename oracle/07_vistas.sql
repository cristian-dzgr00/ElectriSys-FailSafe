-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 07. Vistas (incluye vw_totales_documento)
-- Ejecutar conectado como ELECTRISYS, después de 06 (fn_fecha_local) y de
-- 16_normalizacion_3fn_fase2.sql (esquema 3FN: las cabeceras ya no guardan
-- subtotal/descuento/impuesto/total; salen de vw_totales_documento).
-- ============================================================

-- ── Totales de cada documento calculados desde sus líneas ────────
-- Una fila por documento de ventas, cotizaciones y pedidos:
--   subtotal  = SUMA(cantidad * precio_unit - descuento de la línea)
--   descuento = monto = ROUND(subtotal * descuento_pct / 100, 2)
--   impuesto  = ROUND((subtotal - descuento) * iva_pct / 100, 2)
--   total     = subtotal - descuento + impuesto
-- Los pedidos no llevan descuento ni IVA: van en 0. Un documento sin líneas
-- aparece igual, con ceros (LEFT JOIN).
CREATE OR REPLACE VIEW vw_totales_documento AS
SELECT tipo, documento_id, subtotal, descuento, impuesto,
       subtotal - descuento + impuesto AS total
  FROM (SELECT tipo, documento_id, subtotal, descuento,
               ROUND((subtotal - descuento) * iva_pct / 100, 2) AS impuesto
          FROM (SELECT tipo, documento_id, subtotal, iva_pct,
                       ROUND(subtotal * descuento_pct / 100, 2) AS descuento
                  FROM (SELECT 'venta' AS tipo, v.id AS documento_id,
                               NVL(l.subtotal, 0) AS subtotal,
                               v.descuento_pct, v.iva_pct
                          FROM ventas v
                          LEFT JOIN (SELECT venta_id,
                                            SUM(cantidad * precio_unit - NVL(descuento, 0)) AS subtotal
                                       FROM detalle_ventas GROUP BY venta_id) l
                                 ON l.venta_id = v.id
                        UNION ALL
                        SELECT 'cotizacion', c.id,
                               NVL(l.subtotal, 0),
                               c.descuento_pct, c.iva_pct
                          FROM cotizaciones c
                          LEFT JOIN (SELECT cotizacion_id,
                                            SUM(cantidad * precio_unit - NVL(descuento, 0)) AS subtotal
                                       FROM detalle_cotizaciones GROUP BY cotizacion_id) l
                                 ON l.cotizacion_id = c.id
                        UNION ALL
                        SELECT 'pedido', p.id,
                               NVL(l.subtotal, 0),
                               0, 0
                          FROM pedidos p
                          LEFT JOIN (SELECT pedido_id,
                                            SUM(cantidad * precio_unit) AS subtotal
                                       FROM pedido_detalle GROUP BY pedido_id) l
                                 ON l.pedido_id = p.id)));

-- ── Ventas con nombre de cliente y vendedor (evita repetir el JOIN en cada reporte) ──
CREATE OR REPLACE VIEW vw_ventas_detalle AS
SELECT v.id, v.numero, v.creado_en, v.estado, v.metodo_pago,
       t.subtotal, t.descuento, t.impuesto, t.total,
       c.nombre AS cliente, c.identificacion AS cliente_identificacion,
       u.nombre AS vendedor
  FROM ventas v
  JOIN vw_totales_documento t ON t.tipo = 'venta' AND t.documento_id = v.id
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
       SUM(t.total) AS total_vendido
  FROM ventas v
  JOIN usuarios u ON u.id = v.usuario_id
  JOIN vw_totales_documento t ON t.tipo = 'venta' AND t.documento_id = v.id
 WHERE v.estado != 'anulada'
 GROUP BY u.id, u.nombre, TRUNC(fn_fecha_local(v.creado_en), 'MM');

-- ── Repuestos con su compatibilidad de vehículo (soporte al asistente NLP) ──
-- Ampliada con descripcion/precio_venta/categoria/proveedor: son las
-- columnas que ya devuelve GET /api/repuestos/buscar-compatibles
-- (backend/src/routes/repuestos.php). Marca y modelo salen de vw_vehiculos
-- (3FN: ya no son columnas de VEHICULOS).
CREATE OR REPLACE VIEW vw_repuestos_compatibles AS
SELECT r.id AS repuesto_id, r.codigo, r.nombre AS repuesto, r.descripcion,
       r.stock, r.precio_venta, cat.nombre AS categoria, p.nombre AS proveedor,
       v.marca, v.modelo, v.anio_desde, v.anio_hasta, v.motor, v.combustible
  FROM repuesto_compatibilidad rc
  JOIN repuestos r          ON r.id = rc.repuesto_id
  JOIN vw_vehiculos v       ON v.id = rc.vehiculo_id
  LEFT JOIN categorias cat  ON cat.id = r.categoria_id
  LEFT JOIN proveedores p   ON p.id = r.proveedor_id
 WHERE r.activo = 1;

-- Los packages de 06 dependen de vw_totales_documento: en una carga desde cero
-- 06 corre antes que esta vista y sus cuerpos quedan INVALID; se recompilan aquí.
ALTER PACKAGE pkg_ventas   COMPILE BODY;
ALTER PACKAGE pkg_reportes COMPILE BODY;

PROMPT Vistas creadas correctamente.
