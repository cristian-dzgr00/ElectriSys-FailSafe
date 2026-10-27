-- ============================================================
-- ElectriSys — Sprint 3 · tarjeta 3.13
-- Prueba de triggers: venta baja stock, anulación lo devuelve,
-- stock negativo es rechazado por ck_repuestos_stock.
-- Ejecutar como ELECTRISYS:  sqlplus electrisys/CLAVE@//localhost:1521/freepdb1 @16_prueba_triggers.sql
-- No deja datos: termina con ROLLBACK.   (probado en Oracle 23ai Free)
-- ============================================================
SET SERVEROUTPUT ON SIZE UNLIMITED
SET FEEDBACK OFF
SPOOL evidencia_triggers.txt

DECLARE
    v_rep     repuestos.id%TYPE;
    v_stock0  NUMBER;
    v_stock1  NUMBER;
    v_stock2  NUMBER;
    v_cli     clientes.id%TYPE;
    v_usr     usuarios.id%TYPE;
    v_venta   ventas.id%TYPE;
    v_venta3  ventas.id%TYPE;
    v_sub     NUMBER;
    v_desc    NUMBER;
    v_imp     NUMBER;
    v_tot     NUMBER;
    v_fallos  PLS_INTEGER := 0;

    PROCEDURE chequeo(p_nombre VARCHAR2, p_ok BOOLEAN, p_detalle VARCHAR2) IS
    BEGIN
        IF p_ok THEN
            DBMS_OUTPUT.PUT_LINE('PASS  ' || p_nombre || '  (' || p_detalle || ')');
        ELSE
            v_fallos := v_fallos + 1;
            DBMS_OUTPUT.PUT_LINE('FAIL  ' || p_nombre || '  (' || p_detalle || ')');
        END IF;
    END;
BEGIN
    SELECT id INTO v_cli FROM (SELECT id FROM clientes ORDER BY id) WHERE ROWNUM = 1;
    SELECT id INTO v_usr FROM (SELECT id FROM usuarios ORDER BY id) WHERE ROWNUM = 1;
    SELECT id, stock INTO v_rep, v_stock0
      FROM (SELECT id, stock FROM repuestos WHERE stock >= 5 ORDER BY id) WHERE ROWNUM = 1;
    DBMS_OUTPUT.PUT_LINE('Repuesto de prueba id=' || v_rep || ' stock inicial=' || v_stock0);

    SAVEPOINT inicio;

    -- 1) Registrar venta con 3 unidades: el stock debe bajar 3
    v_venta := pkg_ventas.registrar_venta(v_cli, v_usr, 0, 0);
    INSERT INTO detalle_ventas (venta_id, repuesto_id, cantidad, precio_unit)
    VALUES (v_venta, v_rep, 3, 1000);
    SELECT stock INTO v_stock1 FROM repuestos WHERE id = v_rep;
    chequeo('1. La venta descuenta stock', v_stock1 = v_stock0 - 3, v_stock0 || ' -> ' || v_stock1);

    -- 2) Anular la venta: el stock debe volver al valor inicial
    UPDATE ventas SET estado = 'anulada' WHERE id = v_venta;
    SELECT stock INTO v_stock2 FROM repuestos WHERE id = v_rep;
    chequeo('2. La anulación devuelve el stock', v_stock2 = v_stock0, v_stock1 || ' -> ' || v_stock2);

    -- 3) Stock negativo: debe fallar con ORA-02290 (ck_repuestos_stock)
    DECLARE
        v_venta2 ventas.id%TYPE;
    BEGIN
        v_venta2 := pkg_ventas.registrar_venta(v_cli, v_usr, 0, 0);
        INSERT INTO detalle_ventas (venta_id, repuesto_id, cantidad, precio_unit)
        VALUES (v_venta2, v_rep, v_stock0 + 1, 1);
        chequeo('3. Stock negativo rechazado', FALSE, 'no lanzó error');
    EXCEPTION
        WHEN OTHERS THEN
            chequeo('3. Stock negativo rechazado', SQLCODE = -2290, SQLERRM);
    END;

    -- 4) Anular dos veces: pkg_ventas lo rechaza con ORA-20002
    BEGIN
        pkg_ventas.anular_venta(v_venta);
        chequeo('4. No se anula dos veces', FALSE, 'no lanzó error');
    EXCEPTION
        WHEN OTHERS THEN
            chequeo('4. No se anula dos veces', SQLCODE = -20002, SQLERRM);
    END;

    -- 5) Totales derivados: 3 x 1000 con 100 de descuento en la línea, 10 % de
    --    descuento y 19 % de IVA en la cabecera.
    --    subtotal 2900; descuento 290; impuesto (2900-290)*19% = 495,90; total 3105,90
    v_venta3 := pkg_ventas.registrar_venta(v_cli, v_usr, 10, 19);
    INSERT INTO detalle_ventas (venta_id, repuesto_id, cantidad, precio_unit, descuento)
    VALUES (v_venta3, v_rep, 3, 1000, 100);
    SELECT subtotal, descuento, impuesto, total INTO v_sub, v_desc, v_imp, v_tot
      FROM vw_totales_documento WHERE tipo = 'venta' AND documento_id = v_venta3;
    chequeo('5. vw_totales_documento calcula los montos',
            v_sub = 2900 AND v_desc = 290 AND v_imp = 495.9 AND v_tot = 3105.9,
            'subtotal=' || v_sub || ' descuento=' || v_desc || ' impuesto=' || v_imp || ' total=' || v_tot);

    -- 6) La misma venta no admite el mismo repuesto en dos líneas: ORA-00001 (pk_detalle_ventas)
    BEGIN
        INSERT INTO detalle_ventas (venta_id, repuesto_id, cantidad, precio_unit)
        VALUES (v_venta3, v_rep, 1, 1000);
        chequeo('6. Repuesto repetido en la venta rechazado', FALSE, 'no lanzó error');
    EXCEPTION
        WHEN OTHERS THEN
            chequeo('6. Repuesto repetido en la venta rechazado', SQLCODE = -1, SQLERRM);
    END;

    ROLLBACK TO inicio;
    ROLLBACK;
    DBMS_OUTPUT.PUT_LINE(CASE WHEN v_fallos = 0 THEN 'RESULTADO: TODAS LAS PRUEBAS PASARON'
                              ELSE 'RESULTADO: ' || v_fallos || ' PRUEBA(S) FALLARON' END);
END;
/
SPOOL OFF
