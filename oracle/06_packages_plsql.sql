-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 06. PL/SQL: tipos, secuencia y packages de negocio
-- Ejecutar conectado como ELECTRISYS.
-- ============================================================

-- ── Tipo objeto para pasar líneas de venta a PKG_VENTAS.REGISTRAR_VENTA ──
CREATE OR REPLACE TYPE t_item_venta AS OBJECT (
    repuesto_id NUMBER,
    cantidad    NUMBER,
    precio_unit NUMBER,
    descuento   NUMBER
);
/

CREATE OR REPLACE TYPE t_items_venta AS TABLE OF t_item_venta;
/

-- ── Secuencia para el consecutivo human-readable de venta (VT-2026-000123) ──
CREATE SEQUENCE seq_numero_venta START WITH 1 INCREMENT BY 1;

-- ============================================================
-- PKG_VENTAS — lógica de negocio equivalente a VentaModel.php,
-- pero garantizada a nivel de base de datos (funciona igual si la
-- llama el backend PHP, un script batch, o alguien desde SQL Developer).
-- ============================================================
CREATE OR REPLACE PACKAGE pkg_ventas AS

    -- Genera el consecutivo con formato VT-<año>-<secuencia con ceros>
    FUNCTION fn_generar_numero_venta RETURN VARCHAR2;

    -- Registra una venta completa (cabecera + detalle) en una sola
    -- transacción. El descuento de stock lo hace automáticamente
    -- trg_detven_descuenta_stock al insertar cada línea; si algún
    -- ítem no tiene stock suficiente, toda la venta se revierte.
    FUNCTION registrar_venta(
        p_cliente_id  IN ventas.cliente_id%TYPE,
        p_usuario_id  IN ventas.usuario_id%TYPE,
        p_items       IN t_items_venta,
        p_metodo_pago IN ventas.metodo_pago%TYPE DEFAULT 'efectivo',
        p_impuesto    IN NUMBER DEFAULT 0
    ) RETURN ventas.id%TYPE;

    -- Anula una venta. trg_ventas_anulada_restaura_stock repone el
    -- inventario automáticamente al detectar el cambio de estado.
    PROCEDURE anular_venta(p_venta_id IN ventas.id%TYPE);

END pkg_ventas;
/

CREATE OR REPLACE PACKAGE BODY pkg_ventas AS

    FUNCTION fn_generar_numero_venta RETURN VARCHAR2 IS
    BEGIN
        RETURN 'VT-' || TO_CHAR(SYSDATE, 'YYYY') || '-' ||
               LPAD(seq_numero_venta.NEXTVAL, 6, '0');
    END fn_generar_numero_venta;

    FUNCTION registrar_venta(
        p_cliente_id  IN ventas.cliente_id%TYPE,
        p_usuario_id  IN ventas.usuario_id%TYPE,
        p_items       IN t_items_venta,
        p_metodo_pago IN ventas.metodo_pago%TYPE DEFAULT 'efectivo',
        p_impuesto    IN NUMBER DEFAULT 0
    ) RETURN ventas.id%TYPE
    IS
        v_venta_id  ventas.id%TYPE;
        v_numero    ventas.numero%TYPE;
        v_subtotal  NUMBER := 0;
        v_descuento NUMBER := 0;
        v_linea_sub NUMBER;
    BEGIN
        IF p_items IS NULL OR p_items.COUNT = 0 THEN
            RAISE_APPLICATION_ERROR(-20001, 'Una venta debe tener al menos un ítem.');
        END IF;

        FOR i IN 1 .. p_items.COUNT LOOP
            v_linea_sub := (p_items(i).cantidad * p_items(i).precio_unit) - p_items(i).descuento;
            v_subtotal  := v_subtotal + v_linea_sub;
            v_descuento := v_descuento + p_items(i).descuento;
        END LOOP;

        v_numero := fn_generar_numero_venta();

        INSERT INTO ventas (numero, cliente_id, usuario_id, subtotal, descuento, impuesto, total, metodo_pago)
        VALUES (v_numero, p_cliente_id, p_usuario_id, v_subtotal, v_descuento, p_impuesto,
                v_subtotal + p_impuesto, p_metodo_pago)
        RETURNING id INTO v_venta_id;

        FOR i IN 1 .. p_items.COUNT LOOP
            INSERT INTO detalle_ventas (venta_id, repuesto_id, cantidad, precio_unit, descuento, subtotal)
            VALUES (v_venta_id, p_items(i).repuesto_id, p_items(i).cantidad, p_items(i).precio_unit,
                    p_items(i).descuento, (p_items(i).cantidad * p_items(i).precio_unit) - p_items(i).descuento);
        END LOOP;

        RETURN v_venta_id;
    EXCEPTION
        WHEN OTHERS THEN
            ROLLBACK;
            RAISE;
    END registrar_venta;

    PROCEDURE anular_venta(p_venta_id IN ventas.id%TYPE) IS
        v_estado ventas.estado%TYPE;
    BEGIN
        SELECT estado INTO v_estado FROM ventas WHERE id = p_venta_id FOR UPDATE;

        IF v_estado = 'anulada' THEN
            RAISE_APPLICATION_ERROR(-20002, 'La venta ' || p_venta_id || ' ya estaba anulada.');
        END IF;

        UPDATE ventas SET estado = 'anulada' WHERE id = p_venta_id;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20003, 'No existe la venta ' || p_venta_id || '.');
    END anular_venta;

