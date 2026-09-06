-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 05. Datos de prueba (equivalente a database/seed.sql +
--     database/seed_vehiculos.sql de MySQL)
-- Ejecutar conectado como ELECTRISYS, una sola vez sobre el esquema
-- recién creado (no es idempotente: no incluye guardas NOT EXISTS
-- porque no hace falta re-ejecutarlo sobre datos existentes).
-- Nota: Oracle no soporta VALUES (...),(...),(...) multi-fila en un
-- solo INSERT como MySQL — cada fila es un INSERT independiente.
-- ============================================================

-- SET DEFINE OFF es obligatorio: por defecto SQL*Plus interpreta "&"
-- como el inicio de una variable de sustitución (ej. "K&N Filtros"
-- dispararía un prompt pidiendo un valor para "N" y corrompería el
-- resto del script). Sin esto el seed falla a mitad de camino.
SET DEFINE OFF;

-- ── Usuarios (password = "password" para ambos, mismo hash bcrypt del proyecto) ──
INSERT INTO usuarios (nombre, email, password, rol_id) VALUES
    ('Administrador', 'admin@electrisys.com', '$2y$10$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2.uheWG/igi', 1);
INSERT INTO usuarios (nombre, email, password, rol_id) VALUES
    ('Carlos Vendedor', 'vendedor@electrisys.com', '$2y$10$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2.uheWG/igi', 2);

-- ── Clientes (12) ──────────────────────────────────────────────────
INSERT INTO clientes (nombre, identificacion, tipo_doc, telefono, email) VALUES ('Constructora Andina S.A.S', '900123456', 'NIT', '6012345678', 'compras@andina.com');
INSERT INTO clientes (nombre, identificacion, tipo_doc, telefono, email) VALUES ('Luis Felipe Gómez', '1075234567', 'CC', '3156789012', 'lgomez@gmail.com');
INSERT INTO clientes (nombre, identificacion, tipo_doc, telefono, email) VALUES ('Ferretería El Tornillo', '800987654', 'NIT', '6023456789', 'compras@eltornillo.com');
INSERT INTO clientes (nombre, identificacion, tipo_doc, telefono, email) VALUES ('Taller Mecánico El Motor', '900456123', 'NIT', '3011122334', 'contacto@elmotor.com');
INSERT INTO clientes (nombre, identificacion, tipo_doc, telefono, email) VALUES ('Agropecuaria La Esperanza S.A.S', '900789456', 'NIT', '3122233445', 'compras@laesperanza.com');
INSERT INTO clientes (nombre, identificacion, tipo_doc, telefono, email) VALUES ('Juan Carlos Restrepo', '80234567', 'CC', '3133344556', 'jcrestrepo@gmail.com');
INSERT INTO clientes (nombre, identificacion, tipo_doc, telefono, email) VALUES ('Distribuidora de Repuestos del Valle', '900321654', 'NIT', '3144455667', 'ventas@repuestosvalle.com');
INSERT INTO clientes (nombre, identificacion, tipo_doc, telefono, email) VALUES ('Finca San Isidro', '900654987', 'NIT', '3155566778', 'sanisidro@fincas.com');
INSERT INTO clientes (nombre, identificacion, tipo_doc, telefono, email) VALUES ('María Fernanda Torres', '1032456789', 'CC', '3166677889', 'mftorres@gmail.com');
INSERT INTO clientes (nombre, identificacion, tipo_doc, telefono, email) VALUES ('Talleres Unidos del Sur Ltda', '900987321', 'NIT', '3177788990', 'info@unidosdelsur.com');
INSERT INTO clientes (nombre, identificacion, tipo_doc, telefono, email) VALUES ('Cooperativa Agrícola del Meta', '800112233', 'NIT', '3188899001', 'coopmeta@agro.com');
INSERT INTO clientes (nombre, identificacion, tipo_doc, telefono, email) VALUES ('Pedro Antonio Gómez', '19345678', 'CC', '3199900112', 'pagomez@gmail.com');

