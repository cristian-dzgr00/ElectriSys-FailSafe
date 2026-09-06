-- ============================================================
-- ElectriSys — Oracle 23ai
-- Genera volumen sintético (NO es parte del seed real) para poder
-- observar diferencias reales en el optimizador de consultas.
-- Con solo 12 clientes / 23 repuestos / 0 ventas, el optimizador de
-- Oracle elige FULL TABLE SCAN incluso con índices creados, porque
-- para una tabla tan chica es realmente más barato — un índice solo
-- se justifica quand hay volumen. Este script simula ese volumen.
--
-- Se desactiva trg_detven_descuenta_stock durante la carga: es un
-- trigger de negocio que descontaría stock real por cada línea
-- sintética y violaría el CHECK ck_repuestos_stock casi de inmediato.
-- Desactivar triggers durante cargas masivas es práctica estándar de
-- Oracle (igual se hace antes de un import con Data Pump).
-- ============================================================

ALTER TRIGGER trg_detven_descuenta_stock DISABLE;

DECLARE
    v_venta_id     ventas.id%TYPE;
    v_cliente_id   clientes.id%TYPE;
    v_usuario_id   usuarios.id%TYPE;
    v_repuesto_id  repuestos.id%TYPE;
    v_precio       NUMBER;
    v_cantidad     NUMBER;
    v_num_lineas   NUMBER;
    v_subtotal     NUMBER;
    TYPE t_ids IS TABLE OF NUMBER;
    v_clientes  t_ids;
    v_usuarios  t_ids;
    v_repuestos t_ids;
BEGIN
    SELECT id BULK COLLECT INTO v_clientes  FROM clientes;
    SELECT id BULK COLLECT INTO v_usuarios  FROM usuarios;
    SELECT id BULK COLLECT INTO v_repuestos FROM repuestos;

    FOR i IN 1 .. 8000 LOOP
        v_cliente_id := v_clientes(TRUNC(DBMS_RANDOM.VALUE(1, v_clientes.COUNT + 1)));
        v_usuario_id := v_usuarios(TRUNC(DBMS_RANDOM.VALUE(1, v_usuarios.COUNT + 1)));
        v_subtotal   := 0;

        INSERT INTO ventas (numero, cliente_id, usuario_id, subtotal, total, creado_en)
        VALUES ('VOL-' || LPAD(i, 7, '0'), v_cliente_id, v_usuario_id, 0, 0,
                SYSTIMESTAMP - DBMS_RANDOM.VALUE(0, 730))
        RETURNING id INTO v_venta_id;

        v_num_lineas := TRUNC(DBMS_RANDOM.VALUE(1, 4)); -- 1 a 3 líneas por venta

        FOR j IN 1 .. v_num_lineas LOOP
            v_repuesto_id := v_repuestos(TRUNC(DBMS_RANDOM.VALUE(1, v_repuestos.COUNT + 1)));
            v_cantidad    := TRUNC(DBMS_RANDOM.VALUE(1, 4));
            v_precio      := TRUNC(DBMS_RANDOM.VALUE(10000, 400000));

            INSERT INTO detalle_ventas (venta_id, repuesto_id, cantidad, precio_unit, subtotal)
            VALUES (v_venta_id, v_repuesto_id, v_cantidad, v_precio, v_cantidad * v_precio);

            v_subtotal := v_subtotal + (v_cantidad * v_precio);
        END LOOP;

        UPDATE ventas SET subtotal = v_subtotal, total = v_subtotal WHERE id = v_venta_id;

        IF MOD(i, 1000) = 0 THEN
            COMMIT;
        END IF;
    END LOOP;
    COMMIT;
END;
/

ALTER TRIGGER trg_detven_descuenta_stock ENABLE;

EXEC DBMS_STATS.GATHER_TABLE_STATS('ELECTRISYS', 'VENTAS', cascade => TRUE);
EXEC DBMS_STATS.GATHER_TABLE_STATS('ELECTRISYS', 'DETALLE_VENTAS', cascade => TRUE);

SELECT COUNT(*) AS total_ventas FROM ventas;
SELECT COUNT(*) AS total_detalle FROM detalle_ventas;

PROMPT Volumen sintetico generado (no forma parte del seed real de la app).
