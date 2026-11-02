#!/bin/bash
# ============================================================
# ElectriSys POS — vigilante liviano para la VM web de Oracle Cloud
#
# Corre por cron cada 30 minutos (ver oracle/docs/despliegue-oracle-cloud.md).
# Hace dos cosas, sin Prometheus ni Grafana (no caben en 1 GB de RAM):
#
#   1. Consulta /api/health. Ese endpoint ejecuta SQL contra Autonomous
#      Database, y Oracle detiene una Always Free tras 7 dias sin conexiones
#      SQL: este chequeo periodico reinicia ese contador.
#   2. Si la API no responde "ok", levanta de nuevo los contenedores y lo deja
#      escrito en el log. Tambien registra el estado del NLP (VM aparte).
#
# Variables opcionales: DOMINIO, NLP_HOST (se leen de docker/.env).
# ============================================================
set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="${VIGILANTE_LOG:-$HOME/electrisys/vigilante.log}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.oracle-web.yml)
SERVICIOS=(backend-a backend-b websocket-server frontend)

# Se leen solo las dos variables necesarias: el .env tiene secretos con
# caracteres que un `source` completo podria interpretar mal.
leer_env() { grep -E "^$1=" "$DIR/.env" 2>/dev/null | head -n1 | cut -d= -f2-; }
DOMINIO="${DOMINIO:-$(leer_env DOMINIO)}"; DOMINIO="${DOMINIO:-electrisys.duckdns.org}"
NLP_HOST="${NLP_HOST:-$(leer_env NLP_HOST)}"; NLP_HOST="${NLP_HOST:-10.0.0.11}"

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

api_ok() {
  # --resolve evita depender del DNS ni de salir a internet para llegar a si mismo
  curl -fsS -m 20 --resolve "$DOMINIO:443:127.0.0.1" "https://$DOMINIO/api/health" 2>/dev/null \
    | grep -q '"status": *"ok"'
}

if api_ok; then
  log "OK api+db"
else
  log "FALLO api: levantando contenedores"
  (cd "$DIR" && "${COMPOSE[@]}" up -d --no-build "${SERVICIOS[@]}" >> "$LOG" 2>&1)
  sleep 30
  if api_ok; then log "RECUPERADO tras reinicio"; else log "SIGUE CAIDO: requiere revision manual"; fi
fi

if curl -fsS -m 10 "http://$NLP_HOST:8000/health" >/dev/null 2>&1; then
  log "OK nlp"
else
  log "AVISO nlp no responde en $NLP_HOST:8000"
fi

# Rotacion simple: conservar las ultimas 1000 lineas
if [ "$(wc -l < "$LOG")" -gt 1000 ]; then tail -n 500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"; fi