-- ── Categorías (12) ────────────────────────────────────────────────
INSERT INTO categorias (nombre) VALUES ('Filtros');
INSERT INTO categorias (nombre) VALUES ('Frenos');
INSERT INTO categorias (nombre) VALUES ('Baterías');
INSERT INTO categorias (nombre) VALUES ('Suspensión');
INSERT INTO categorias (nombre) VALUES ('Motor');
INSERT INTO categorias (nombre) VALUES ('Transmisión');
INSERT INTO categorias (nombre) VALUES ('Encendido');
INSERT INTO categorias (nombre) VALUES ('Correas y Bandas');
INSERT INTO categorias (nombre) VALUES ('Sistema Eléctrico');
INSERT INTO categorias (nombre) VALUES ('Hidráulica');
INSERT INTO categorias (nombre) VALUES ('Enganches y Acoples');
INSERT INTO categorias (nombre) VALUES ('Neumáticos');

-- ── Proveedores (13) ───────────────────────────────────────────────
INSERT INTO proveedores (nombre, contacto, telefono, email) VALUES ('Toyota Original Parts', 'Andrea Ruiz', '3001112233', 'aruiz@toyotaparts.com');
INSERT INTO proveedores (nombre, contacto, telefono, email) VALUES ('K&N Filtros', 'Jorge Salazar', '3012223344', 'jsalazar@knfilters.com');
INSERT INTO proveedores (nombre, contacto, telefono, email) VALUES ('Mobil 1 Distribuidora', 'Laura Peña', '3023334455', 'lpena@mobil1.com');
INSERT INTO proveedores (nombre, contacto, telefono, email) VALUES ('Brembo Colombia', 'Diego Cárdenas', '3034445566', 'dcardenas@brembo.com');
INSERT INTO proveedores (nombre, contacto, telefono, email) VALUES ('Bosch Autopartes', 'Camila Rojas', '3045556677', 'crojas@bosch.com');
INSERT INTO proveedores (nombre, contacto, telefono, email) VALUES ('NGK Bujías', 'Felipe Ortiz', '3056667788', 'fortiz@ngk.com');
INSERT INTO proveedores (nombre, contacto, telefono, email) VALUES ('Mac Baterías', 'Sandra Gil', '3067778899', 'sgil@macbaterias.com');
INSERT INTO proveedores (nombre, contacto, telefono, email) VALUES ('Gates Correas', 'Ricardo Mora', '3078889900', 'rmora@gates.com');
INSERT INTO proveedores (nombre, contacto, telefono, email) VALUES ('John Deere Partes', 'Oscar Villamil', '3089990011', 'ovillamil@johndeere.com');
INSERT INTO proveedores (nombre, contacto, telefono, email) VALUES ('Case IH Repuestos', 'Natalia Bermúdez', '3090001122', 'nbermudez@caseih.com');
INSERT INTO proveedores (nombre, contacto, telefono, email) VALUES ('Fleetguard Filtros Industriales', 'Hernán Castro', '3101112233', 'hcastro@fleetguard.com');
INSERT INTO proveedores (nombre, contacto, telefono, email) VALUES ('Massey Ferguson Repuestos', 'Liliana Prada', '3112223344', 'lprada@masseyferguson.com');
INSERT INTO proveedores (nombre, contacto, telefono, email) VALUES ('Michelin Agro', 'Sergio Nieto', '3123334455', 'snieto@michelinagro.com');

