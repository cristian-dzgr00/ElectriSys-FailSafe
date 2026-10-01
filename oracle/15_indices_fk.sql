-- ============================================================
-- ElectriSys — Índices sobre las columnas de claves foráneas
-- 15. Ejecutar conectado como ELECTRISYS, después de 14.
--
-- Oracle crea índice automático para PRIMARY KEY y UNIQUE, pero NO para
-- las columnas de una FOREIGN KEY. Sin ese índice:
--   1. Los JOIN hijo->padre (ventas por vendedor, detalle por repuesto)
--      recorren la tabla hija completa.
--   2. Borrar o actualizar la PK del padre obliga a Oracle a bloquear la
--      tabla hija ENTERA mientras verifica que no queden filas que la
--      referencien (bloqueo TM en modo compartido): una anulación o una
--      depuración de catálogo frena todas las ventas en curso.
--
-- Se encontraron con esta consulta (FK cuya columna no encabeza ningún
-- índice); después de este script debe devolver CERO filas:
--   SELECT c.table_name, cc.column_name
--     FROM user_constraints c
--     JOIN user_cons_columns cc ON cc.constraint_name = c.constraint_name
--    WHERE c.constraint_type = 'R'
--      AND NOT EXISTS (SELECT 1 FROM user_ind_columns ic
--                       WHERE ic.table_name = c.table_name
--                         AND ic.column_name = cc.column_name
--                         AND ic.column_position = cc.position);
--
-- detalle_ventas(venta_id) y detalle_cotizaciones no aparecen todas: el
-- índice compuesto idx_detven_venta_repuesto (03_indices.sql) ya cubre
-- venta_id por ser su primera columna, pero NO repuesto_id (segunda).
--
-- Re-ejecutable: si un índice ya existe (ORA-00955) o la columna ya está
-- indexada con otro nombre (ORA-01408), se informa y se sigue.
-- ============================================================
SET SERVEROUTPUT ON

DECLARE
    TYPE t_indices IS TABLE OF VARCHAR2(200);
    v_indices t_indices := t_indices(
        'idx_cotiz_cliente      ON cotizaciones(cliente_id)',
        'idx_cotiz_usuario      ON cotizaciones(usuario_id)',
        'idx_detcot_cotizacion  ON detalle_cotizaciones(cotizacion_id)',
        'idx_detcot_repuesto    ON detalle_cotizaciones(repuesto_id)',
        'idx_detven_repuesto    ON detalle_ventas(repuesto_id)',
        'idx_pedidos_usuario    ON pedidos(usuario_id)',
        'idx_peddet_repuesto    ON pedido_detalle(repuesto_id)',
        'idx_repuestos_proveedor ON repuestos(proveedor_id)',
        'idx_repuestos_categoria ON repuestos(categoria_id)',
        'idx_usuarios_rol       ON usuarios(rol_id)',
        'idx_ventas_usuario     ON ventas(usuario_id)'
    );
BEGIN
    FOR i IN 1 .. v_indices.COUNT LOOP
        BEGIN
            EXECUTE IMMEDIATE 'CREATE INDEX ' || v_indices(i);
            DBMS_OUTPUT.PUT_LINE('Creado:    ' || v_indices(i));
        EXCEPTION
            WHEN OTHERS THEN
                IF SQLCODE IN (-955, -1408) THEN
                    DBMS_OUTPUT.PUT_LINE('Ya existia: ' || v_indices(i));
                ELSE
                    RAISE;
                END IF;
        END;
    END LOOP;
END;
/

-- audit_log.usuario_id NO lleva FK a usuarios (y por eso tampoco aparece
-- arriba): el log de auditoría debe sobrevivir a cualquier cambio sobre
-- la tabla de usuarios. Ya tiene su índice idx_audit_usuario (03_indices).

PROMPT Indices de claves foraneas listos.
