#!/usr/bin/env bash
# ============================================================
# generate-certs.sh — PKI interna para ElectriSys mTLS
#
# Genera:
#   tls/ca/          → CA raíz propia
#   tls/nginx/       → certificado para Nginx (cliente de PHP-FPM)
#   tls/php-fpm/     → certificado para PHP-FPM (servidor)
#   tls/mysql/       → certificado para MySQL
#
# Uso:
#   chmod +x tls/generate-certs.sh
#   ./tls/generate-certs.sh
# ============================================================
set -euo pipefail

CERTS_DIR="$(cd "$(dirname "$0")" && pwd)"
DAYS=825   # máximo aceptado por Chrome/iOS

echo "[ElectriSys TLS] Generando PKI interna..."

# ── 1. Crear CA raíz ──────────────────────────────────────────
mkdir -p "$CERTS_DIR/ca"
openssl genrsa -out "$CERTS_DIR/ca/ca.key" 4096

openssl req -new -x509 -days $DAYS \
  -key "$CERTS_DIR/ca/ca.key" \
  -out "$CERTS_DIR/ca/ca.crt" \
  -subj "/C=CO/ST=Bogota/O=ElectriSys/CN=ElectriSys-CA"

echo "[✓] CA raíz generada"

# ── Función helper: generar cert firmado por la CA ────────────
gen_cert() {
  local NAME="$1"
  local CN="$2"
  local DIR="$CERTS_DIR/$NAME"

  mkdir -p "$DIR"

  openssl genrsa -out "$DIR/$NAME.key" 2048

  # CSR con Subject Alternative Names para k8s
  openssl req -new \
    -key "$DIR/$NAME.key" \
    -out "$DIR/$NAME.csr" \
    -subj "/C=CO/ST=Bogota/O=ElectriSys/CN=$CN" \
    -addext "subjectAltName=DNS:$CN,DNS:$CN.electrisys.svc.cluster.local,IP:127.0.0.1"

  openssl x509 -req -days $DAYS \
    -in "$DIR/$NAME.csr" \
    -CA "$CERTS_DIR/ca/ca.crt" \
    -CAkey "$CERTS_DIR/ca/ca.key" \
    -CAcreateserial \
    -out "$DIR/$NAME.crt" \
    -extfile <(printf "subjectAltName=DNS:%s,DNS:%s.electrisys.svc.cluster.local,IP:127.0.0.1" "$CN" "$CN")

  rm "$DIR/$NAME.csr"
  chmod 600 "$DIR/$NAME.key"
  echo "[✓] Certificado generado: $NAME ($CN)"
}

# ── 2. Certificados por servicio ──────────────────────────────
gen_cert "nginx"     "frontend"
gen_cert "php-fpm"   "backend-a"
gen_cert "mysql"     "mysql-primary"

# ── 3. Verificar cadena ───────────────────────────────────────
echo ""
echo "[ElectriSys TLS] Verificando cadena de certificados..."
openssl verify -CAfile "$CERTS_DIR/ca/ca.crt" "$CERTS_DIR/nginx/nginx.crt"
openssl verify -CAfile "$CERTS_DIR/ca/ca.crt" "$CERTS_DIR/php-fpm/php-fpm.crt"
openssl verify -CAfile "$CERTS_DIR/ca/ca.crt" "$CERTS_DIR/mysql/mysql.crt"

# ── 4. Crear Secret de Kubernetes ─────────────────────────────
echo ""
echo "[ElectriSys TLS] Generando k8s/tls/tls-secret.yaml..."
kubectl create secret generic electrisys-tls \
  --namespace electrisys \
  --from-file=ca.crt="$CERTS_DIR/ca/ca.crt" \
  --from-file=nginx.crt="$CERTS_DIR/nginx/nginx.crt" \
  --from-file=nginx.key="$CERTS_DIR/nginx/nginx.key" \
  --from-file=php-fpm.crt="$CERTS_DIR/php-fpm/php-fpm.crt" \
  --from-file=php-fpm.key="$CERTS_DIR/php-fpm/php-fpm.key" \
  --from-file=mysql.crt="$CERTS_DIR/mysql/mysql.crt" \
  --from-file=mysql.key="$CERTS_DIR/mysql/mysql.key" \
  --dry-run=client -o yaml > "$CERTS_DIR/../k8s/tls/tls-secret.yaml"

echo ""
echo "[✓] PKI generada exitosamente en $CERTS_DIR"
echo "    Agrega tls/ a .gitignore — NUNCA subir las claves privadas al repo"