-- ── Repuestos: autopartes (12) ─────────────────────────────────────
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT '90915-YZZD4','Filtro de aceite original Toyota','Filtro de aceite original para motores Toyota 2.7 gasolina',
  (SELECT id FROM categorias WHERE nombre='Filtros'), (SELECT id FROM proveedores WHERE nombre='Toyota Original Parts'), 28000,42000,0,5 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'HP-1002','Filtro de aceite K&N HP-1002','Filtro de aceite de alto flujo, compatible con motores 2.7L gasolina',
  (SELECT id FROM categorias WHERE nombre='Filtros'), (SELECT id FROM proveedores WHERE nombre='K&N Filtros'), 22000,35000,12,5 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'M1-102','Filtro de aceite Mobil 1 M1-102','Filtro de aceite sintético de larga duración para motores 2.7L gasolina',
  (SELECT id FROM categorias WHERE nombre='Filtros'), (SELECT id FROM proveedores WHERE nombre='Mobil 1 Distribuidora'), 24000,38000,8,5 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'BRM-FD204','Pastillas de freno delanteras Brembo','Juego de pastillas de freno delanteras cerámicas',
  (SELECT id FROM categorias WHERE nombre='Frenos'), (SELECT id FROM proveedores WHERE nombre='Brembo Colombia'), 65000,95000,20,5 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'BSH-0281','Pastillas de freno delanteras Bosch','Juego de pastillas de freno delanteras semi-metálicas',
  (SELECT id FROM categorias WHERE nombre='Frenos'), (SELECT id FROM proveedores WHERE nombre='Bosch Autopartes'), 58000,84000,15,5 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'NGK-BKR6E','Bujía NGK BKR6E','Bujía de níquel estándar para motores a gasolina',
  (SELECT id FROM categorias WHERE nombre='Encendido'), (SELECT id FROM proveedores WHERE nombre='NGK Bujías'), 9000,15000,60,10 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'MAC-48D','Batería Mac 48D','Batería de 12V 60Ah para vehículos livianos y pickups',
  (SELECT id FROM categorias WHERE nombre='Baterías'), (SELECT id FROM proveedores WHERE nombre='Mac Baterías'), 180000,260000,10,3 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'GAT-T295','Correa de distribución Gates T295','Correa de distribución reforzada',
  (SELECT id FROM categorias WHERE nombre='Correas y Bandas'), (SELECT id FROM proveedores WHERE nombre='Gates Correas'), 45000,68000,6,3 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'BSH-ALT120','Alternador Bosch 120A','Alternador reconstruido 12V 120A para vehículos livianos',
  (SELECT id FROM categorias WHERE nombre='Sistema Eléctrico'), (SELECT id FROM proveedores WHERE nombre='Bosch Autopartes'), 210000,310000,7,3 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'MNR-AM204','Amortiguador delantero Monroe','Amortiguador a gas para suspensión delantera',
  (SELECT id FROM categorias WHERE nombre='Suspensión'), (SELECT id FROM proveedores WHERE nombre='Bosch Autopartes'), 95000,140000,14,4 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'BSH-RAD330','Radiador de aluminio Bosch','Radiador de aluminio para sistema de enfriamiento',
  (SELECT id FROM categorias WHERE nombre='Motor'), (SELECT id FROM proveedores WHERE nombre='Bosch Autopartes'), 280000,395000,5,2 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'MI-P205','Llanta Michelin 205/55R16','Neumático radial para automóvil',
  (SELECT id FROM categorias WHERE nombre='Neumáticos'), (SELECT id FROM proveedores WHERE nombre='Michelin Agro'), 210000,320000,24,6 FROM dual;

