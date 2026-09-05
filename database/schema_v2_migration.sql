-- ============================================================
-- ElectriSys POS - Migración v2.0
-- Ejecutar DESPUÉS del schema.sql base
-- ============================================================

USE electrisys;

-- ── 1. Rol 'dueno' faltante ──────────────────────────────────────
INSERT IGNORE INTO roles (nombre) VALUES ('dueno');

-- ── 2. Columnas deleted_at — soft delete consistente ────────────
ALTER TABLE clientes    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP NULL DEFAULT NULL;
ALTER TABLE repuestos   ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP NULL DEFAULT NULL;
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP NULL DEFAULT NULL;
ALTER TABLE usuarios    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP NULL DEFAULT NULL;

-- ── 3. Columnas updated_at en todas las tablas ───────────────────
ALTER TABLE usuarios    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP;
ALTER TABLE clientes    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP;
ALTER TABLE repuestos   ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP;
ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP;
ALTER TABLE ventas      ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP;
ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP;

-- ── 4. Índice compuesto en detalle_ventas ────────────────────────
-- Acelera JOIN entre venta_id y repuesto_id (cálculos de totales, reportes)
CREATE INDEX IF NOT EXISTS idx_detalle_ventas_venta_repuesto
    ON detalle_ventas(venta_id, repuesto_id);

-- Índice para búsqueda de ventas por estado
CREATE INDEX IF NOT EXISTS idx_ventas_estado ON ventas(estado);

-- Índice de clientes por identificación
CREATE INDEX IF NOT EXISTS idx_clientes_identificacion ON clientes(identificacion);

-- Índice de repuestos por código
CREATE INDEX IF NOT EXISTS idx_repuestos_codigo ON repuestos(codigo);

-- ── 5. Tabla de audit log ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    usuario_id  INT UNSIGNED,
    accion      VARCHAR(100) NOT NULL,
    detalle     TEXT,
    ip          VARCHAR(45),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_usuario (usuario_id),
    INDEX idx_audit_accion  (accion),
    INDEX idx_audit_fecha   (created_at)
);

-- ── 6. Tabla para rate limiting (fallback sin APCu) ──────────────
CREATE TABLE IF NOT EXISTS login_attempts (
    id         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    ip         VARCHAR(45) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_attempts_ip_date (ip, created_at)
);

-- Limpiar intentos viejos automáticamente (event scheduler)
-- Si el event_scheduler está habilitado en MySQL:
-- CREATE EVENT IF NOT EXISTS clean_login_attempts
--     ON SCHEDULE EVERY 1 HOUR
--     DO DELETE FROM login_attempts WHERE created_at < DATE_SUB(NOW(), INTERVAL 2 HOUR);

-- ── 7. Campo versión en ventas para detectar conflictos de sync ──
ALTER TABLE ventas ADD COLUMN IF NOT EXISTS version INT UNSIGNED DEFAULT 1;

-- Trigger para incrementar versión en cada UPDATE
DROP TRIGGER IF EXISTS ventas_version_bump;
CREATE TRIGGER ventas_version_bump
    BEFORE UPDATE ON ventas
    FOR EACH ROW
    SET NEW.version = OLD.version + 1;

-- ── 8. Índice para replication lag monitoring ────────────────────
-- pt-heartbeat usa tabla heartbeat — crear si se va a usar Percona Toolkit
CREATE TABLE IF NOT EXISTS heartbeat (
    ts           VARCHAR(26) NOT NULL,
    server_id    INT UNSIGNED NOT NULL PRIMARY KEY,
    file         VARCHAR(255) DEFAULT NULL,
    position     BIGINT DEFAULT NULL,
    relay_master_log_file VARCHAR(255) DEFAULT NULL,
    exec_master_log_pos   BIGINT DEFAULT NULL
);

