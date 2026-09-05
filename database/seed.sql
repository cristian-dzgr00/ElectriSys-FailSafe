-- ============================================================
-- ElectriSys POS - Datos de prueba
-- ============================================================
USE electrisys;

-- Admin y Vendedor: password = password
INSERT INTO usuarios (nombre, email, password, rol_id) VALUES
('Administrador', 'admin@electrisys.com', '$2y$10$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2.uheWG/igi', 1),
('Carlos Vendedor', 'vendedor@electrisys.com', '$2y$10$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2.uheWG/igi', 2);

INSERT INTO categorias (nombre) VALUES
('Cables y Conductores'),('Breakers'),('Tomacorrientes'),
('Iluminación'),('Herramientas'),('Motores'),('Transformadores');

INSERT INTO proveedores (nombre, contacto, telefono, email) VALUES
('ElectroDistribuidora Ltda', 'Pedro Ramírez', '3001234567', 'pedror@electrodist.com'),
('Schneider Electric Col', 'María López', '3109876543', 'mlopez@schneider.com'),
('ABB Colombia', 'Juan Torres', '3205551234', 'jtorres@abb.com');

INSERT INTO repuestos (codigo, nombre, categoria_id, proveedor_id, precio_compra, precio_venta, stock, stock_minimo) VALUES
('CAB-001', 'Cable THHN 12AWG (metro)', 1, 1, 1800, 2500, 500, 50),
('CAB-002', 'Cable THHN 10AWG (metro)', 1, 1, 2800, 3800, 300, 30),
('BRK-001', 'Breaker 1P 20A Schneider', 2, 2, 18000, 25000, 80, 10),
('BRK-002', 'Breaker 2P 30A Schneider', 2, 2, 32000, 45000, 40, 5),
('TOM-001', 'Tomacorriente doble polarizado', 3, 1, 4500, 7000, 120, 20),
('LMP-001', 'Bombillo LED 12W E27', 4, 3, 6000, 9500, 200, 25),
('HER-001', 'Destornillador aislado 1000V', 5, 3, 22000, 35000, 15, 3);

INSERT INTO clientes (nombre, identificacion, tipo_doc, telefono, email) VALUES
('Constructora Andina S.A.S', '900123456', 'NIT', '6012345678', 'compras@andina.com'),
('Luis Felipe Gómez', '1075234567', 'CC', '3156789012', 'lgomez@gmail.com'),
('Ferretería El Tornillo', '800987654', 'NIT', '6023456789', 'compras@eltornillo.com');