-- ── Repuestos: maquinaria agrícola (11) ────────────────────────────
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'JD-RE504836','Filtro de aceite hidráulico John Deere','Filtro de aceite hidráulico para tractores serie 5000/6000',
  (SELECT id FROM categorias WHERE nombre='Hidráulica'), (SELECT id FROM proveedores WHERE nombre='John Deere Partes'), 65000,98000,10,3 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'FG-LF3970','Filtro de aceite de motor Fleetguard','Filtro de aceite para motores diésel de tractores e implementos',
  (SELECT id FROM categorias WHERE nombre='Filtros'), (SELECT id FROM proveedores WHERE nombre='Fleetguard Filtros Industriales'), 42000,63000,18,5 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'FG-FF5320','Filtro de combustible Fleetguard','Filtro de combustible diésel para tractores agrícolas',
  (SELECT id FROM categorias WHERE nombre='Filtros'), (SELECT id FROM proveedores WHERE nombre='Fleetguard Filtros Industriales'), 38000,57000,0,5 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'CIH-FF7000','Filtro de combustible Case IH','Filtro de combustible diésel equivalente para tractores serie Puma',
  (SELECT id FROM categorias WHERE nombre='Filtros'), (SELECT id FROM proveedores WHERE nombre='Case IH Repuestos'), 40000,60000,9,4 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'MF-FF6800','Filtro de combustible Massey Ferguson','Filtro de combustible diésel equivalente para tractores serie 4700',
  (SELECT id FROM categorias WHERE nombre='Filtros'), (SELECT id FROM proveedores WHERE nombre='Massey Ferguson Repuestos'), 39000,58000,11,4 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'JD-BAT31','Batería John Deere 31','Batería de 12V 100Ah para tractores y maquinaria pesada',
  (SELECT id FROM categorias WHERE nombre='Baterías'), (SELECT id FROM proveedores WHERE nombre='John Deere Partes'), 320000,460000,6,2 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'CIH-DISC88','Disco de embrague Case IH','Disco de embrague para tractores serie Puma',
  (SELECT id FROM categorias WHERE nombre='Transmisión'), (SELECT id FROM proveedores WHERE nombre='Case IH Repuestos'), 480000,690000,4,2 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'JD-ENG3PT','Enganche de tres puntos John Deere','Kit de enganche de tres puntos categoría II',
  (SELECT id FROM categorias WHERE nombre='Enganches y Acoples'), (SELECT id FROM proveedores WHERE nombre='John Deere Partes'), 850000,1250000,3,1 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'MF-BOMHID','Bomba hidráulica Massey Ferguson','Bomba hidráulica de repuesto para tractores serie 4700/6700',
  (SELECT id FROM categorias WHERE nombre='Hidráulica'), (SELECT id FROM proveedores WHERE nombre='Massey Ferguson Repuestos'), 620000,890000,5,2 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'MI-AGR1846','Llanta agrícola Michelin 18.4-46','Neumático trasero de tractor, uso agrícola',
  (SELECT id FROM categorias WHERE nombre='Neumáticos'), (SELECT id FROM proveedores WHERE nombre='Michelin Agro'), 1450000,2100000,8,2 FROM dual;
INSERT INTO repuestos (codigo, nombre, descripcion, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo)
SELECT 'JD-CORREA112','Correa de alternador John Deere','Correa de accesorios para tractores serie 5000',
  (SELECT id FROM categorias WHERE nombre='Correas y Bandas'), (SELECT id FROM proveedores WHERE nombre='John Deere Partes'), 55000,82000,7,3 FROM dual;

-- ── Vehículos: autos (20) ──────────────────────────────────────────
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Toyota', 'Hilux', 2020, 2025, '2.7', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Toyota', 'Hilux', 2016, 2019, '2.7', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Toyota', 'Corolla', 2019, 2024, '1.8', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Toyota', 'Fortuner', 2018, 2024, '2.7', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Chevrolet', 'Spark', 2017, 2022, '1.2', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Chevrolet', 'Spark GT', 2015, 2020, '1.4', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Chevrolet', 'Aveo', 2014, 2020, '1.6', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Mazda', '3', 2017, 2023, '2.0', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Mazda', 'CX-5', 2018, 2024, '2.5', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Nissan', 'Sentra', 2016, 2021, '1.8', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Nissan', 'Frontier', 2017, 2023, '2.5', 'diesel');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Hyundai', 'Tucson', 2019, 2024, '2.0', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Hyundai', 'Accent', 2015, 2021, '1.6', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Kia', 'Rio', 2016, 2022, '1.6', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Kia', 'Sportage', 2018, 2024, '2.0', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Renault', 'Logan', 2018, 2023, '1.6', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Renault', 'Duster', 2019, 2024, '2.0', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Ford', 'Escape', 2013, 2019, '2.5', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Ford', 'Fiesta', 2014, 2019, '1.6', 'gasolina');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Suzuki', 'Swift', 2018, 2023, '1.2', 'gasolina');

