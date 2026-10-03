-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 09. Perfil de contraseña + usuarios de demostración por rol
-- Ejecutar conectado AS SYSDBA (crear usuarios es un privilegio de sistema).
--
-- RE-EJECUTABLE: si el perfil o un usuario ya existen no falla; solo avisa
-- y conserva lo que hay (no recrea usuarios, para no tocar sus contraseñas).
-- ============================================================

-- Igual que en 01_usuario_y_esquema.sql: forzar la PDB, no confiar en el
-- contenedor por defecto de la conexión SYSDBA.
ALTER SESSION SET CONTAINER = FREEPDB1;
SET SERVEROUTPUT ON

-- Perfil con política de contraseña — vencimiento, bloqueo por intentos
-- fallidos y complejidad mínima (función estándar de Oracle).
DECLARE
    v_existe NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_existe FROM dba_profiles WHERE profile = 'ELECTRISYS_PROFILE';
    IF v_existe = 0 THEN
        EXECUTE IMMEDIATE 'CREATE PROFILE electrisys_profile LIMIT ' ||
            'FAILED_LOGIN_ATTEMPTS 5 PASSWORD_LOCK_TIME 1 PASSWORD_LIFE_TIME 90 ' ||
            'PASSWORD_REUSE_TIME 365 PASSWORD_VERIFY_FUNCTION ora12c_verify_function';
        DBMS_OUTPUT.PUT_LINE('Perfil ELECTRISYS_PROFILE creado.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Perfil ELECTRISYS_PROFILE ya existia, se conserva.');
    END IF;
END;
/

-- Un usuario de demostración por rol. Cada uno se crea solo si no existe.
DECLARE
    PROCEDURE crear(p_usuario VARCHAR2, p_clave VARCHAR2) IS
        v_existe NUMBER;
    BEGIN
        SELECT COUNT(*) INTO v_existe FROM dba_users WHERE username = UPPER(p_usuario);
        IF v_existe = 0 THEN
            EXECUTE IMMEDIATE 'CREATE USER ' || p_usuario || ' IDENTIFIED BY "' || p_clave || '" ' ||
                'DEFAULT TABLESPACE electrisys_data PROFILE electrisys_profile';
            DBMS_OUTPUT.PUT_LINE('Usuario ' || UPPER(p_usuario) || ' creado.');
        ELSE
            DBMS_OUTPUT.PUT_LINE('Usuario ' || UPPER(p_usuario) || ' ya existia, se conserva.');
        END IF;
        -- GRANT es idempotente: si ya lo tiene, no pasa nada.
        EXECUTE IMMEDIATE 'GRANT CREATE SESSION TO ' || p_usuario;
    END;
BEGIN
    crear('electrisys_admin_demo',    'AdminOra_2026!');
    crear('electrisys_vendedor_demo', 'VendedorOra_2026!');
    crear('electrisys_dueno_demo',    'DuenoOra_2026!');
END;
/

PROMPT Usuarios de demo listos. Ahora conectate como ELECTRISYS y ejecuta:
PROMPT   GRANT rol_electrisys_admin     TO electrisys_admin_demo;
PROMPT   GRANT rol_electrisys_vendedor  TO electrisys_vendedor_demo;
PROMPT   GRANT rol_electrisys_dueno     TO electrisys_dueno_demo;
PROMPT (el dueño de los objetos, ELECTRISYS, es quien puede conceder sus propios roles)
