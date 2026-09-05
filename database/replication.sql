-- ============================================================
-- ElectriSys - Configuración de Replicación MySQL
-- Ejecutar en el servidor PRIMARY
-- ============================================================

-- 1. Crear usuario replicador (en Primary)
CREATE USER IF NOT EXISTS 'replicator'@'%' IDENTIFIED WITH mysql_native_password BY 'ReplicaPass2024!';
GRANT REPLICATION SLAVE ON *.* TO 'replicator'@'%';
FLUSH PRIVILEGES;

-- 2. Ver status del Primary (guardar File y Position para configurar Replica)
SHOW MASTER STATUS;

-- ============================================================
-- Ejecutar en el servidor REPLICA
-- ============================================================

-- 3. Configurar conexión al Primary (reemplazar File y Position con los valores de arriba)
-- CHANGE MASTER TO
--   MASTER_HOST='mysql-primary',
--   MASTER_USER='replicator',
--   MASTER_PASSWORD='ReplicaPass2024!',
--   MASTER_LOG_FILE='binlog.000001',
--   MASTER_LOG_POS=0;

-- 4. Iniciar replicación
-- START SLAVE;
-- SHOW SLAVE STATUS\G

-- ============================================================
-- Job de sincronización: replicar registros con pendiente_sync=1
-- Ejecutar periódicamente desde un cron o worker K8s
-- ============================================================
-- UPDATE electrisys.ventas SET pendiente_sync = 0
-- WHERE pendiente_sync = 1;
-- (El worker PHP en backend se encarga de re-insertar en Primary)
