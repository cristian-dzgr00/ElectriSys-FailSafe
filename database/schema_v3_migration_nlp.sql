-- ============================================================
-- ElectriSys POS - Migración v3.0 (Asistente NLP de repuestos)
-- Ejecutar DESPUÉS de schema.sql y schema_v2_migration.sql
-- ============================================================

USE electrisys;

-- ── 1. Vehículos ──────────────────────────────────────────────────
-- Un repuesto suele aplicar a un rango de años de un modelo, no a un
-- año exacto, por eso se usa anio_desde/anio_hasta en vez de un único año.
CREATE TABLE IF NOT EXISTS vehiculos (
    id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    marca        VARCHAR(80) NOT NULL,
    modelo       VARCHAR(80) NOT NULL,
    anio_desde   SMALLINT UNSIGNED NOT NULL,
    anio_hasta   SMALLINT UNSIGNED NOT NULL,
    motor        VARCHAR(50),
    combustible  ENUM('gasolina','diesel','hibrido','electrico','gas') NOT NULL DEFAULT 'gasolina',
    creado_en    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_vehiculo (marca, modelo, anio_desde, anio_hasta, motor, combustible),
    INDEX idx_vehiculos_marca_modelo (marca, modelo),
    INDEX idx_vehiculos_anios (anio_desde, anio_hasta)
);

-- ── 2. Compatibilidad repuesto ↔ vehículo (N:N) ────────────────────
CREATE TABLE IF NOT EXISTS repuesto_compatibilidad (
    id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    repuesto_id  INT UNSIGNED NOT NULL,
    vehiculo_id  INT UNSIGNED NOT NULL,
    creado_en    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (repuesto_id) REFERENCES repuestos(id) ON DELETE CASCADE,
    FOREIGN KEY (vehiculo_id) REFERENCES vehiculos(id) ON DELETE CASCADE,
    UNIQUE KEY uq_repuesto_vehiculo (repuesto_id, vehiculo_id),
    INDEX idx_compat_repuesto (repuesto_id),
    INDEX idx_compat_vehiculo (vehiculo_id)
);

-- ── 3. Log de consultas al asistente NLP ───────────────────────────
-- Alimentada por AsistenteLogObserver (patrón Observer, igual que
-- AuditLogObserver ya usado para ventas).
CREATE TABLE IF NOT EXISTS consultas_asistente (
    id                  INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    usuario_id          INT UNSIGNED,
    texto_consulta      TEXT NOT NULL,
    intencion_detectada VARCHAR(50),
    entidades_json      JSON,
    respuesta_json      JSON,
    creado_en           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
    INDEX idx_consultas_usuario (usuario_id),
    INDEX idx_consultas_intencion (intencion_detectada),
    INDEX idx_consultas_fecha (creado_en)
);
