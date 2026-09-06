-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 04. Triggers
-- Ejecutar conectado como ELECTRISYS.
-- ============================================================

-- ── 1. updated_at automático (Oracle no tiene "ON UPDATE CURRENT_TIMESTAMP"
--       declarativo como MySQL; se replica con un trigger BEFORE UPDATE por tabla) ──
CREATE OR REPLACE TRIGGER trg_usuarios_updated_at
    BEFORE UPDATE ON usuarios
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER trg_proveedores_updated_at
    BEFORE UPDATE ON proveedores
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER trg_repuestos_updated_at
    BEFORE UPDATE ON repuestos
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER trg_clientes_updated_at
    BEFORE UPDATE ON clientes
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER trg_cotizaciones_updated_at
    BEFORE UPDATE ON cotizaciones
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/

-- ── 2. Ventas: updated_at + control de versión (optimistic locking) ──
-- Equivalente al trigger ventas_version_bump de MySQL (database/schema.sql).
CREATE OR REPLACE TRIGGER trg_ventas_before_update
    BEFORE UPDATE ON ventas
    FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
    :NEW.version    := :OLD.version + 1;
END;
/

-- ── 3. Descuento de stock automático al registrar el detalle de una venta ──
-- Regla de negocio a nivel de base de datos: ninguna aplicación que escriba
-- directo en detalle_ventas puede dejar el inventario inconsistente.
-- Si el stock no alcanza, el CHECK ck_repuestos_stock (stock >= 0) revierte
-- toda la transacción con ORA-02290.
CREATE OR REPLACE TRIGGER trg_detven_descuenta_stock
    AFTER INSERT ON detalle_ventas
    FOR EACH ROW
BEGIN
    UPDATE repuestos
       SET stock = stock - :NEW.cantidad
     WHERE id = :NEW.repuesto_id;
END;
/

-- ── 4. Restaurar stock al anular una venta ──────────────────────
CREATE OR REPLACE TRIGGER trg_ventas_anulada_restaura_stock
    AFTER UPDATE OF estado ON ventas
    FOR EACH ROW
    WHEN (NEW.estado = 'anulada' AND OLD.estado != 'anulada')
DECLARE
    CURSOR c_detalle IS
        SELECT repuesto_id, cantidad
          FROM detalle_ventas
         WHERE venta_id = :OLD.id;
BEGIN
    FOR fila IN c_detalle LOOP
        UPDATE repuestos
           SET stock = stock + fila.cantidad
         WHERE id = fila.repuesto_id;
    END LOOP;
END;
/

-- ── 5. Auditoría automática de cambios sensibles en repuestos ────
-- Réplica a nivel de base de datos del patrón Observer que ya usa el
-- backend PHP (AuditLogObserver): cualquier cambio de precio o stock
-- queda registrado aunque se haga por fuera de la aplicación (ej. un
-- script directo o un DBA en SQL Developer).
CREATE OR REPLACE TRIGGER trg_repuestos_auditoria
    AFTER UPDATE OF precio_venta, stock ON repuestos
    FOR EACH ROW
BEGIN
    INSERT INTO audit_log (usuario_id, accion, detalle)
    VALUES (
        NULL,
        'cambio_repuesto',
        'repuesto_id=' || :OLD.id ||
        ' precio_venta:' || :OLD.precio_venta || '->' || :NEW.precio_venta ||
        ' stock:' || :OLD.stock || '->' || :NEW.stock
    );
END;
/

PROMPT Triggers creados correctamente.
