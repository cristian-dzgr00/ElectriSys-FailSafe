-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 01. Tablespace dedicado + usuario/esquema de la aplicación
-- Ejecutar conectado como SYSDBA, contra la PDB (freepdb1).
--
-- La contraseña del usuario llega como PARÁMETRO, no escrita acá: este
-- archivo está versionado en el repositorio y el repositorio se despliega.
--   sqlplus sys/<pass>@//localhost:1521/freepdb1 as sysdba --     @01_usuario_y_esquema.sql "LaContrasenaDeLaApp"
-- Sin el parámetro, SQL*Plus la pide por teclado (nunca queda en disco).
-- cargar_esquema.sh se la pasa desde $DB_PASS.
--
-- El script es RE-EJECUTABLE: si el tablespace o el usuario ya existen no
-- falla, solo avisa. Hace falta porque la imagen gvenzl/oracle-free crea el
-- usuario por su cuenta (APP_USER) antes de que este script corra, y porque
-- el procedimiento de recuperación ante desastre lo vuelve a ejecutar sobre
-- una base que puede estar a medio armar.
-- ============================================================

-- Conexiones SYSDBA vía bequeath (docker exec ... sqlplus / as sysdba) caen por
-- defecto en CDB$ROOT, no en la PDB, sin importar TWO_TASK/env del shell que
-- las invoque. Forzar el contenedor acá hace este script correcto sin
-- importar cómo se lo llame (cargar_esquema.sh, un docker exec suelto, etc).
ALTER SESSION SET CONTAINER = FREEPDB1;

SET VERIFY OFF
SET SERVEROUTPUT ON
DEFINE app_pass = &1

-- Tablespace propio (no usar SYSTEM/USERS para datos de aplicación)
DECLARE
    v_existe NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_existe FROM dba_tablespaces
     WHERE tablespace_name = 'ELECTRISYS_DATA';
    IF v_existe = 0 THEN
        EXECUTE IMMEDIATE 'CREATE TABLESPACE electrisys_data ' ||
            'DATAFILE ''/opt/oracle/oradata/electrisys_data01.dbf'' SIZE 200M ' ||
            'AUTOEXTEND ON NEXT 50M MAXSIZE 2G';
        DBMS_OUTPUT.PUT_LINE('Tablespace ELECTRISYS_DATA creado.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Tablespace ELECTRISYS_DATA ya existia, se conserva.');
    END IF;
END;
/

-- Usuario/esquema de la aplicación.
-- Si ya existe (lo creó la imagen de Docker, o es una recuperación sobre una
-- base a medio armar) no se recrea —eso borraría el esquema entero— pero sí
-- se le ajusta el tablespace y la cuota, que es lo que la imagen no define.
DECLARE
    v_existe NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_existe FROM dba_users WHERE username = 'ELECTRISYS';
    IF v_existe = 0 THEN
        EXECUTE IMMEDIATE 'CREATE USER electrisys IDENTIFIED BY "&app_pass" ' ||
            'DEFAULT TABLESPACE electrisys_data TEMPORARY TABLESPACE temp ' ||
            'QUOTA UNLIMITED ON electrisys_data';
        DBMS_OUTPUT.PUT_LINE('Usuario ELECTRISYS creado.');
    ELSE
        EXECUTE IMMEDIATE 'ALTER USER electrisys ' ||
            'DEFAULT TABLESPACE electrisys_data QUOTA UNLIMITED ON electrisys_data';
        DBMS_OUTPUT.PUT_LINE('Usuario ELECTRISYS ya existia: se conservo, con su tablespace ajustado.');
    END IF;
END;
/

-- Privilegios mínimos necesarios para que el dueño del esquema
-- pueda crear sus propios objetos (nada de DBA ni privilegios de sistema amplios)
GRANT CREATE SESSION   TO electrisys;
GRANT CREATE TABLE     TO electrisys;
GRANT CREATE VIEW      TO electrisys;
GRANT CREATE SEQUENCE  TO electrisys;
GRANT CREATE PROCEDURE TO electrisys;
GRANT CREATE TRIGGER   TO electrisys;
GRANT CREATE TYPE      TO electrisys;
GRANT CREATE ROLE      TO electrisys;

PROMPT Usuario ELECTRISYS listo. Conectate con:
PROMPT   sqlplus electrisys/<la contrasena>@//localhost:1521/freepdb1
