-- ============================================================
-- ElectriSys POS - Catálogo real de repuestos: autopartes y
-- maquinaria agrícola, + vehículos/equipos y su compatibilidad.
-- Ejecutar DESPUÉS de seed.sql y schema_v3_migration_nlp.sql.
-- ============================================================

USE electrisys;

-- ── 1. Categorías ────────────────────────────────────────────────
INSERT IGNORE INTO categorias (nombre) VALUES
('Filtros'),('Frenos'),('Baterías'),('Suspensión'),
('Motor'),('Transmisión'),('Encendido'),('Correas y Bandas'),
('Sistema Eléctrico'),('Hidráulica'),('Enganches y Acoples'),('Neumáticos');

-- ── 2. Proveedores ───────────────────────────────────────────────
INSERT INTO proveedores (nombre, contacto, telefono, email)
SELECT * FROM (SELECT 'Toyota Original Parts', 'Andrea Ruiz', '3001112233', 'aruiz@toyotaparts.com') AS t
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
INSERT INTO proveedores (nombre, contacto, telefono, email)
SELECT * FROM (SELECT 'John Deere Partes', 'Oscar Villamil', '3089990011', 'ovillamil@johndeere.com') AS t
WHERE NOT EXISTS (SELECT 1 FROM proveedores WHERE nombre = 'John Deere Partes');
INSERT INTO proveedores (nombre, contacto, telefono, email)
SELECT * FROM (SELECT 'Case IH Repuestos', 'Natalia Bermúdez', '3090001122', 'nbermudez@caseih.com') AS t
WHERE NOT EXISTS (SELECT 1 FROM proveedores WHERE nombre = 'Case IH Repuestos');
INSERT INTO proveedores (nombre, contacto, telefono, email)
SELECT * FROM (SELECT 'Fleetguard Filtros Industriales', 'Hernán Castro', '3101112233', 'hcastro@fleetguard.com') AS t
WHERE NOT EXISTS (SELECT 1 FROM proveedores WHERE nombre = 'Fleetguard Filtros Industriales');
INSERT INTO proveedores (nombre, contacto, telefono, email)
SELECT * FROM (SELECT 'Massey Ferguson Repuestos', 'Liliana Prada', '3112223344', 'lprada@masseyferguson.com') AS t
WHERE NOT EXISTS (SELECT 1 FROM proveedores WHERE nombre = 'Massey Ferguson Repuestos');
INSERT INTO proveedores (nombre, contacto, telefono, email)
SELECT * FROM (SELECT 'Michelin Agro', 'Sergio Nieto', '3123334455', 'snieto@michelinagro.com') AS t
WHERE NOT EXISTS (SELECT 1 FROM proveedores WHERE nombre = 'Michelin Agro');

