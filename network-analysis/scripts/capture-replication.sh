#!/usr/bin/env bash
# ============================================================
# capture-replication.sh — replicación MySQL Primary→Replica
# Captura los eventos de binlog: WRITE_ROWS, UPDATE_ROWS,
# DELETE_ROWS, QUERY_EVENT para ver la sincronización.
# ============================================================
set -euo pipefail

CAPTURES_DIR="$(cd "$(dirname "$0")/../captures" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTFILE="$CAPTURES_DIR/replication_$TIMESTAMP.pcap"

INTERFACE="${1:-lo}"
DURATION="${2:-60}"
PRIMARY_PORT=3306
REPLICA_PORT=3307   # en docker-compose el replica mapea al 3307

mkdir -p "$CAPTURES_DIR"

echo "[ElectriSys] Capturando replicación MySQL por ${DURATION}s..."
echo "[ElectriSys] Genera una venta en la app para ver eventos binlog"
echo ""

sudo tcpdump -i "$INTERFACE" -w "$OUTFILE" -s 0 \
  "tcp port $PRIMARY_PORT or tcp port $REPLICA_PORT" \
  -G "$DURATION" -W 1 2>/dev/null || true

echo "[✓] Captura completa"
echo ""
echo "── Eventos de replicación binlog ───────────────────────────"
tshark -r "$OUTFILE" \
  -Y "mysql.binlog.event_type" \
  -T fields \
  -e frame.time_relative \
  -e ip.src \
  -e ip.dst \
  -e mysql.binlog.event_type \
  -E header=y 2>/dev/null || echo "Requiere tshark con disector MySQL binlog"

echo ""
echo "── Bytes transferidos Primary→Replica ───────────────────────"
tshark -r "$OUTFILE" \
  -q \
  -z "conv,tcp,tcp.port==$PRIMARY_PORT" 2>/dev/null || true
