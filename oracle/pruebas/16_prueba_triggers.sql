-- ============================================================
-- ElectriSys — Sprint 3 · tarjeta 3.13
-- Prueba de triggers: venta baja stock, anulación lo devuelve,
-- stock negativo es rechazado por ck_repuestos_stock.
-- Ejecutar como ELECTRISYS:  sqlplus electrisys/CLAVE@//localhost:1521/freepdb1 @16_prueba_triggers.sql
-- No deja datos: termina con ROLLBACK.   (SIN PROBAR en Oracle real)
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
    v_venta := pkg_ventas.registrar_venta(v_cli, v_usr, 3000, 0, 0, 3000);
    INSERT INTO detalle_ventas (venta_id, repuesto_id, cantidad, precio_unit, subtotal)
    VALUES (v_venta, v_rep, 3, 1000, 3000);
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
        v_venta2 := pkg_ventas.registrar_venta(v_cli, v_usr, 1, 0, 0, 1);
        INSERT INTO detalle_ventas (venta_id, repuesto_id, cantidad, precio_unit, subtotal)
        VALUES (v_venta2, v_rep, v_stock0 + 1, 1, v_stock0 + 1);
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

    ROLLBACK TO inicio;
    ROLLBACK;
    DBMS_OUTPUT.PUT_LINE(CASE WHEN v_fallos = 0 THEN 'RESULTADO: TODAS LAS PRUEBAS PASARON'
                              ELSE 'RESULTADO: ' || v_fallos || ' PRUEBA(S) FALLARON' END);
END;
/
SPOOL OFF