-- ── 3. Repuestos: autopartes ─────────────────────────────────────
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT '90915-YZZD4','Filtro de aceite original Toyota','Filtro de aceite original para motores Toyota 2.7 gasolina',
  (SELECT id FROM categorias WHERE nombre='Filtros'), (SELECT id FROM proveedores WHERE nombre='Toyota Original Parts'), 28000,42000,0,5;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'HP-1002','Filtro de aceite K&N HP-1002','Filtro de aceite de alto flujo, compatible con motores 2.7L gasolina',
  (SELECT id FROM categorias WHERE nombre='Filtros'), (SELECT id FROM proveedores WHERE nombre='K&N Filtros'), 22000,35000,12,5;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'M1-102','Filtro de aceite Mobil 1 M1-102','Filtro de aceite sintético de larga duración para motores 2.7L gasolina',
  (SELECT id FROM categorias WHERE nombre='Filtros'), (SELECT id FROM proveedores WHERE nombre='Mobil 1 Distribuidora'), 24000,38000,8,5;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'BRM-FD204','Pastillas de freno delanteras Brembo','Juego de pastillas de freno delanteras cerámicas',
  (SELECT id FROM categorias WHERE nombre='Frenos'), (SELECT id FROM proveedores WHERE nombre='Brembo Colombia'), 65000,95000,20,5;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'BSH-0281','Pastillas de freno delanteras Bosch','Juego de pastillas de freno delanteras semi-metálicas',
  (SELECT id FROM categorias WHERE nombre='Frenos'), (SELECT id FROM proveedores WHERE nombre='Bosch Autopartes'), 58000,84000,15,5;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'NGK-BKR6E','Bujía NGK BKR6E','Bujía de níquel estándar para motores a gasolina',
  (SELECT id FROM categorias WHERE nombre='Encendido'), (SELECT id FROM proveedores WHERE nombre='NGK Bujías'), 9000,15000,60,10;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'MAC-48D','Batería Mac 48D','Batería de 12V 60Ah para vehículos livianos y pickups',
  (SELECT id FROM categorias WHERE nombre='Baterías'), (SELECT id FROM proveedores WHERE nombre='Mac Baterías'), 180000,260000,10,3;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'GAT-T295','Correa de distribución Gates T295','Correa de distribución reforzada',
  (SELECT id FROM categorias WHERE nombre='Correas y Bandas'), (SELECT id FROM proveedores WHERE nombre='Gates Correas'), 45000,68000,6,3;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'BSH-ALT120','Alternador Bosch 120A','Alternador reconstruido 12V 120A para vehículos livianos',
  (SELECT id FROM categorias WHERE nombre='Sistema Eléctrico'), (SELECT id FROM proveedores WHERE nombre='Bosch Autopartes'), 210000,310000,7,3;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'MNR-AM204','Amortiguador delantero Monroe','Amortiguador a gas para suspensión delantera',
  (SELECT id FROM categorias WHERE nombre='Suspensión'), (SELECT id FROM proveedores WHERE nombre='Bosch Autopartes'), 95000,140000,14,4;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'BSH-RAD330','Radiador de aluminio Bosch','Radiador de aluminio para sistema de enfriamiento',
  (SELECT id FROM categorias WHERE nombre='Motor'), (SELECT id FROM proveedores WHERE nombre='Bosch Autopartes'), 280000,395000,5,2;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'MI-P205','Llanta Michelin 205/55R16','Neumático radial para automóvil',
  (SELECT id FROM categorias WHERE nombre='Neumáticos'), (SELECT id FROM proveedores WHERE nombre='Michelin Agro'), 210000,320000,24,6;

-- ── 4. Repuestos: maquinaria agrícola ────────────────────────────
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'JD-RE504836','Filtro de aceite hidráulico John Deere','Filtro de aceite hidráulico para tractores serie 5000/6000',
  (SELECT id FROM categorias WHERE nombre='Hidráulica'), (SELECT id FROM proveedores WHERE nombre='John Deere Partes'), 65000,98000,10,3;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'FG-LF3970','Filtro de aceite de motor Fleetguard','Filtro de aceite para motores diésel de tractores e implementos',
  (SELECT id FROM categorias WHERE nombre='Filtros'), (SELECT id FROM proveedores WHERE nombre='Fleetguard Filtros Industriales'), 42000,63000,18,5;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'FG-FF5320','Filtro de combustible Fleetguard','Filtro de combustible diésel para tractores agrícolas',
  (SELECT id FROM categorias WHERE nombre='Filtros'), (SELECT id FROM proveedores WHERE nombre='Fleetguard Filtros Industriales'), 38000,57000,0,5;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'CIH-FF7000','Filtro de combustible Case IH','Filtro de combustible diésel equivalente para tractores serie Puma',
  (SELECT id FROM categorias WHERE nombre='Filtros'), (SELECT id FROM proveedores WHERE nombre='Case IH Repuestos'), 40000,60000,9,4;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'MF-FF6800','Filtro de combustible Massey Ferguson','Filtro de combustible diésel equivalente para tractores serie 4700',
  (SELECT id FROM categorias WHERE nombre='Filtros'), (SELECT id FROM proveedores WHERE nombre='Massey Ferguson Repuestos'), 39000,58000,11,4;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'JD-BAT31','Batería John Deere 31','Batería de 12V 100Ah para tractores y maquinaria pesada',
  (SELECT id FROM categorias WHERE nombre='Baterías'), (SELECT id FROM proveedores WHERE nombre='John Deere Partes'), 320000,460000,6,2;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'CIH-DISC88','Disco de embrague Case IH','Disco de embrague para tractores serie Puma',
  (SELECT id FROM categorias WHERE nombre='Transmisión'), (SELECT id FROM proveedores WHERE nombre='Case IH Repuestos'), 480000,690000,4,2;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'JD-ENG3PT','Enganche de tres puntos John Deere','Kit de enganche de tres puntos categoría II',
  (SELECT id FROM categorias WHERE nombre='Enganches y Acoples'), (SELECT id FROM proveedores WHERE nombre='John Deere Partes'), 850000,1250000,3,1;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'MF-BOMHID','Bomba hidráulica Massey Ferguson','Bomba hidráulica de repuesto para tractores serie 4700/6700',
  (SELECT id FROM categorias WHERE nombre='Hidráulica'), (SELECT id FROM proveedores WHERE nombre='Massey Ferguson Repuestos'), 620000,890000,5,2;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'MI-AGR1846','Llanta agrícola Michelin 18.4-46','Neumático trasero de tractor, uso agrícola',
  (SELECT id FROM categorias WHERE nombre='Neumáticos'), (SELECT id FROM proveedores WHERE nombre='Michelin Agro'), 1450000,2100000,8,2;
