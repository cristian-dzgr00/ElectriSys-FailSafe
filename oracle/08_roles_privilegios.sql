-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 08. Roles de base de datos, perfil de contraseña y usuarios demo
-- Ejecutar conectado como ELECTRISYS (los GRANT sobre objetos propios
-- no requieren privilegios de sistema) salvo donde se indica SYSDBA.
--
-- Mapea 1:1 los 3 roles de negocio de la tabla ROLES (admin/vendedor/
-- dueño) a roles reales de la base de datos, con privilegios de objeto
-- distintos — no todo el mundo con acceso a la BD debe poder hacer lo
-- mismo, aunque la aplicación PHP use un único usuario de conexión.
-- ============================================================

-- ── Roles de base de datos ────────────────────────────────────────
CREATE ROLE rol_electrisys_admin;
CREATE ROLE rol_electrisys_vendedor;
CREATE ROLE rol_electrisys_dueno;

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
GRANT SELECT                         ON audit_log                 TO rol_electrisys_admin;
GRANT EXECUTE ON pkg_ventas   TO rol_electrisys_admin;
GRANT EXECUTE ON pkg_reportes TO rol_electrisys_admin;

-- ── VENDEDOR: opera el punto de venta, no administra catálogo ni ve auditoría ──
GRANT SELECT                    ON repuestos               TO rol_electrisys_vendedor;
GRANT SELECT                    ON categorias               TO rol_electrisys_vendedor;
GRANT SELECT                    ON proveedores              TO rol_electrisys_vendedor;
GRANT SELECT                    ON vehiculos                TO rol_electrisys_vendedor;
GRANT SELECT                    ON repuesto_compatibilidad  TO rol_electrisys_vendedor;
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
GRANT SELECT ON audit_log              TO rol_electrisys_dueno;
GRANT SELECT ON vw_ventas_detalle      TO rol_electrisys_dueno;
GRANT SELECT ON vw_repuestos_stock_bajo TO rol_electrisys_dueno;
GRANT SELECT ON vw_ventas_por_vendedor TO rol_electrisys_dueno;
GRANT EXECUTE ON pkg_reportes TO rol_electrisys_dueno;

PROMPT Roles ELECTRISYS creados y con privilegios asignados.
PROMPT ------------------------------------------------------------
PROMPT Lo que sigue (perfil de contraseña + CREATE USER) requiere
PROMPT privilegios de sistema: ejecutar conectado AS SYSDBA.
PROMPT ------------------------------------------------------------
