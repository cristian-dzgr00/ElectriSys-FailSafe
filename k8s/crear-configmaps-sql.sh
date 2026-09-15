#!/bin/bash
# ============================================================
# Genera los ConfigMaps con los scripts de inicialización de MySQL.
#
# POR QUÉ HACE FALTA
# ------------------
# mysql-primary.yaml solo montaba el PVC y su my.cnf: no cargaba ningún
# .sql, así que en Kubernetes la base arrancaba SIN TABLAS (en
# docker-compose sí se montan vía volumes). Y sin replication.sql tampoco
# existía el usuario 'replicator', por lo que la réplica no tenía con qué
# engancharse al primary.
#
# Se generan desde database/*.sql en vez de copiar el SQL dentro de un
# YAML: así hay una sola fuente de verdad y no se desincronizan.
#
# Ejecutar ANTES de aplicar los manifiestos:
#     ./k8s/crear-configmaps-sql.sh
#     kubectl apply -f k8s/
# ============================================================
set -euo pipefail

NS="electrisys"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

echo "==> ConfigMap mysql-init-sql (esquema + seeds + usuario de replicación)"
# Los nombres llevan prefijo numérico: la imagen de MySQL ejecuta los
# archivos de /docker-entrypoint-initdb.d en orden alfabético.
kubectl create configmap mysql-init-sql \
    --namespace "$NS" \
    --from-file=01-schema.sql="$DIR/database/schema.sql" \
    --from-file=02-seed.sql="$DIR/database/seed.sql" \
    --from-file=03-replication.sql="$DIR/database/replication.sql" \
    --from-file=04-schema-v3-nlp.sql="$DIR/database/schema_v3_migration_nlp.sql" \
    --from-file=05-seed-vehiculos.sql="$DIR/database/seed_vehiculos.sql" \
    --dry-run=client -o yaml | kubectl apply -f -

echo "==> ConfigMap mysql-replica-init (engancha la réplica al primary)"
kubectl create configmap mysql-replica-init \
    --namespace "$NS" \
    --from-file=01-setup-replica.sh="$DIR/database/setup-replica.sh" \
    --dry-run=client -o yaml | kubectl apply -f -

echo
echo "Listo. Ahora: kubectl apply -f k8s/"
