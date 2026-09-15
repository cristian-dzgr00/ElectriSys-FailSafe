#!/bin/bash
# ============================================================
# ElectriSys — Configuración automática de la réplica MySQL
#
# Se ejecuta una sola vez, desde /docker-entrypoint-initdb.d/ del
# contenedor mysql-replica, la primera vez que se crea su volumen.
#
# Método (snapshot consistente + posición exacta del binlog):
#   1. Espera a que el primary acepte conexiones.
#   2. mysqldump --single-transaction --master-data=2 toma una copia
#      consistente de la BD y anota en qué punto del binlog quedó.
#   3. Importa esa copia en la réplica.
#   4. Arranca la replicación EXACTAMENTE desde esa posición, de modo
#      que no se reaplican las sentencias ya incluidas en el snapshot
#      (que causarían errores de "database/user already exists").
# ============================================================
set -euo pipefail

PRIMARY_HOST="${REPLICATION_SOURCE_HOST:-mysql-primary}"
REPL_USER="${REPLICATION_USER:-replicator}"
REPL_PASS="${REPLICATION_PASSWORD:-ReplicaPass2024!}"
ROOT_PASS="${MYSQL_ROOT_PASSWORD}"
DB_NAME="${MYSQL_DATABASE:-electrisys}"
SNAPSHOT="/tmp/primary-snapshot.sql"

log() { echo "[ElectriSys][replica] $*"; }

# ── 1. Esperar al primary ────────────────────────────────────
log "Esperando a que ${PRIMARY_HOST} acepte conexiones..."
for intento in $(seq 1 60); do
    if mysql -h "$PRIMARY_HOST" -u root -p"$ROOT_PASS" -e "SELECT 1" >/dev/null 2>&1; then
        log "Primary disponible (intento ${intento})."
        break
    fi
    if [ "$intento" -eq 60 ]; then
        log "ERROR: ${PRIMARY_HOST} no respondió tras 120s. Replicación NO configurada."
        exit 1
    fi
    sleep 2
done

# ── 2. Snapshot consistente + posición del binlog ────────────
log "Tomando snapshot de '${DB_NAME}' desde el primary..."
mysqldump -h "$PRIMARY_HOST" -u root -p"$ROOT_PASS" \
    --single-transaction \
    --master-data=2 \
    --routines --triggers --events \
    --databases "$DB_NAME" > "$SNAPSHOT"

MASTER_LINE=$(grep -m1 "^-- CHANGE MASTER TO MASTER_LOG_FILE=" "$SNAPSHOT" || true)
if [ -z "$MASTER_LINE" ]; then
    log "ERROR: el snapshot no incluye la posición del binlog."
    log "       Verifica que el primary tenga --log-bin habilitado."
    exit 1
fi

LOG_FILE=$(echo "$MASTER_LINE" | sed -n "s/.*MASTER_LOG_FILE='\([^']*\)'.*/\1/p")
LOG_POS=$(echo  "$MASTER_LINE" | sed -n "s/.*MASTER_LOG_POS=\([0-9]*\).*/\1/p")
log "Snapshot tomado en ${LOG_FILE}:${LOG_POS}"

# ── 3. Importar el snapshot en la réplica ────────────────────
log "Importando snapshot..."
mysql -u root -p"$ROOT_PASS" < "$SNAPSHOT"
rm -f "$SNAPSHOT"

# ── 4. Enganchar la replicación desde esa posición ───────────
log "Configurando replicación desde ${PRIMARY_HOST}..."
mysql -u root -p"$ROOT_PASS" <<SQL
CHANGE REPLICATION SOURCE TO
    SOURCE_HOST     = '${PRIMARY_HOST}',
    SOURCE_USER     = '${REPL_USER}',
    SOURCE_PASSWORD = '${REPL_PASS}',
    SOURCE_LOG_FILE = '${LOG_FILE}',
    SOURCE_LOG_POS  = ${LOG_POS};
START REPLICA;
SQL

log "Replicación iniciada. Verifica con: SHOW REPLICA STATUS\\G"
