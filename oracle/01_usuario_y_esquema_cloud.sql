-- ============================================================
-- ElectriSys - Oracle Cloud (Autonomous AI Database)
-- 01. Usuario/esquema de la aplicacion
-- Ejecutar conectado como ADMIN. Recibe la clave de ELECTRISYS como parametro:
--   @01_usuario_y_esquema_cloud.sql "LaClaveDeLaApp"
-- Diferencias con 01_usuario_y_esquema.sql (Docker): sin SYSDBA, sin
-- ALTER SESSION SET CONTAINER y sin CREATE TABLESPACE con datafile; en
-- Autonomous el almacenamiento lo administra Oracle (tablespace DATA).
-- Re-ejecutable: si el usuario existe, solo ajusta la cuota.
-- ============================================================
SET VERIFY OFF
SET SERVEROUTPUT ON
DEFINE app_pass = &1

DECLARE
    v_existe NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_existe FROM dba_users WHERE username = 'ELECTRISYS';
    IF v_existe = 0 THEN
        EXECUTE IMMEDIATE 'CREATE USER electrisys IDENTIFIED BY "&app_pass" ' ||
            'QUOTA UNLIMITED ON data';
        DBMS_OUTPUT.PUT_LINE('Usuario ELECTRISYS creado.');
    ELSE
        EXECUTE IMMEDIATE 'ALTER USER electrisys QUOTA UNLIMITED ON data';
        DBMS_OUTPUT.PUT_LINE('Usuario ELECTRISYS ya existia: se conservo, con la cuota ajustada.');
    END IF;
END;
/

GRANT CREATE SESSION   TO electrisys;
GRANT CREATE TABLE     TO electrisys;
GRANT CREATE VIEW      TO electrisys;
GRANT CREATE SEQUENCE  TO electrisys;
GRANT CREATE PROCEDURE TO electrisys;
GRANT CREATE TRIGGER   TO electrisys;
GRANT CREATE TYPE      TO electrisys;
GRANT CREATE ROLE      TO electrisys;

PROMPT Usuario ELECTRISYS listo.
