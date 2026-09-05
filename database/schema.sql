-- ============================================================
-- ElectriSys POS - Schema v2.0
-- ============================================================

CREATE DATABASE IF NOT EXISTS electrisys CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE electrisys;

-- ── Roles ─────────────────────────────────────────────────────────
CREATE TABLE roles (
    id        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    nombre    VARCHAR(50) NOT NULL UNIQUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO roles (nombre) VALUES ('admin'), ('vendedor'), ('dueno');

-- ── Usuarios ──────────────────────────────────────────────────────
CREATE TABLE usuarios (
    id         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    nombre     VARCHAR(100) NOT NULL,
    email      VARCHAR(150) NOT NULL UNIQUE,
    password   VARCHAR(255) NOT NULL,
    rol_id     INT UNSIGNED NOT NULL,
    activo     TINYINT(1) DEFAULT 1,
    creado_en  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL DEFAULT NULL,
    FOREIGN KEY (rol_id) REFERENCES roles(id)
);

-- ── Proveedores ───────────────────────────────────────────────────
CREATE TABLE proveedores (
    id         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    nombre     VARCHAR(150) NOT NULL,
    contacto   VARCHAR(100),
    telefono   VARCHAR(30),
    email      VARCHAR(150),
    direccion  TEXT,
    activo     TINYINT(1) DEFAULT 1,
    creado_en  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL DEFAULT NULL
);

-- ── Categorías ────────────────────────────────────────────────────
CREATE TABLE categorias (
    id        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    nombre    VARCHAR(100) NOT NULL UNIQUE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Repuestos ─────────────────────────────────────────────────────
CREATE TABLE repuestos (
    id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    codigo        VARCHAR(50) UNIQUE,
    nombre        VARCHAR(200) NOT NULL,
    descripcion   TEXT,
    categoria_id  INT UNSIGNED,
    proveedor_id  INT UNSIGNED,
    precio_compra DECIMAL(12,2) NOT NULL DEFAULT 0,
    precio_venta  DECIMAL(12,2) NOT NULL DEFAULT 0,
    stock         INT NOT NULL DEFAULT 0,
    stock_minimo  INT NOT NULL DEFAULT 5,
    activo        TINYINT(1) DEFAULT 1,
    creado_en     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
    deleted_at    TIMESTAMP NULL DEFAULT NULL,
    FOREIGN KEY (categoria_id) REFERENCES categorias(id),
    FOREIGN KEY (proveedor_id) REFERENCES proveedores(id)
);

-- ── Clientes ──────────────────────────────────────────────────────
CREATE TABLE clientes (
    id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    nombre         VARCHAR(150) NOT NULL,
    identificacion VARCHAR(30) UNIQUE,
    tipo_doc       ENUM('CC','NIT','CE','Pasaporte') DEFAULT 'CC',
    telefono       VARCHAR(30),
    email          VARCHAR(150),
    direccion      TEXT,
    activo         TINYINT(1) DEFAULT 1,
    creado_en      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
    deleted_at     TIMESTAMP NULL DEFAULT NULL
);

-- ── Ventas ────────────────────────────────────────────────────────
CREATE TABLE ventas (
    id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    numero         VARCHAR(20) NOT NULL UNIQUE,
    cliente_id     INT UNSIGNED,
    usuario_id     INT UNSIGNED NOT NULL,
    subtotal       DECIMAL(14,2) NOT NULL DEFAULT 0,
    descuento      DECIMAL(14,2) NOT NULL DEFAULT 0,
    impuesto       DECIMAL(14,2) NOT NULL DEFAULT 0,
    total          DECIMAL(14,2) NOT NULL DEFAULT 0,
    metodo_pago    ENUM('efectivo','tarjeta','transferencia','credito') DEFAULT 'efectivo',
    estado         ENUM('completada','anulada','pendiente') DEFAULT 'completada',
    notas          TEXT,
    pendiente_sync TINYINT(1) DEFAULT 0,
    version        INT UNSIGNED DEFAULT 1,          -- control de conflictos en sync
    creado_en      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id)  REFERENCES clientes(id),
    FOREIGN KEY (usuario_id)  REFERENCES usuarios(id)
);

-- Auto-incrementar versión en cada UPDATE
CREATE TRIGGER ventas_version_bump
    BEFORE UPDATE ON ventas
    FOR EACH ROW
    SET NEW.version = OLD.version + 1;

-- ── Detalle de Ventas ─────────────────────────────────────────────
CREATE TABLE detalle_ventas (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    venta_id    INT UNSIGNED NOT NULL,
    repuesto_id INT UNSIGNED NOT NULL,
    cantidad    INT NOT NULL DEFAULT 1,
    precio_unit DECIMAL(12,2) NOT NULL,
    descuento   DECIMAL(12,2) NOT NULL DEFAULT 0,
    subtotal    DECIMAL(12,2) NOT NULL,
    FOREIGN KEY (venta_id)    REFERENCES ventas(id) ON DELETE CASCADE,
    FOREIGN KEY (repuesto_id) REFERENCES repuestos(id)
);

-- ── Cotizaciones ──────────────────────────────────────────────────
CREATE TABLE cotizaciones (
    id         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    numero     VARCHAR(20) NOT NULL UNIQUE,
    cliente_id INT UNSIGNED,
    usuario_id INT UNSIGNED NOT NULL,
    subtotal   DECIMAL(14,2) NOT NULL DEFAULT 0,
    descuento  DECIMAL(14,2) NOT NULL DEFAULT 0,
    impuesto   DECIMAL(14,2) NOT NULL DEFAULT 0,
    total      DECIMAL(14,2) NOT NULL DEFAULT 0,
    estado     ENUM('borrador','enviada','aceptada','rechazada','vencida') DEFAULT 'borrador',
    vence_en   DATE,
    notas      TEXT,
    creado_en  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id),
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

-- ── Detalle de Cotizaciones ───────────────────────────────────────
CREATE TABLE detalle_cotizaciones (
    id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    cotizacion_id INT UNSIGNED NOT NULL,
    repuesto_id   INT UNSIGNED NOT NULL,
    cantidad      INT NOT NULL DEFAULT 1,
    precio_unit   DECIMAL(12,2) NOT NULL,
    descuento     DECIMAL(12,2) NOT NULL DEFAULT 0,
    subtotal      DECIMAL(12,2) NOT NULL,
    FOREIGN KEY (cotizacion_id) REFERENCES cotizaciones(id) ON DELETE CASCADE,
    FOREIGN KEY (repuesto_id)   REFERENCES repuestos(id)
);

-- ── Audit Log ─────────────────────────────────────────────────────
CREATE TABLE audit_log (
    id         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT UNSIGNED,
    accion     VARCHAR(100) NOT NULL,
    detalle    TEXT,
    ip         VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_usuario (usuario_id),
    INDEX idx_audit_accion  (accion),
    INDEX idx_audit_fecha   (created_at)
);

-- ── Login Attempts (rate limiting fallback sin APCu) ──────────────
CREATE TABLE login_attempts (
    id         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    ip         VARCHAR(45) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_attempts_ip_date (ip, created_at)
);

-- ── Heartbeat para monitoreo de replication lag ───────────────────
CREATE TABLE heartbeat (
    ts                        VARCHAR(26) NOT NULL,
    server_id                 INT UNSIGNED NOT NULL PRIMARY KEY,
    file                      VARCHAR(255) DEFAULT NULL,
    position                  BIGINT DEFAULT NULL,
    relay_master_log_file     VARCHAR(255) DEFAULT NULL,
    exec_master_log_pos       BIGINT DEFAULT NULL
);

-- ═══════════════════════════════════════════════════════════════
-- ÍNDICES DE RENDIMIENTO
-- ═══════════════════════════════════════════════════════════════
CREATE INDEX idx_ventas_fecha          ON ventas(creado_en);
CREATE INDEX idx_ventas_cliente        ON ventas(cliente_id);
CREATE INDEX idx_ventas_estado         ON ventas(estado);
CREATE INDEX idx_ventas_sync           ON ventas(pendiente_sync);
CREATE INDEX idx_repuestos_stock       ON repuestos(stock);
CREATE INDEX idx_repuestos_codigo      ON repuestos(codigo);
CREATE INDEX idx_clientes_identificacion ON clientes(identificacion);

-- Índice compuesto clave: acelera JOIN en reportes y cálculo de totales
CREATE INDEX idx_detalle_ventas_venta_repuesto
    ON detalle_ventas(venta_id, repuesto_id);
