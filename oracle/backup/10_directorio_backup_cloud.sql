-- ============================================================
-- ElectriSys - Oracle Cloud (Autonomous AI Database)
-- backup/10. Directory object para Data Pump
-- Ejecutar conectado como ADMIN.
-- En Autonomous la ruta es un nombre relativo dentro del servidor de la
-- base (no hay /opt/oracle ni C:\). Los .dmp quedan ahi; para sacarlos hay
-- que copiarlos a Object Storage con DBMS_CLOUD.PUT_OBJECT.
-- ============================================================
CREATE OR REPLACE DIRECTORY electrisys_backup_dir AS 'electrisys_backup';
GRANT READ, WRITE ON DIRECTORY electrisys_backup_dir TO electrisys;
GRANT CREATE TABLE TO electrisys;

PROMPT Directorio ELECTRISYS_BACKUP_DIR listo.