INSERT IGNORE INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'JD-CORREA112','Correa de alternador John Deere','Correa de accesorios para tractores serie 5000',
  (SELECT id FROM categorias WHERE nombre='Correas y Bandas'), (SELECT id FROM proveedores WHERE nombre='John Deere Partes'), 55000,82000,7,3;

-- ── 5. Vehículos (autos) ─────────────────────────────────────────
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

-- ── 6. Maquinaria agrícola (misma tabla vehiculos) ───────────────
INSERT IGNORE INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES
('John Deere', '5075E', 2016, 2024, '4.5', 'diesel'),
('John Deere', '6110M', 2017, 2024, '4.5', 'diesel'),
('Case IH', 'Puma 165', 2015, 2023, '6.7', 'diesel'),
('Case IH', 'Farmall 75C', 2016, 2023, '3.4', 'diesel'),
('Massey Ferguson', '4707', 2017, 2024, '4.4', 'diesel'),
('Massey Ferguson', '6713', 2016, 2023, '4.9', 'diesel'),
('New Holland', 'T6.120', 2016, 2024, '6.7', 'diesel');

-- ── 7. Compatibilidad: autopartes ────────────────────────────────
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = '90915-YZZD4' AND v.marca='Toyota' AND v.modelo='Hilux' AND v.anio_desde=2020;
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'HP-1002' AND v.marca='Toyota' AND v.modelo='Hilux' AND v.anio_desde=2020;
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'M1-102' AND v.marca='Toyota' AND v.modelo='Hilux' AND v.anio_desde=2020;
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo IN ('90915-YZZD4','HP-1002','M1-102') AND v.marca='Toyota' AND v.modelo='Fortuner';
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo IN ('BRM-FD204','BSH-0281') AND v.marca='Mazda' AND v.modelo IN ('3','CX-5');
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'NGK-BKR6E' AND v.marca IN ('Kia','Hyundai') AND v.modelo IN ('Rio','Accent');
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'MAC-48D' AND v.marca='Chevrolet' AND v.modelo IN ('Spark','Spark GT');
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'GAT-T295' AND v.marca='Nissan' AND v.modelo='Sentra';
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'BSH-ALT120' AND v.marca='Renault' AND v.modelo IN ('Logan','Duster');
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'MNR-AM204' AND v.marca='Ford' AND v.modelo IN ('Escape','Fiesta');
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'BSH-RAD330' AND v.marca='Hyundai' AND v.modelo='Tucson';
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'MI-P205' AND v.marca='Suzuki' AND v.modelo='Swift';

-- ── 8. Compatibilidad: maquinaria agrícola ───────────────────────
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo IN ('JD-RE504836','JD-BAT31','JD-ENG3PT','JD-CORREA112') AND v.marca='John Deere' AND v.modelo='5075E';
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo IN ('FG-LF3970','JD-BAT31') AND v.marca='John Deere' AND v.modelo='6110M';
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo IN ('FG-FF5320','CIH-DISC88') AND v.marca='Case IH' AND v.modelo='Puma 165';
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'CIH-FF7000' AND v.marca='Case IH' AND v.modelo IN ('Farmall 75C','Puma 165');
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo IN ('MF-FF6800','MF-BOMHID') AND v.marca='Massey Ferguson' AND v.modelo='4707';
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'MF-BOMHID' AND v.marca='Massey Ferguson' AND v.modelo='6713';
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'MI-AGR1846' AND v.marca IN ('John Deere','Case IH','Massey Ferguson','New Holland');
INSERT IGNORE INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v
WHERE r.codigo = 'FG-LF3970' AND v.marca='New Holland' AND v.modelo='T6.120';
