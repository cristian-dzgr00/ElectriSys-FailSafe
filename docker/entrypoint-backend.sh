#!/bin/sh
# ============================================================
# entrypoint-backend.sh
# Arranca stunnel (mTLS listener en 9443) y luego PHP-FPM.
# Si los certificados no existen, arranca solo PHP-FPM (dev).
# ============================================================
set -e

TLS_CONF="/etc/stunnel/stunnel.conf"

if [ -f "$TLS_CONF" ] && [ -f "/etc/tls/php-fpm/php-fpm.crt" ]; then
    echo "[EntryPoint] Iniciando stunnel mTLS listener..."
    stunnel "$TLS_CONF" &
    echo "[EntryPoint] stunnel PID: $!"
else
    echo "[EntryPoint] AVISO: Certificados TLS no encontrados — PHP-FPM sin mTLS (solo dev)"
fi

echo "[EntryPoint] Iniciando PHP-FPM..."
exec php-fpm