-- ── Vehículos: maquinaria agrícola (7) ─────────────────────────────
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('John Deere', '5075E', 2016, 2024, '4.5', 'diesel');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('John Deere', '6110M', 2017, 2024, '4.5', 'diesel');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Case IH', 'Puma 165', 2015, 2023, '6.7', 'diesel');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Case IH', 'Farmall 75C', 2016, 2023, '3.4', 'diesel');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Massey Ferguson', '4707', 2017, 2024, '4.4', 'diesel');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('Massey Ferguson', '6713', 2016, 2023, '4.9', 'diesel');
INSERT INTO vehiculos (marca, modelo, anio_desde, anio_hasta, motor, combustible) VALUES ('New Holland', 'T6.120', 2016, 2024, '6.7', 'diesel');

-- ── Compatibilidad: autopartes ─────────────────────────────────────
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo = '90915-YZZD4' AND v.marca='Toyota' AND v.modelo='Hilux' AND v.anio_desde=2020;
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo = 'HP-1002' AND v.marca='Toyota' AND v.modelo='Hilux' AND v.anio_desde=2020;
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo = 'M1-102' AND v.marca='Toyota' AND v.modelo='Hilux' AND v.anio_desde=2020;
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo IN ('90915-YZZD4','HP-1002','M1-102') AND v.marca='Toyota' AND v.modelo='Fortuner';
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo IN ('BRM-FD204','BSH-0281') AND v.marca='Mazda' AND v.modelo IN ('3','CX-5');
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo = 'NGK-BKR6E' AND v.marca IN ('Kia','Hyundai') AND v.modelo IN ('Rio','Accent');
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo = 'MAC-48D' AND v.marca='Chevrolet' AND v.modelo IN ('Spark','Spark GT');
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo = 'GAT-T295' AND v.marca='Nissan' AND v.modelo='Sentra';
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo = 'BSH-ALT120' AND v.marca='Renault' AND v.modelo IN ('Logan','Duster');
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo = 'MNR-AM204' AND v.marca='Ford' AND v.modelo IN ('Escape','Fiesta');
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo = 'BSH-RAD330' AND v.marca='Hyundai' AND v.modelo='Tucson';
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo = 'MI-P205' AND v.marca='Suzuki' AND v.modelo='Swift';

-- ── Compatibilidad: maquinaria agrícola ────────────────────────────
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo IN ('JD-RE504836','JD-BAT31','JD-ENG3PT','JD-CORREA112') AND v.marca='John Deere' AND v.modelo='5075E';
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo IN ('FG-LF3970','JD-BAT31') AND v.marca='John Deere' AND v.modelo='6110M';
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo IN ('FG-FF5320','CIH-DISC88') AND v.marca='Case IH' AND v.modelo='Puma 165';
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo = 'CIH-FF7000' AND v.marca='Case IH' AND v.modelo IN ('Farmall 75C','Puma 165');
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo IN ('MF-FF6800','MF-BOMHID') AND v.marca='Massey Ferguson' AND v.modelo='4707';
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo = 'MF-BOMHID' AND v.marca='Massey Ferguson' AND v.modelo='6713';
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo = 'MI-AGR1846' AND v.marca IN ('John Deere','Case IH','Massey Ferguson','New Holland');
INSERT INTO repuesto_compatibilidad (repuesto_id, vehiculo_id)
SELECT r.id, v.id FROM repuestos r, vehiculos v WHERE r.codigo = 'FG-LF3970' AND v.marca='New Holland' AND v.modelo='T6.120';

COMMIT;

PROMPT Datos de prueba cargados correctamente.
