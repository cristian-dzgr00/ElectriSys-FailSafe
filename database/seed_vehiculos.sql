-- ============================================================
-- ElectriSys POS - Seed de repuestos automotrices + vehículos
-- Ejecutar DESPUÉS de seed.sql y schema_v3_migration_nlp.sql
-- Da datos reales para probar el asistente NLP end-to-end con el
-- caso del enunciado: "no hay filtro de aceite original de Toyota
-- para Hilux 2.7 gasolina 2024, ¿qué recomiendo?"
-- ============================================================

USE electrisys;

-- ── 1. Categorías automotrices ──────────────────────────────────
INSERT IGNORE INTO categorias (nombre) VALUES
('Filtros'),('Frenos'),('Baterías'),('Suspensión'),
('Motor'),('Transmisión'),('Encendido'),('Correas y Bandas');

-- ── 2. Proveedores de marcas automotrices ───────────────────────
-- proveedores.nombre no tiene UNIQUE en schema.sql, así que se usa
-- NOT EXISTS (en vez de INSERT IGNORE) para que el script sea
-- idempotente si se corre más de una vez contra la misma BD.
INSERT INTO proveedores (nombre, contacto, telefono, email)
SELECT * FROM (SELECT 'Toyota Original Parts' AS nombre, 'Andrea Ruiz' AS contacto, '3001112233' AS telefono, 'aruiz@toyotaparts.com' AS email) AS t
WHERE NOT EXISTS (SELECT 1 FROM proveedores WHERE nombre = 'Toyota Original Parts');

INSERT INTO proveedores (nombre, contacto, telefono, email)
SELECT * FROM (SELECT 'K&N Filtros', 'Jorge Salazar', '3012223344', 'jsalazar@knfilters.com') AS t
WHERE NOT EXISTS (SELECT 1 FROM proveedores WHERE nombre = 'K&N Filtros');

INSERT INTO proveedores (nombre, contacto, telefono, email)
SELECT * FROM (SELECT 'Mobil 1 Distribuidora', 'Laura Peña', '3023334455', 'lpena@mobil1.com') AS t
WHERE NOT EXISTS (SELECT 1 FROM proveedores WHERE nombre = 'Mobil 1 Distribuidora');

INSERT INTO proveedores (nombre, contacto, telefono, email)
SELECT * FROM (SELECT 'Brembo Colombia', 'Diego Cárdenas', '3034445566', 'dcardenas@brembo.com') AS t
WHERE NOT EXISTS (SELECT 1 FROM proveedores WHERE nombre = 'Brembo Colombia');

INSERT INTO proveedores (nombre, contacto, telefono, email)
SELECT * FROM (SELECT 'Bosch Autopartes', 'Camila Rojas', '3045556677', 'crojas@bosch.com') AS t
WHERE NOT EXISTS (SELECT 1 FROM proveedores WHERE nombre = 'Bosch Autopartes');

INSERT INTO proveedores (nombre, contacto, telefono, email)
SELECT * FROM (SELECT 'NGK Bujías', 'Felipe Ortiz', '3056667788', 'fortiz@ngk.com') AS t
WHERE NOT EXISTS (SELECT 1 FROM proveedores WHERE nombre = 'NGK Bujías');

INSERT INTO proveedores (nombre, contacto, telefono, email)
SELECT * FROM (SELECT 'Mac Baterías', 'Sandra Gil', '3067778899', 'sgil@macbaterias.com') AS t
WHERE NOT EXISTS (SELECT 1 FROM proveedores WHERE nombre = 'Mac Baterías');

INSERT INTO proveedores (nombre, contacto, telefono, email)
SELECT * FROM (SELECT 'Gates Correas', 'Ricardo Mora', '3078889900', 'rmora@gates.com') AS t
WHERE NOT EXISTS (SELECT 1 FROM proveedores WHERE nombre = 'Gates Correas');

-- ── 3. Repuestos automotrices de ejemplo ────────────────────────
-- Usamos SELECT con subconsulta de categoria_id/proveedor_id por nombre
-- para no depender de IDs fijos (categorias/proveedores existentes varían).
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT * FROM (SELECT
    '90915-YZZD4' AS codigo,
    'Filtro de aceite original Toyota' AS nombre,
    'Filtro de aceite original para motores Toyota 2.7 gasolina' AS descripcion,
    (SELECT id FROM categorias WHERE nombre='Filtros') AS categoria_id,
    (SELECT id FROM proveedores WHERE nombre='Toyota Original Parts') AS proveedor_id,
    28000 AS precio_compra, 42000 AS precio_venta, 0 AS stock, 5 AS stock_minimo
) AS t;

INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT * FROM (SELECT
    'HP-1002', 'Filtro de aceite K&N HP-1002',
    'Filtro de aceite de alto flujo, compatible con motores 2.7L gasolina',
    (SELECT id FROM categorias WHERE nombre='Filtros'),
    (SELECT id FROM proveedores WHERE nombre='K&N Filtros'),
    22000, 35000, 12, 5
) AS t;

INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT * FROM (SELECT
    'M1-102', 'Filtro de aceite Mobil 1 M1-102',
    'Filtro de aceite sintético de larga duración para motores 2.7L gasolina',
    (SELECT id FROM categorias WHERE nombre='Filtros'),
    (SELECT id FROM proveedores WHERE nombre='Mobil 1 Distribuidora'),
    24000, 38000, 8, 5
) AS t;

INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT * FROM (SELECT
    'BRM-FD204', 'Pastillas de freno delanteras Brembo',
    'Juego de pastillas de freno delanteras cerámicas',
    (SELECT id FROM categorias WHERE nombre='Frenos'),
    (SELECT id FROM proveedores WHERE nombre='Brembo Colombia'),
    65000, 95000, 20, 5
) AS t;

INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT * FROM (SELECT
    'BSH-0281', 'Pastillas de freno delanteras Bosch',
    'Juego de pastillas de freno delanteras semi-metálicas',
    (SELECT id FROM categorias WHERE nombre='Frenos'),
    (SELECT id FROM proveedores WHERE nombre='Bosch Autopartes'),
    58000, 84000, 15, 5
) AS t;

INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT * FROM (SELECT
    'NGK-BKR6E', 'Bujía NGK BKR6E',
    'Bujía de níquel estándar para motores a gasolina',
    (SELECT id FROM categorias WHERE nombre='Encendido'),
    (SELECT id FROM proveedores WHERE nombre='NGK Bujías'),
    9000, 15000, 60, 10
) AS t;

INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT * FROM (SELECT
    'MAC-48D', 'Batería Mac 48D',
    'Batería de 12V 60Ah para vehículos livianos y pickups',
    (SELECT id FROM categorias WHERE nombre='Baterías'),
    (SELECT id FROM proveedores WHERE nombre='Mac Baterías'),
    180000, 260000, 10, 3
) AS t;

INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT * FROM (SELECT
    'GAT-T295', 'Correa de distribución Gates T295',
    'Correa de distribución reforzada',
    (SELECT id FROM categorias WHERE nombre='Correas y Bandas'),
    (SELECT id FROM proveedores WHERE nombre='Gates Correas'),
    45000, 68000, 6, 3
) AS t;

-- ── 4. Vehículos ─────────────────────────────────────────────────
INSERT IGNORE INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES
('Toyota', 'Hilux', 2020, 2025, '2.7', 'gasolina'),
('Toyota', 'Hilux', 2016, 2019, '2.7', 'gasolina'),
('Toyota', 'Corolla', 2019, 2024, '1.8', 'gasolina'),
('Toyota', 'Fortuner', 2018, 2024, '2.7', 'gasolina'),
('Chevrolet', 'Spark', 2017, 2022, '1.2', 'gasolina'),
('Chevrolet', 'Spark GT', 2015, 2020, '1.4', 'gasolina'),
('Chevrolet', 'Aveo', 2014, 2020, '1.6', 'gasolina'),
('Mazda', '3', 2017, 2023, '2.0', 'gasolina'),
('Mazda', 'CX-5', 2018, 2024, '2.5', 'gasolina'),
('Nissan', 'Sentra', 2016, 2021, '1.8', 'gasolina'),
('Nissan', 'Frontier', 2017, 2023, '2.5', 'diesel'),
('Hyundai', 'Tucson', 2019, 2024, '2.0', 'gasolina'),
('Hyundai', 'Accent', 2015, 2021, '1.6', 'gasolina'),
('Kia', 'Rio', 2016, 2022, '1.6', 'gasolina'),
('Kia', 'Sportage', 2018, 2024, '2.0', 'gasolina'),
('Renault', 'Logan', 2018, 2023, '1.6', 'gasolina'),
('Renault', 'Duster', 2019, 2024, '2.0', 'gasolina'),
('Ford', 'Escape', 2013, 2019, '2.5', 'gasolina'),
('Ford', 'Fiesta', 2014, 2019, '1.6', 'gasolina'),
('Suzuki', 'Swift', 2018, 2023, '1.2', 'gasolina');

-- ── 5. Compatibilidad repuesto ↔ vehículo ────────────────────────
-- Filtros de aceite: el original y sus dos sustitutos aplican a la
-- misma Hilux 2.7 gasolina 2020-2025 (caso exacto del enunciado).
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = '90915-YZZD4' AND v.marca='Toyota' AND v.modelo='Hilux' AND v.anio_desde=2020;

INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'HP-1002' AND v.marca='Toyota' AND v.modelo='Hilux' AND v.anio_desde=2020;

INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'M1-102' AND v.marca='Toyota' AND v.modelo='Hilux' AND v.anio_desde=2020;

-- Los mismos filtros también aplican a la Fortuner (mismo motor 2.7 gasolina)
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo IN ('90915-YZZD4','HP-1002','M1-102') AND v.marca='Toyota' AND v.modelo='Fortuner';

-- Pastillas de freno: Brembo y Bosch, ambas compatibles con Mazda 3 y CX-5
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo IN ('BRM-FD204','BSH-0281') AND v.marca='Mazda' AND v.modelo IN ('3','CX-5');

-- Bujías NGK: compatibles con Kia Rio y Hyundai Accent
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'NGK-BKR6E' AND v.marca IN ('Kia','Hyundai') AND v.modelo IN ('Rio','Accent');

-- Batería Mac: compatible con Chevrolet Spark y Spark GT
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'MAC-48D' AND v.marca='Chevrolet' AND v.modelo IN ('Spark','Spark GT');

-- Correa de distribución Gates: compatible con Nissan Sentra
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'GAT-T295' AND v.marca='Nissan' AND v.modelo='Sentra';
