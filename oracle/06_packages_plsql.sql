-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 06. PL/SQL: secuencia y packages de negocio
-- Ejecutar conectado como ELECTRISYS.
--
-- Nota sobre esta versión: registrar_venta() originalmente recibía la
-- venta completa (cabecera + todas las líneas) en un solo llamado, vía un
-- parámetro de tipo colección (t_items_venta, TABLE OF OBJECT). Se separó
-- en registrar_venta() (solo cabecera) + agregar_item_venta() (una línea
-- por llamado) porque bindear tipos objeto/colección de Oracle desde PHP
-- es la parte más fragil y peor soportada de la integración PHP<->Oracle
-- (poco documentada, casi nadie la usa en producción real) — con parámetros
-- escalares simples, el backend PHP llama a agregar_item_venta() en un
-- loop, un ítem por vez, sin ese riesgo. El trigger de stock
-- (trg_detven_descuenta_stock) sigue funcionando igual: dispara por cada
-- INSERT en detalle_ventas, sin importar si vino de un loop o de una sola
-- sentencia.
-- ============================================================

-- ── Secuencia para el consecutivo human-readable de venta (VT-2026-000123) ──
-- CREATE SEQUENCE no soporta "OR REPLACE"/"IF NOT EXISTS" — se envuelve en
-- PL/SQL para que el script sea repetible (ej. al reconstruir el
-- contenedor de desarrollo sin volumen limpio).
BEGIN
    EXECUTE IMMEDIATE 'CREATE SEQUENCE seq_numero_venta START WITH 1 INCREMENT BY 1';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN -- ORA-00955: ya existe
            RAISE;
        END IF;
END;
/

-- ── Fecha local del negocio ──────────────────────────────────────
-- Las columnas TIMESTAMP se llenan con SYSTIMESTAMP y el contenedor de
-- Oracle corre en UTC, pero el negocio (y la UI) razonan en hora de
-- Colombia. Sin convertir, una venta de las 11:42 p.m. del 15 cae en el
-- 16 al agrupar por día: aparecía en "Ingresos hoy" y faltaba en el
-- gráfico del día 15. Toda agrupación por día/mes debe pasar por aquí;
-- es el único lugar donde se declara la zona horaria del negocio.
CREATE OR REPLACE FUNCTION fn_fecha_local(p_ts IN TIMESTAMP)
    RETURN DATE DETERMINISTIC IS
BEGIN
    RETURN CAST(FROM_TZ(p_ts, 'UTC') AT TIME ZONE 'America/Bogota' AS DATE);
END;
/

-- Hoy según la hora local del negocio (no la del servidor).
CREATE OR REPLACE FUNCTION fn_hoy_local RETURN DATE IS
BEGIN
    RETURN TRUNC(CAST(SYSTIMESTAMP AT TIME ZONE 'America/Bogota' AS DATE));
END;
/

