#!/usr/bin/env bash
# ============================================================
# capture-api.sh — captura peticiones REST a /api/*
# Muestra headers HTTP completos, Authorization JWT y tiempos.
# ============================================================
set -euo pipefail

CAPTURES_DIR="$(cd "$(dirname "$0")/../captures" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTFILE="$CAPTURES_DIR/api_$TIMESTAMP.pcap"

INTERFACE="${1:-lo}"
DURATION="${2:-60}"

mkdir -p "$CAPTURES_DIR"

echo "[ElectriSys] Capturando API REST por ${DURATION}s en $INTERFACE..."
echo "[ElectriSys] Salida: $OUTFILE"
echo ""

sudo tcpdump -i "$INTERFACE" -w "$OUTFILE" -s 0 "tcp port 80" \
  -G "$DURATION" -W 1 2>/dev/null || true

echo "[✓] Captura completa"
echo ""
echo "── Resumen de rutas capturadas ─────────────────────────────"
tshark -r "$OUTFILE" \
  -Y "http.request" \
  -T fields \
  -e frame.time_relative \
  -e http.request.method \
  -e http.request.uri \
  -e http.response.code \
  -E separator="|" \
  -E header=y 2>/dev/null | column -t -s"|" || true

echo ""
echo "── Headers de seguridad en respuestas ──────────────────────"
tshark -r "$OUTFILE" \
  -Y "http.response" \
  -T fields \
  -e http.response.code \
  -e http.x_content_type_options \
  -e http.x_frame_options \
  -e http.strict_transport_security \
  -E header=y 2>/dev/null || true
