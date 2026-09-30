-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 11. Cotizaciones: nuevo ciclo de vida de 3 estados
-- Ejecutar conectado como el usuario ELECTRISYS.
--
-- Reemplaza el flujo comercial genérico (borrador → enviada → aceptada /
-- rechazada / vencida) por el que realmente usa el negocio:
--
--   activa    →  se acaba de hacer, los precios cotizados siguen vigentes
--   vencida   →  cambió el precio de alguno de sus repuestos, ya no se
--                puede sostener el total que se le prometió al cliente
--   realizada →  el cliente aceptó y se convirtió en venta
--
-- La diferencia de fondo con el modelo anterior: "vencida" deja de ser un
-- estado que alguien marca a mano y pasa a ser una consecuencia automática
-- de un hecho del negocio. Una cotización con precios viejos no es un
-- documento "pendiente de revisar": es una promesa que la empresa ya no
-- puede cumplir, y el sistema tiene que decirlo solo.
--
-- La fecha vence_en se conserva como dato informativo (el vendedor le dice
-- al cliente hasta cuándo estima tenerla), pero NO cambia el estado: por
-- decisión del negocio, lo único que vence una cotización es que se le
-- mueva el precio a un repuesto.
-- ============================================================

-- ── 1. Quitar el CHECK viejo ──────────────────────────────────────
-- Tiene que ir PRIMERO: el constraint anterior solo admite los estados
-- viejos, así que cualquier UPDATE a 'activa' se rechazaría con ORA-02290
-- antes de poder migrar nada.
--
-- Envuelto para que el script sea re-ejecutable: si el constraint ya no
-- está (porque el script corrió antes), no debe abortar el resto.
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE cotizaciones DROP CONSTRAINT ck_cotiz_estado';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -2443 THEN   -- ORA-02443: el constraint no existe
            RAISE;
        END IF;
END;
/

-- ── 2. Migrar los datos existentes ────────────────────────────────
-- Las que ya estaban vencidas se quedan vencidas; el resto arranca activa.
UPDATE cotizaciones SET estado = 'activa' WHERE estado <> 'vencida';
COMMIT;

-- ── 3. Poner el CHECK nuevo ───────────────────────────────────────
ALTER TABLE cotizaciones MODIFY estado DEFAULT 'activa';

ALTER TABLE cotizaciones
    ADD CONSTRAINT ck_cotiz_estado CHECK (estado IN ('activa','vencida','realizada'));

-- ── 4. Vencimiento automático al cambiar un precio ────────────────
-- El corazón de la regla nueva. Cuando a un repuesto le cambia el
-- precio_venta, toda cotización ACTIVA que lo incluya queda vencida al
-- instante, sin que nadie tenga que acordarse de revisarlo.
--
-- Solo se tocan las 'activa': una 'realizada' ya se convirtió en venta y
-- su precio quedó congelado en la factura, y una 'vencida' ya lo está.
--
-- No hay problema de tabla mutante: el trigger es sobre REPUESTOS y
-- escribe sobre COTIZACIONES, que es otra tabla.
CREATE OR REPLACE TRIGGER trg_repuestos_vence_cotizaciones
    AFTER UPDATE OF precio_venta ON repuestos
    FOR EACH ROW
    WHEN (NEW.precio_venta != OLD.precio_venta)
BEGIN
    UPDATE cotizaciones c
       SET c.estado = 'vencida'
     WHERE c.estado = 'activa'
       AND EXISTS (
           SELECT 1
             FROM detalle_cotizaciones d
            WHERE d.cotizacion_id = c.id
              AND d.repuesto_id   = :NEW.id
       );
END;
/

PROMPT Cotizaciones migradas al ciclo activa/vencida/realizada.