-- ============================================================
-- PKG_VENTAS — lógica de negocio equivalente a VentaModel.php,
-- pero garantizada a nivel de base de datos (funciona igual si la
-- llama el backend PHP, un script batch, o alguien desde SQL Developer).
-- El descuento/restauración de stock lo hacen los triggers
-- (trg_detven_descuenta_stock, trg_ventas_anulada_restaura_stock) — este
-- package NUNCA toca repuestos.stock directamente, así evita el riesgo de
-- descontar/restaurar dos veces si además hubiera lógica manual en PHP.
-- ============================================================
CREATE OR REPLACE PACKAGE pkg_ventas AS

    -- Genera el consecutivo con formato VT-<año>-<secuencia con ceros>
    FUNCTION fn_generar_numero_venta RETURN VARCHAR2;

    -- Crea la cabecera de una venta. subtotal/descuento/impuesto/total
    -- llegan YA CALCULADOS por PHP (GestorVentas aplica la Strategy de
    -- descuento — PrecioEstandarStrategy/DescuentoVolumenStrategy/
    -- ExentoIvaStrategy — antes de llamar acá). Oracle no reimplementa esa
    -- regla de negocio: solo la persiste. Cada línea se agrega después
    -- con agregar_item_venta().
    FUNCTION registrar_venta(
        p_cliente_id  IN ventas.cliente_id%TYPE,
        p_usuario_id  IN ventas.usuario_id%TYPE,
        p_subtotal    IN ventas.subtotal%TYPE,
        p_descuento   IN ventas.descuento%TYPE DEFAULT 0,
        p_impuesto    IN ventas.impuesto%TYPE DEFAULT 0,
        p_total       IN ventas.total%TYPE,
        p_metodo_pago IN ventas.metodo_pago%TYPE DEFAULT 'efectivo',
        p_notas       IN ventas.notas%TYPE DEFAULT NULL
    ) RETURN ventas.id%TYPE;

    -- Agrega una línea a una venta ya creada. Solo descuenta stock (vía
    -- trigger) e inserta el detalle — NO toca subtotal/impuesto/total de
    -- la cabecera, que ya llegaron correctos desde registrar_venta().
    PROCEDURE agregar_item_venta(
        p_venta_id    IN detalle_ventas.venta_id%TYPE,
        p_repuesto_id IN detalle_ventas.repuesto_id%TYPE,
        p_cantidad    IN detalle_ventas.cantidad%TYPE,
        p_precio_unit IN detalle_ventas.precio_unit%TYPE,
        p_descuento   IN detalle_ventas.descuento%TYPE DEFAULT 0
    );

    -- Anula una venta. trg_ventas_anulada_restaura_stock repone el
    -- inventario automáticamente al detectar el cambio de estado.
    PROCEDURE anular_venta(p_venta_id IN ventas.id%TYPE);

    -- Listado paginado + filtros, equivalente a VentaModel::listar().
    -- El cursor incluye la columna total_filas (COUNT(*) OVER()) para que
    -- el backend no necesite una segunda consulta para el total.
    -- p_desde/p_hasta como texto 'YYYY-MM-DD' (no DATE): bindear un DATE
    -- desde PHP vía oci8 depende del NLS_DATE_FORMAT de la sesión, que no
    -- es 'YYYY-MM-DD' por defecto — más simple y predecible convertir con
    -- TO_DATE() adentro del package, con formato explícito.
    FUNCTION listar_ventas(
        p_estado IN VARCHAR2 DEFAULT NULL,
        p_desde  IN VARCHAR2 DEFAULT NULL,
        p_hasta  IN VARCHAR2 DEFAULT NULL,
        p_q      IN VARCHAR2 DEFAULT NULL,
        p_limit  IN NUMBER   DEFAULT 15,
        p_offset IN NUMBER   DEFAULT 0
    ) RETURN SYS_REFCURSOR;

    -- Cabecera + líneas de una venta, equivalente a VentaModel::buscarPorId().
    PROCEDURE buscar_venta_por_id(
        p_id       IN  ventas.id%TYPE,
        p_cabecera OUT SYS_REFCURSOR,
        p_detalle  OUT SYS_REFCURSOR
    );

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
        p_subtotal    IN ventas.subtotal%TYPE,
        p_descuento   IN ventas.descuento%TYPE DEFAULT 0,
        p_impuesto    IN ventas.impuesto%TYPE DEFAULT 0,
        p_total       IN ventas.total%TYPE,
        p_metodo_pago IN ventas.metodo_pago%TYPE DEFAULT 'efectivo',
        p_notas       IN ventas.notas%TYPE DEFAULT NULL
    ) RETURN ventas.id%TYPE
    IS
        v_venta_id ventas.id%TYPE;
        v_numero   ventas.numero%TYPE;
    BEGIN
        v_numero := fn_generar_numero_venta();

        INSERT INTO ventas (numero, cliente_id, usuario_id, subtotal, descuento, impuesto, total, metodo_pago, notas)
        VALUES (v_numero, p_cliente_id, p_usuario_id, p_subtotal, p_descuento, p_impuesto, p_total, p_metodo_pago, p_notas)
        RETURNING id INTO v_venta_id;

        RETURN v_venta_id;
    EXCEPTION
        WHEN OTHERS THEN
            ROLLBACK;
            RAISE;
    END registrar_venta;

    PROCEDURE agregar_item_venta(
        p_venta_id    IN detalle_ventas.venta_id%TYPE,
        p_repuesto_id IN detalle_ventas.repuesto_id%TYPE,
        p_cantidad    IN detalle_ventas.cantidad%TYPE,
        p_precio_unit IN detalle_ventas.precio_unit%TYPE,
        p_descuento   IN detalle_ventas.descuento%TYPE DEFAULT 0
    ) IS
        v_subtotal_linea NUMBER;
    BEGIN
        v_subtotal_linea := (p_cantidad * p_precio_unit) - p_descuento;

        -- trg_detven_descuenta_stock descuenta el stock automáticamente;
        -- si no alcanza, ck_repuestos_stock revierte toda la transacción
        -- (ORA-02290) y ninguna línea queda a medias.
        INSERT INTO detalle_ventas (venta_id, repuesto_id, cantidad, precio_unit, descuento, subtotal)
        VALUES (p_venta_id, p_repuesto_id, p_cantidad, p_precio_unit, p_descuento, v_subtotal_linea);
    EXCEPTION
        WHEN OTHERS THEN
            ROLLBACK;
            RAISE;
    END agregar_item_venta;

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

    FUNCTION listar_ventas(
        p_estado IN VARCHAR2 DEFAULT NULL,
        p_desde  IN VARCHAR2 DEFAULT NULL,
        p_hasta  IN VARCHAR2 DEFAULT NULL,
        p_q      IN VARCHAR2 DEFAULT NULL,
        p_limit  IN NUMBER   DEFAULT 15,
        p_offset IN NUMBER   DEFAULT 0
    ) RETURN SYS_REFCURSOR IS
        v_cursor SYS_REFCURSOR;
    BEGIN
        OPEN v_cursor FOR
            SELECT v.*, c.nombre AS cliente_nombre, u.nombre AS vendedor_nombre,
                   COUNT(*) OVER() AS total_filas
              FROM ventas v
              LEFT JOIN clientes c ON v.cliente_id = c.id
              JOIN usuarios u      ON v.usuario_id = u.id
             WHERE (p_estado IS NULL OR v.estado = p_estado)
               AND (p_desde  IS NULL OR fn_fecha_local(v.creado_en) >= TO_DATE(p_desde, 'YYYY-MM-DD'))
               AND (p_hasta  IS NULL OR fn_fecha_local(v.creado_en) <  TO_DATE(p_hasta, 'YYYY-MM-DD') + 1)
               AND (p_q      IS NULL OR v.numero LIKE '%' || p_q || '%'
                                      OR c.nombre LIKE '%' || p_q || '%')
             ORDER BY v.creado_en DESC
            OFFSET p_offset ROWS FETCH NEXT p_limit ROWS ONLY;
        RETURN v_cursor;
    END listar_ventas;

    PROCEDURE buscar_venta_por_id(
        p_id       IN  ventas.id%TYPE,
        p_cabecera OUT SYS_REFCURSOR,
        p_detalle  OUT SYS_REFCURSOR
    ) IS
    BEGIN
        OPEN p_cabecera FOR
            SELECT v.*, c.nombre AS cliente_nombre, u.nombre AS vendedor_nombre
              FROM ventas v
              LEFT JOIN clientes c ON v.cliente_id = c.id
              JOIN usuarios u      ON v.usuario_id = u.id
             WHERE v.id = p_id;

        OPEN p_detalle FOR
            SELECT dv.*, r.nombre AS producto_nombre, r.codigo
              FROM detalle_ventas dv
              JOIN repuestos r ON dv.repuesto_id = r.id
             WHERE dv.venta_id = p_id;
    END buscar_venta_por_id;

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

    -- Resumen global del día (todos los vendedores) — equivalente a
    -- VentaModel::resumenHoy(). A diferencia de total_vendido(), no
    -- filtra por usuario.
    PROCEDURE resumen_hoy(p_cursor OUT SYS_REFCURSOR);

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
        SELECT NVL(SUM(stock * precio_compra), 0) INTO v_valor FROM repuestos WHERE activo = 1;
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

    PROCEDURE resumen_hoy(p_cursor OUT SYS_REFCURSOR) IS
    BEGIN
        OPEN p_cursor FOR
            SELECT COUNT(*)         AS total_ventas,
                   NVL(SUM(total),0) AS ingresos,
                   NVL(AVG(total),0) AS ticket_promedio
              FROM ventas
             WHERE TRUNC(fn_fecha_local(creado_en)) = fn_hoy_local()
               AND estado = 'completada';
    END resumen_hoy;

END pkg_reportes;
/

PROMPT Packages PL/SQL creados correctamente.
