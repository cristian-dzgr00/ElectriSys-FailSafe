-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 10. Directory object para Data Pump (backup lógico del esquema)
-- Ejecutar conectado AS SYSDBA.
--
-- La ruta es SIEMPRE del lado del SERVIDOR de base de datos, no del
-- cliente que lanza expdp: Data Pump escribe el .dmp con el proceso de
-- Oracle. En el despliegue esto significa una ruta dentro del contenedor
-- oracle-db, montada como volumen persistente para que el backup
-- sobreviva a un `docker compose down` (ver docker/docker-compose.yml,
-- volumen oracle_backups).
--
-- La carpeta debe existir y pertenecer al usuario `oracle` (uid 54321 en
-- la imagen gvenzl/oracle-free). El volumen nombrado de Docker se crea
-- vacío y con permisos de root, así que el servicio de backup la ajusta
-- en su arranque — ver docker/docker-compose.backup.yml.
--
-- ── Equivalente en la máquina de desarrollo Windows (instancia nativa) ──
-- Si corrés Oracle instalado en Windows en vez del contenedor, la ruta es
-- otra y la carpeta tiene que ser accesible por la cuenta de servicio de
-- Oracle ("NT SERVICE\OracleServiceFREE"), NO una carpeta de OneDrive o
-- Documentos, que quedan restringidas al usuario de Windows:
--   mkdir C:\oracle_backups\electrisys
--   icacls C:\oracle_backups\electrisys /grant "NT SERVICE\OracleServiceFREE:(OI)(CI)F" /T
--   -- Igual que en 01_usuario_y_esquema.sql: forzar la PDB. Un DIRECTORY creado
-- en CDB$ROOT no es visible para una sesión conectada a FREEPDB1 (como la
-- app, o electrisys), así que esto también evita un ORA-29283/ORA-06564.
ALTER SESSION SET CONTAINER = FREEPDB1;

CREATE OR REPLACE DIRECTORY electrisys_backup_dir AS 'C:\oracle_backups\electrisys';
-- ============================================================

CREATE OR REPLACE DIRECTORY electrisys_backup_dir AS '/opt/oracle/backups/electrisys';
GRANT READ, WRITE ON DIRECTORY electrisys_backup_dir TO electrisys;

-- Data Pump crea una "master table" en el esquema que corre el export, así
-- que exige CREATE TABLE. 01_usuario_y_esquema.sql ya lo concede, pero se
-- repite acá a propósito: si la base se creó con el APP_USER de la imagen
-- gvenzl/oracle-free en vez de con ese script, el privilegio solo llega por
-- el rol DB_DEVELOPER_ROLE — y los roles NO se aplican dentro de un package
-- con derechos de definidor como PKG_BACKUP. El síntoma es un ORA-31626
-- ("job does not exist") al llamarlo desde la aplicación, mientras el mismo
-- bloque anónimo funciona desde SQL*Plus, donde el rol sí está activo.
GRANT CREATE TABLE TO electrisys;

PROMPT Directorio ELECTRISYS_BACKUP_DIR listo -> /opt/oracle/backups/electrisys
