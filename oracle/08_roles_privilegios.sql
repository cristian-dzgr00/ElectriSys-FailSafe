-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 08. Roles de base de datos y sus privilegios
-- Ejecutar conectado como ELECTRISYS (los GRANT sobre objetos propios
-- no requieren privilegios de sistema), DESPUÉS de 02..07, 10..16.
--
-- Mapea 1:1 los 3 roles de negocio de la tabla ROLES (admin/vendedor/
-- dueño) a roles reales de la base de datos, con privilegios de objeto
-- distintos — no todo el mundo con acceso a la BD debe poder hacer lo
-- mismo, aunque la aplicación PHP use un único usuario de conexión.
--
-- Es RE-EJECUTABLE: si los roles ya existen (ORA-01921) se siguen usando, y
-- los GRANT repetidos no fallan. Los privilegios de las tablas y vistas de
-- los scripts 10 (pedidos), 15 y 16 (marcas, modelos, consulta_*,
-- vw_vehiculos, vw_totales_documento) se otorgan aquí: esos scripts corren
-- antes de que los roles existan en una carga desde cero.
-- ============================================================

-- ── Roles de base de datos ────────────────────────────────────────
BEGIN
    FOR r IN (SELECT column_value AS nombre
                FROM TABLE(sys.odcivarchar2list('rol_electrisys_admin',
                                                'rol_electrisys_vendedor',
                                                'rol_electrisys_dueno'))) LOOP
        BEGIN
            EXECUTE IMMEDIATE 'CREATE ROLE ' || r.nombre;
        EXCEPTION
            WHEN OTHERS THEN
                IF SQLCODE != -1921 THEN   -- ORA-01921: el rol ya existe
                    RAISE;
                END IF;
        END;
    END LOOP;
END;
/

-- ── ADMIN: control total sobre el esquema de la aplicación ────────
GRANT SELECT, INSERT, UPDATE, DELETE ON usuarios                 TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON roles                    TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON proveedores               TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON categorias                TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON repuestos                 TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON clientes                  TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON ventas                    TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON detalle_ventas            TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON cotizaciones              TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON detalle_cotizaciones      TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON vehiculos                 TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON repuesto_compatibilidad   TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON marcas                    TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON modelos                   TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON consulta_entidades        TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON consulta_recomendaciones  TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON pedidos                   TO rol_electrisys_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON pedido_detalle            TO rol_electrisys_admin;
GRANT SELECT                         ON audit_log                 TO rol_electrisys_admin;
GRANT SELECT ON vw_vehiculos          TO rol_electrisys_admin;
GRANT SELECT ON vw_totales_documento  TO rol_electrisys_admin;
GRANT EXECUTE ON pkg_ventas   TO rol_electrisys_admin;
GRANT EXECUTE ON pkg_reportes TO rol_electrisys_admin;

-- ── VENDEDOR: opera el punto de venta, no administra catálogo ni ve auditoría ──
GRANT SELECT                    ON repuestos               TO rol_electrisys_vendedor;
GRANT SELECT                    ON categorias               TO rol_electrisys_vendedor;
GRANT SELECT                    ON proveedores              TO rol_electrisys_vendedor;
GRANT SELECT                    ON vehiculos                TO rol_electrisys_vendedor;
GRANT SELECT                    ON repuesto_compatibilidad  TO rol_electrisys_vendedor;
GRANT SELECT                    ON marcas                   TO rol_electrisys_vendedor;
GRANT SELECT                    ON modelos                  TO rol_electrisys_vendedor;
GRANT SELECT                    ON vw_vehiculos             TO rol_electrisys_vendedor;
GRANT SELECT                    ON vw_totales_documento     TO rol_electrisys_vendedor;
GRANT SELECT, INSERT            ON clientes                 TO rol_electrisys_vendedor;
GRANT SELECT, INSERT            ON ventas                   TO rol_electrisys_vendedor;
GRANT SELECT, INSERT            ON detalle_ventas           TO rol_electrisys_vendedor;
GRANT SELECT, INSERT, UPDATE    ON cotizaciones             TO rol_electrisys_vendedor;
GRANT SELECT, INSERT            ON detalle_cotizaciones     TO rol_electrisys_vendedor;
GRANT EXECUTE ON pkg_ventas TO rol_electrisys_vendedor;
-- Nota: el vendedor NUNCA recibe UPDATE/DELETE directo sobre REPUESTOS.
-- El stock solo cambia vía trg_detven_descuenta_stock (al vender) o
-- por un ADMIN — así el DB refuerza la misma regla que ya aplica el
-- backend PHP a nivel de aplicación, pero sin depender de que el
-- cliente HTTP se comporte bien.
-- Pedidos a proveedor: el vendedor no recibe ningún privilegio (ni SELECT);
-- reabastecer no es parte de su operación.

-- ── DUEÑO: solo lectura + reportes gerenciales ────────────────────
GRANT SELECT ON usuarios               TO rol_electrisys_dueno;
GRANT SELECT ON proveedores            TO rol_electrisys_dueno;
GRANT SELECT ON categorias             TO rol_electrisys_dueno;
GRANT SELECT ON repuestos              TO rol_electrisys_dueno;
GRANT SELECT ON clientes               TO rol_electrisys_dueno;
GRANT SELECT ON ventas                 TO rol_electrisys_dueno;
GRANT SELECT ON detalle_ventas         TO rol_electrisys_dueno;
GRANT SELECT ON cotizaciones           TO rol_electrisys_dueno;
GRANT SELECT ON detalle_cotizaciones   TO rol_electrisys_dueno;
GRANT SELECT ON marcas                 TO rol_electrisys_dueno;
GRANT SELECT ON modelos                TO rol_electrisys_dueno;
GRANT SELECT ON consulta_entidades     TO rol_electrisys_dueno;
GRANT SELECT ON consulta_recomendaciones TO rol_electrisys_dueno;
GRANT SELECT ON audit_log              TO rol_electrisys_dueno;
GRANT SELECT ON vw_vehiculos           TO rol_electrisys_dueno;
GRANT SELECT ON vw_totales_documento   TO rol_electrisys_dueno;
GRANT SELECT ON vw_ventas_detalle      TO rol_electrisys_dueno;
GRANT SELECT ON vw_repuestos_stock_bajo TO rol_electrisys_dueno;
GRANT SELECT ON vw_ventas_por_vendedor TO rol_electrisys_dueno;
GRANT EXECUTE ON pkg_reportes TO rol_electrisys_dueno;
-- Pedidos: el DUEÑO también inserta y actualiza (autorizar una compra y darla
-- por recibida es una decisión gerencial). No recibe DELETE: un pedido se
-- cancela cambiando su estado, nunca se borra.
GRANT SELECT, INSERT, UPDATE ON pedidos        TO rol_electrisys_dueno;
GRANT SELECT, INSERT, UPDATE ON pedido_detalle TO rol_electrisys_dueno;

PROMPT Roles ELECTRISYS creados y con privilegios asignados.
PROMPT ------------------------------------------------------------
PROMPT Lo que sigue (perfil de contraseña + CREATE USER) requiere
PROMPT privilegios de sistema: ejecutar conectado AS SYSDBA.
PROMPT ------------------------------------------------------------
