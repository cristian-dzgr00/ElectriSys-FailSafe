-- ============================================================
-- ElectriSys — Sprint 3 · tarjeta 3.12
-- Planes de ejecución con volumen grande (>= 100 000 ventas):
-- compara FULL SCAN contra el plan que elige el optimizador con índices.
-- Ejecutar como ELECTRISYS. Genera evidencia_100k.txt y al final borra el
-- volumen sintético (prefijo VOL-). (probado en Oracle 23ai Free)
-- ============================================================
SET SERVEROUTPUT ON SIZE UNLIMITED
SET LINESIZE 200 PAGESIZE 200 FEEDBACK ON TIMING ON
SPOOL evidencia_100k.txt

PROMPT === 1. Generando 100 000 ventas sintéticas (trg_detven_descuenta_stock desactivado) ===
ALTER TRIGGER trg_detven_descuenta_stock DISABLE;

INSERT INTO ventas (numero, cliente_id, usuario_id, subtotal, total, creado_en)
SELECT 'VOL-' || LPAD(n, 7, '0'),
       (SELECT id FROM (SELECT id FROM clientes ORDER BY DBMS_RANDOM.VALUE) WHERE ROWNUM = 1),
       (SELECT MIN(id) FROM usuarios),
       50000, 50000,
       SYSTIMESTAMP - DBMS_RANDOM.VALUE(0, 730)
  FROM (SELECT LEVEL AS n FROM dual CONNECT BY LEVEL <= 100000);

INSERT INTO detalle_ventas (venta_id, repuesto_id, cantidad, precio_unit, subtotal)
SELECT v.id, (SELECT MIN(id) FROM repuestos), 1, 50000, 50000
  FROM ventas v WHERE v.numero LIKE 'VOL-%';
COMMIT;

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'VENTAS', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'DETALLE_VENTAS', cascade => TRUE);
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'POSIBLES_ERRORES', cascade => TRUE);
END;
/
SELECT COUNT(*) AS total_ventas FROM ventas;

PROMPT === 2. Consulta A: ventas de un cliente ===
PROMPT --- SIN índice (FULL)
EXPLAIN PLAN FOR SELECT /*+ FULL(v) */ * FROM ventas v WHERE cliente_id = 5;
SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);
PROMPT --- CON índice idx_ventas_cliente
EXPLAIN PLAN FOR SELECT /*+ INDEX(v idx_ventas_cliente) */ * FROM ventas v WHERE cliente_id = 5;
SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);

PROMPT === 3. Consulta B: ventas de los últimos 7 días ===
PROMPT --- SIN índice
EXPLAIN PLAN FOR SELECT /*+ FULL(v) */ * FROM ventas v WHERE creado_en >= SYSTIMESTAMP - 7;
SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);
PROMPT --- CON índice idx_ventas_fecha
EXPLAIN PLAN FOR SELECT /*+ INDEX(v idx_ventas_fecha) */ * FROM ventas v WHERE creado_en >= SYSTIMESTAMP - 7;
SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);

PROMPT === 4. Consulta C: detalle de una venta ===
PROMPT --- SIN índice
EXPLAIN PLAN FOR SELECT /*+ FULL(d) */ * FROM detalle_ventas d WHERE venta_id = 100;
SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);
PROMPT --- CON índice idx_detven_venta_repuesto
EXPLAIN PLAN FOR SELECT /*+ INDEX(d idx_detven_venta_repuesto) */ * FROM detalle_ventas d WHERE venta_id = 100;
SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);

PROMPT === 5. Consulta D: búsqueda en posibles_errores (el índice único cubre tipo,error) ===
PROMPT --- SIN índice
EXPLAIN PLAN FOR SELECT /*+ FULL(p) */ correcto FROM posibles_errores p WHERE tipo = 'marca' AND error = 'toyta';
SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);
PROMPT --- CON índice
EXPLAIN PLAN FOR SELECT correcto FROM posibles_errores p WHERE tipo = 'marca' AND error = 'toyta';
SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);

PROMPT === 6. Tiempo real de la consulta A (Autotrace no requerido) ===
VARIABLE t0 NUMBER
EXEC :t0 := DBMS_UTILITY.GET_TIME
SELECT /*+ FULL(v) */ COUNT(*) FROM ventas v WHERE cliente_id = 5;
EXEC DBMS_OUTPUT.PUT_LINE('Centésimas con FULL: ' || (DBMS_UTILITY.GET_TIME - :t0))
EXEC :t0 := DBMS_UTILITY.GET_TIME
SELECT /*+ INDEX(v idx_ventas_cliente) */ COUNT(*) FROM ventas v WHERE cliente_id = 5;
EXEC DBMS_OUTPUT.PUT_LINE('Centésimas con índice: ' || (DBMS_UTILITY.GET_TIME - :t0))

PROMPT === 7. Limpieza del volumen sintético ===
DELETE FROM detalle_ventas WHERE venta_id IN (SELECT id FROM ventas WHERE numero LIKE 'VOL-%');
DELETE FROM ventas WHERE numero LIKE 'VOL-%';
COMMIT;
ALTER TRIGGER trg_detven_descuenta_stock ENABLE;
SPOOL OFF
