-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 09. Perfil de contraseña + usuarios de demostración por rol
-- Ejecutar conectado AS SYSDBA (crear usuarios es un privilegio de sistema).
-- ============================================================

-- Igual que en 01_usuario_y_esquema.sql: forzar la PDB, no confiar en el
-- contenedor por defecto de la conexión SYSDBA.
ALTER SESSION SET CONTAINER = FREEPDB1;

-- Perfil con política de contraseña — vencimiento, bloqueo por intentos
-- fallidos y complejidad mínima (función estándar de Oracle).
CREATE PROFILE electrisys_profile LIMIT
    FAILED_LOGIN_ATTEMPTS   5
    PASSWORD_LOCK_TIME      1
    PASSWORD_LIFE_TIME      90
    PASSWORD_REUSE_TIME     365
    PASSWORD_VERIFY_FUNCTION ora12c_verify_function;

CREATE USER electrisys_admin_demo IDENTIFIED BY "AdminOra_2026!"
    DEFAULT TABLESPACE electrisys_data
    PROFILE electrisys_profile;
GRANT CREATE SESSION TO electrisys_admin_demo;

CREATE USER electrisys_vendedor_demo IDENTIFIED BY "VendedorOra_2026!"
    DEFAULT TABLESPACE electrisys_data
    PROFILE electrisys_profile;
GRANT CREATE SESSION TO electrisys_vendedor_demo;

CREATE USER electrisys_dueno_demo IDENTIFIED BY "DuenoOra_2026!"
    DEFAULT TABLESPACE electrisys_data
    PROFILE electrisys_profile;
GRANT CREATE SESSION TO electrisys_dueno_demo;

PROMPT Usuarios de demo creados. Ahora conectate como ELECTRISYS y ejecuta:
PROMPT   GRANT rol_electrisys_admin     TO electrisys_admin_demo;
PROMPT   GRANT rol_electrisys_vendedor  TO electrisys_vendedor_demo;
PROMPT   GRANT rol_electrisys_dueno     TO electrisys_dueno_demo;
PROMPT (el dueño de los objetos, ELECTRISYS, es quien puede conceder sus propios roles)
