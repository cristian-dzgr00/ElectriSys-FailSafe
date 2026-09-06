-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 01. Tablespace dedicado + usuario/esquema de la aplicación
-- Ejecutar conectado como SYSDBA, contra la PDB (freepdb1)
--   sqlplus sys/<password>@localhost:1521/freepdb1 as sysdba @01_usuario_y_esquema.sql
-- ============================================================

-- Tablespace propio (no usar SYSTEM/USERS para datos de aplicación)
CREATE TABLESPACE electrisys_data
    DATAFILE 'electrisys_data01.dbf'
    SIZE 200M
    AUTOEXTEND ON NEXT 50M MAXSIZE 2G;

-- Usuario/esquema de la aplicación
CREATE USER electrisys IDENTIFIED BY "ElectriOra_2026!"
    DEFAULT TABLESPACE electrisys_data
    TEMPORARY TABLESPACE temp
    QUOTA UNLIMITED ON electrisys_data;

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

PROMPT Usuario ELECTRISYS creado. Conectate con:
PROMPT   sqlplus electrisys/ElectriOra_2026!@localhost:1521/freepdb1
