-- ============================================================
-- ElectriSys - Configuración de Replicación MySQL
-- Ejecutar en el servidor PRIMARY
-- ============================================================

-- 1. Crear usuario replicador (en Primary)
CREATE USER IF NOT EXISTS 'replicator'@'%' IDENTIFIED WITH mysql_native_password BY 'ReplicaPass2024!';
GRANT REPLICATION SLAVE ON *.* TO 'replicator'@'%';
FLUSH PRIVILEGES;

-- 2. Ver status del Primary (File y Position actuales del binlog)
SHOW MASTER STATUS;

-- ============================================================
-- Lado REPLICA: automatizado
-- ============================================================
-- Ya NO hay que ejecutar CHANGE REPLICATION SOURCE / START REPLICA a mano.
-- El contenedor mysql-replica corre database/setup-replica.sh desde su
-- /docker-entrypoint-initdb.d/ la primera vez que se crea su volumen:
-- toma un snapshot consistente del primary (mysqldump --master-data=2),
-- lo importa y arranca la replicación exactamente en esa posición.
--
-- Verificar que está replicando:
--   docker exec es_mysql_replica \
--     mysql -uroot -prootpass2024 -e "SHOW REPLICA STATUS\G" \
--     | grep -E "Replica_(IO|SQL)_Running|Seconds_Behind_Source"
--
-- Se espera: Replica_IO_Running: Yes / Replica_SQL_Running: Yes
-- El healthcheck de docker-compose.yml comprueba justamente esto, así que
-- `docker compose ps` marca la réplica como unhealthy si deja de replicar.
--
-- Para rehacer la replicación desde cero (borra los datos de la réplica):
--   docker compose down && docker volume rm docker_mysql_replica_data

-- ============================================================
-- Job de sincronización: replicar registros con pendiente_sync=1
-- Ejecutar periódicamente desde un cron o worker K8s
-- ============================================================
-- UPDATE electrisys.ventas SET pendiente_sync = 0
-- WHERE pendiente_sync = 1;
-- (El worker PHP en backend se encarga de re-insertar en Primary)
