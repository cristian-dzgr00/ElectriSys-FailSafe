#!/usr/bin/env bash
# ============================================================
# setup-wireguard.sh — instala y configura WireGuard en Ubuntu
# Ejecutar como root en el servidor gateway del cluster.
# ============================================================
set -euo pipefail

VPN_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[ElectriSys VPN] Instalando WireGuard..."
apt-get update -qq
apt-get install -y wireguard wireguard-tools

# ── Generar claves del servidor ───────────────────────────────
echo "[ElectriSys VPN] Generando claves del servidor..."
mkdir -p /etc/wireguard
wg genkey | tee /etc/wireguard/server_private.key | wg pubkey > /etc/wireguard/server_public.key
chmod 600 /etc/wireguard/server_private.key

SERVER_PRIVATE=$(cat /etc/wireguard/server_private.key)
SERVER_PUBLIC=$(cat /etc/wireguard/server_public.key)

echo "[✓] Clave pública del servidor: $SERVER_PUBLIC"

# ── Generar clave para primer cliente ─────────────────────────
wg genkey | tee /etc/wireguard/client1_private.key | wg pubkey > /etc/wireguard/client1_public.key
chmod 600 /etc/wireguard/client1_private.key

CLIENT1_PRIVATE=$(cat /etc/wireguard/client1_private.key)
CLIENT1_PUBLIC=$(cat /etc/wireguard/client1_public.key)

# ── Construir wg0.conf con las claves reales ──────────────────
sed "s|<SERVER_PRIVATE_KEY>|$SERVER_PRIVATE|g" "$VPN_DIR/wg0.conf" \
  | sed "s|<CLIENT1_PUBLIC_KEY>|$CLIENT1_PUBLIC|g" \
  > /etc/wireguard/wg0.conf
chmod 600 /etc/wireguard/wg0.conf

# ── Habilitar IP forwarding ───────────────────────────────────
echo "net.ipv4.ip_forward = 1" >> /etc/sysctl.conf
sysctl -p

# ── Iniciar WireGuard ─────────────────────────────────────────
systemctl enable wg-quick@wg0
systemctl start  wg-quick@wg0

echo ""
echo "[✓] WireGuard activo en puerto 51820"
echo "[✓] Red VPN: 10.100.0.0/24"
echo ""
echo "== Configuración para el cliente 1 =="
sed "s|<CLIENT_PRIVATE_KEY>|$CLIENT1_PRIVATE|g" "$VPN_DIR/client-template.conf" \
  | sed "s|<SERVER_PUBLIC_KEY>|$SERVER_PUBLIC|g" \
  | sed "s|<SERVER_IP>|$(curl -s ifconfig.me)|g" \
  | sed "s|<CLUSTER_SUBNET>|10.0.0.0|g" \
  | sed "s|10.100.0.X|10.100.0.2|g"
