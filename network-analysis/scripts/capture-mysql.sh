#!/usr/bin/env bash
# ============================================================
# capture-mysql.sh — protocolo wire de MySQL
# Captura queries SQL, handshake de autenticación y respuestas.
# IMPORTANTE: antes de activar mTLS, las queries viajan en
# texto plano — puedes leerlas directamente aquí.
# ============================================================
set -euo pipefail

CAPTURES_DIR="$(cd "$(dirname "$0")/../captures" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTFILE="$CAPTURES_DIR/mysql_$TIMESTAMP.pcap"

INTERFACE="${1:-lo}"
MYSQL_PORT="${2:-3306}"
DURATION="${3:-30}"

mkdir -p "$CAPTURES_DIR"

echo "[ElectriSys] Capturando tráfico MySQL en $INTERFACE:$MYSQL_PORT por ${DURATION}s"
echo "[ElectriSys] Salida: $OUTFILE"
echo ""

sudo tcpdump -i "$INTERFACE" -w "$OUTFILE" -s 0 "tcp port $MYSQL_PORT" \
  -G "$DURATION" -W 1 2>/dev/null || true

echo "[✓] Captura completa"
echo ""
echo "── Queries SQL capturadas (texto plano pre-mTLS) ───────────"
# El disector MySQL de tshark extrae las queries del payload
tshark -r "$OUTFILE" \
  -Y "mysql.query" \
  -T fields \
  -e frame.time_relative \
  -e ip.src \
  -e mysql.query \
  -E header=y 2>/dev/null || echo "Requiere tshark con disector MySQL"

echo ""
echo "── Handshake de autenticación MySQL ─────────────────────────"
tshark -r "$OUTFILE" \
  -Y "mysql.caps_server" \
  -T fields \
  -e frame.time_relative \
  -e mysql.server_greeting.server_version \
  -e mysql.caps_server \
  -E header=y 2>/dev/null || true

echo ""
echo "NOTA: Tras activar mTLS (TLS session), las queries aparecerán"
echo "como 'Application Data' cifrado — no readable. Ese es el objetivo."
