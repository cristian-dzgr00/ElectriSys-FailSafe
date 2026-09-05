#!/usr/bin/env bash
# ============================================================
# capture-login.sh — captura el flujo TCP completo de un login
#
# Muestra:
#  - Three-way handshake (SYN, SYN-ACK, ACK)
#  - Request HTTP POST /api/auth/login con el body JSON
#  - Response con el JWT en el campo "token"
#  - FIN/ACK del cierre de conexión
#
# Uso: sudo ./network-analysis/scripts/capture-login.sh
# ============================================================
set -euo pipefail

CAPTURES_DIR="$(cd "$(dirname "$0")/../captures" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTFILE="$CAPTURES_DIR/login_$TIMESTAMP.pcap"

INTERFACE="${1:-lo}"       # interfaz: lo para docker local, eth0 para VM
NGINX_PORT="${2:-80}"
DURATION="${3:-30}"        # segundos de captura

mkdir -p "$CAPTURES_DIR"

echo "[ElectriSys] Capturando tráfico de login en $INTERFACE:$NGINX_PORT"
echo "[ElectriSys] Guardando en $OUTFILE (duración: ${DURATION}s)"
echo "[ElectriSys] Abre otra terminal y ejecuta un login para capturar"
echo ""

# Capturar solo tráfico HTTP al endpoint de login
sudo tcpdump \
  -i "$INTERFACE" \
  -w "$OUTFILE" \
  -s 0 \
  "tcp port $NGINX_PORT and (tcp[tcpflags] & (tcp-syn|tcp-fin) != 0 or (port $NGINX_PORT))" \
  -G "$DURATION" -W 1 2>/dev/null || true

echo ""
echo "[✓] Captura guardada: $OUTFILE"
echo ""
echo "── Análisis rápido con tshark ──────────────────────────────"

# Mostrar el handshake TCP
echo ""
echo "Handshake TCP (SYN, SYN-ACK, ACK):"
tshark -r "$OUTFILE" \
  -Y "tcp.flags.syn==1 or tcp.flags.fin==1" \
  -T fields \
  -e frame.time_relative \
  -e ip.src \
  -e ip.dst \
  -e tcp.flags.syn \
  -e tcp.flags.ack \
  -e tcp.flags.fin \
  -E header=y 2>/dev/null || echo "Instalar tshark: apt install tshark"

# Mostrar el payload HTTP
echo ""
echo "Petición HTTP POST /api/auth/login:"
tshark -r "$OUTFILE" \
  -Y "http.request.method == POST" \
  -T fields \
  -e http.request.method \
  -e http.request.uri \
  -e http.authorization \
  -e http.file_data \
  -E header=y 2>/dev/null || true

echo ""
echo "Abre el .pcap en Wireshark con: wireshark -r $OUTFILE"
