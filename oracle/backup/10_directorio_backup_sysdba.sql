-- ============================================================
-- ElectriSys — Migración a Oracle 23ai
-- 10. Directory object para Data Pump (backup lógico del esquema)
-- Ejecutar conectado AS SYSDBA.
--
-- La carpeta del sistema operativo debe existir de antemano y ser
-- accesible por la cuenta de servicio de Oracle (en Windows,
-- "NT SERVICE\OracleServiceFREE" por defecto) — por eso NO se usa una
-- carpeta dentro de OneDrive/Documentos: esas quedan restringidas al
-- usuario de Windows y el servicio de Oracle no puede leerlas/escribirlas.
--   mkdir C:\oracle_backups\electrisys
--   icacls C:\oracle_backups\electrisys /grant "NT SERVICE\OracleServiceFREE:(OI)(CI)F" /T
-- ============================================================

CREATE OR REPLACE DIRECTORY electrisys_backup_dir AS 'C:\oracle_backups\electrisys';
GRANT READ, WRITE ON DIRECTORY electrisys_backup_dir TO electrisys;

PROMPT Directorio ELECTRISYS_BACKUP_DIR listo -> C:\oracle_backups\electrisys