END pkg_ventas;
/

-- ============================================================
-- PKG_REPORTES — consultas gerenciales reutilizables (dueño/admin)
-- ============================================================
CREATE OR REPLACE PACKAGE pkg_reportes AS

    -- Total vendido por un vendedor en un rango de fechas (ventas no anuladas)
    FUNCTION total_vendido(
        p_usuario_id IN usuarios.id%TYPE,
        p_desde      IN DATE DEFAULT DATE '1900-01-01',
        p_hasta      IN DATE DEFAULT SYSDATE
    ) RETURN NUMBER;

    -- Valor total del inventario a precio de compra (para control financiero)
    FUNCTION stock_valorizado RETURN NUMBER;

    -- Top N repuestos más vendidos (por unidades), vía REF CURSOR
    PROCEDURE ranking_repuestos_mas_vendidos(
        p_top    IN  NUMBER,
        p_cursor OUT SYS_REFCURSOR
    );

END pkg_reportes;
/

CREATE OR REPLACE PACKAGE BODY pkg_reportes AS

    FUNCTION total_vendido(
        p_usuario_id IN usuarios.id%TYPE,
        p_desde      IN DATE DEFAULT DATE '1900-01-01',
        p_hasta      IN DATE DEFAULT SYSDATE
    ) RETURN NUMBER IS
        v_total NUMBER;
    BEGIN
        SELECT NVL(SUM(total), 0) INTO v_total
          FROM ventas
         WHERE usuario_id = p_usuario_id
           AND estado != 'anulada'
           AND creado_en BETWEEN p_desde AND p_hasta;
        RETURN v_total;
    END total_vendido;

    FUNCTION stock_valorizado RETURN NUMBER IS
        v_valor NUMBER;
    BEGIN
        SELECT NVL(SUM(stock * precio_compra), 0) INTO v_valor FROM repuestos WHERE activo = TRUE;
        RETURN v_valor;
    END stock_valorizado;

    PROCEDURE ranking_repuestos_mas_vendidos(
        p_top    IN  NUMBER,
        p_cursor OUT SYS_REFCURSOR
    ) IS
    BEGIN
        OPEN p_cursor FOR
            SELECT r.codigo, r.nombre, SUM(dv.cantidad) AS unidades_vendidas
              FROM detalle_ventas dv
              JOIN ventas v      ON v.id = dv.venta_id AND v.estado != 'anulada'
              JOIN repuestos r   ON r.id = dv.repuesto_id
             GROUP BY r.codigo, r.nombre
             ORDER BY unidades_vendidas DESC
            FETCH FIRST p_top ROWS ONLY;
    END ranking_repuestos_mas_vendidos;

END pkg_reportes;
/

PROMPT Packages PL/SQL creados correctamente.
