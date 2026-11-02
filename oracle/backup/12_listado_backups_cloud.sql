-- ============================================================
-- ElectriSys - Oracle Cloud (Autonomous AI Database)
-- backup/12. Permiso para listar los respaldos desde la aplicacion
-- Ejecutar conectado como ADMIN (una sola vez).
--
-- Por que: en Autonomous Database el directorio ELECTRISYS_BACKUP_DIR vive
-- en el servidor de la base, no en el contenedor del backend. La pantalla
-- Respaldos lista los .dmp con DBMS_CLOUD.LIST_FILES, que el usuario
-- ELECTRISYS no puede ejecutar por defecto. Sin este permiso el listado
-- sale vacio con el aviso "No se pudo leer el listado de respaldos".
-- ============================================================
GRANT EXECUTE ON DBMS_CLOUD TO electrisys;

PROMPT Permiso sobre DBMS_CLOUD concedido a ELECTRISYS.
