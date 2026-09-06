-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 03. Índices de rendimiento (equivalentes a los de MySQL schema.sql)
-- Ejecutar conectado como ELECTRISYS.
-- ============================================================

CREATE INDEX idx_ventas_fecha            ON ventas(creado_en);
CREATE INDEX idx_ventas_cliente          ON ventas(cliente_id);
CREATE INDEX idx_ventas_estado           ON ventas(estado);
CREATE INDEX idx_repuestos_stock         ON repuestos(stock);
-- idx_repuestos_codigo / idx_clientes_identificacion NO se crean aparte:
-- ya tienen un índice único implícito por las constraints
-- uq_repuestos_codigo / uq_clientes_identificacion (02_ddl_tablas.sql).
-- A diferencia de MySQL, en Oracle crear otro índice sobre las mismas
-- columnas da ORA-01408 ("esta lista de columnas ya está indexada").

-- Índice compuesto: acelera el JOIN venta_id+repuesto_id en reportes y cálculo de totales
CREATE INDEX idx_detven_venta_repuesto ON detalle_ventas(venta_id, repuesto_id);

-- Índices del módulo de vehículos/compatibilidad (asistente NLP)
CREATE INDEX idx_vehiculos_marca_modelo ON vehiculos(marca, modelo);
CREATE INDEX idx_vehiculos_anios        ON vehiculos(anio_desde, anio_hasta);
CREATE INDEX idx_compat_repuesto        ON repuesto_compatibilidad(repuesto_id);
CREATE INDEX idx_compat_vehiculo        ON repuesto_compatibilidad(vehiculo_id);

-- Auditoría y rate limiting
CREATE INDEX idx_audit_usuario     ON audit_log(usuario_id);
CREATE INDEX idx_audit_accion      ON audit_log(accion);
CREATE INDEX idx_audit_fecha       ON audit_log(created_at);
CREATE INDEX idx_attempts_ip_fecha ON login_attempts(ip, created_at);
CREATE INDEX idx_consultas_usuario   ON consultas_asistente(usuario_id);
CREATE INDEX idx_consultas_intencion ON consultas_asistente(intencion_detectada);

PROMPT Indices creados correctamente.
