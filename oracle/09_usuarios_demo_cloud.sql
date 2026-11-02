-- ============================================================
-- ElectriSys - Oracle Cloud (Autonomous AI Database)
-- 09. Perfil de contrasena + usuarios de demostracion por rol
-- Ejecutar conectado como ADMIN.
-- Diferencias con 09_usuarios_demo_sysdba.sql: sin ALTER SESSION SET
-- CONTAINER, sin tablespace explicito (se usa DATA por defecto) y sin
-- ora12c_verify_function (Autonomous ya aplica su propia complejidad de
-- clave). Si el perfil no se puede crear, los usuarios usan el perfil DEFAULT.
-- Re-ejecutable.
-- ============================================================
SET SERVEROUTPUT ON

DECLARE
    v_perfil VARCHAR2(30) := 'DEFAULT';

    PROCEDURE crear(p_usuario VARCHAR2, p_clave VARCHAR2) IS
        v_existe NUMBER;
    BEGIN
        SELECT COUNT(*) INTO v_existe FROM dba_users WHERE username = UPPER(p_usuario);
        IF v_existe = 0 THEN
            EXECUTE IMMEDIATE 'CREATE USER ' || p_usuario || ' IDENTIFIED BY "' || p_clave ||
                '" PROFILE ' || v_perfil;
            DBMS_OUTPUT.PUT_LINE('Usuario ' || UPPER(p_usuario) || ' creado.');
        ELSE
            DBMS_OUTPUT.PUT_LINE('Usuario ' || UPPER(p_usuario) || ' ya existia, se conserva.');
        END IF;
        EXECUTE IMMEDIATE 'GRANT CREATE SESSION TO ' || p_usuario;
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_OUTPUT.PUT_LINE('ERROR con ' || UPPER(p_usuario) || ': ' || SQLERRM);
    END;
BEGIN
    DECLARE
        v_existe NUMBER;
    BEGIN
        SELECT COUNT(*) INTO v_existe FROM dba_profiles WHERE profile = 'ELECTRISYS_PROFILE';
        IF v_existe = 0 THEN
            EXECUTE IMMEDIATE 'CREATE PROFILE electrisys_profile LIMIT ' ||
                'FAILED_LOGIN_ATTEMPTS 5 PASSWORD_LOCK_TIME 1 PASSWORD_LIFE_TIME 90 ' ||
                'PASSWORD_REUSE_TIME 365';
            DBMS_OUTPUT.PUT_LINE('Perfil ELECTRISYS_PROFILE creado.');
        ELSE
            DBMS_OUTPUT.PUT_LINE('Perfil ELECTRISYS_PROFILE ya existia, se conserva.');
        END IF;
        v_perfil := 'ELECTRISYS_PROFILE';
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_OUTPUT.PUT_LINE('No se pudo crear el perfil (' || SQLERRM || '); se usa DEFAULT.');
    END;

    crear('electrisys_admin_demo',    'AdminOra_2026!');
    crear('electrisys_vendedor_demo', 'VendedorOra_2026!');
    crear('electrisys_dueno_demo',    'DuenoOra_2026!');
END;
/

PROMPT Usuarios de demo listos. Conectado como ELECTRISYS, ejecuta:
PROMPT   GRANT rol_electrisys_admin     TO electrisys_admin_demo;
PROMPT   GRANT rol_electrisys_vendedor  TO electrisys_vendedor_demo;
PROMPT   GRANT rol_electrisys_dueno     TO electrisys_dueno_demo;
