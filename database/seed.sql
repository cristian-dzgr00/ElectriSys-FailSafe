-- ============================================================
-- ElectriSys POS - Datos de prueba
-- Categorías, proveedores y repuestos reales de autopartes y
-- maquinaria agrícola viven en seed_vehiculos.sql (se ejecuta después).
-- ============================================================
USE electrisys;

-- Admin y Vendedor: password = password
INSERT INTO usuarios (nombre, email, password, rol_id) VALUES
('Administrador', 'admin@electrisys.com', '$2y$10$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2.uheWG/igi', 1),
('Carlos Vendedor', 'vendedor@electrisys.com', '$2y$10$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2.uheWG/igi', 2);

INSERT INTO clientes (nombre, identificacion, tipo_doc, telefono, email) VALUES
('Constructora Andina S.A.S', '900123456', 'NIT', '6012345678', 'compras@andina.com'),
('Luis Felipe Gómez', '1075234567', 'CC', '3156789012', 'lgomez@gmail.com'),
('Ferretería El Tornillo', '800987654', 'NIT', '6023456789', 'compras@eltornillo.com'),
('Taller Mecánico El Motor', '900456123', 'NIT', '3011122334', 'contacto@elmotor.com'),
('Agropecuaria La Esperanza S.A.S', '900789456', 'NIT', '3122233445', 'compras@laesperanza.com'),
('Juan Carlos Restrepo', '80234567', 'CC', '3133344556', 'jcrestrepo@gmail.com'),
('Distribuidora de Repuestos del Valle', '900321654', 'NIT', '3144455667', 'ventas@repuestosvalle.com'),
('Finca San Isidro', '900654987', 'NIT', '3155566778', 'sanisidro@fincas.com'),
('María Fernanda Torres', '1032456789', 'CC', '3166677889', 'mftorres@gmail.com'),
('Talleres Unidos del Sur Ltda', '900987321', 'NIT', '3177788990', 'info@unidosdelsur.com'),
('Cooperativa Agrícola del Meta', '800112233', 'NIT', '3188899001', 'coopmeta@agro.com'),
('Pedro Antonio Gómez', '19345678', 'CC', '3199900112', 'pagomez@gmail.com');
