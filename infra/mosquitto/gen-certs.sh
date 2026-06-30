#!/usr/bin/env bash
# gen-certs.sh — generate local dev TLS certs for Mosquitto and sample devices.
#
# Usage: bash infra/mosquitto/gen-certs.sh
#
# Creates:
#   infra/mosquitto/certs/ca.{key,crt}          — local CA (10-year validity)
#   infra/mosquitto/certs/server.{key,crt}       — Mosquitto server cert
#   infra/mosquitto/certs/ingest.{key,crt}       — ingest worker client cert
#   infra/mosquitto/certs/device-sample.{key,crt} — one sample device cert
#
# All private keys are 4096-bit RSA.  Never commit these to git.

set -euo pipefail

CERTS_DIR="$(cd "$(dirname "$0")" && pwd)/certs"
mkdir -p "$CERTS_DIR"

DAYS_CA=3650    # 10 years
DAYS_LEAF=825   # ~2 years (Apple/Mozilla max for trusted certs)

C=IN; ST=Maharashtra; L=Pune; O=obdmonai-dev

# ─── CA ───────────────────────────────────────────────────────────────────────
echo "[gen-certs] Generating CA..."
openssl genrsa -out "$CERTS_DIR/ca.key" 4096

openssl req -new -x509 -days "$DAYS_CA" \
  -key "$CERTS_DIR/ca.key" \
  -out "$CERTS_DIR/ca.crt" \
  -subj "/C=$C/ST=$ST/L=$L/O=$O/CN=obdmonai-dev-CA"

# ─── Helper: issue_cert <name> <CN> ───────────────────────────────────────────
issue_cert() {
  local name=$1 cn=$2
  echo "[gen-certs] Generating cert: $name (CN=$cn)..."
  openssl genrsa -out "$CERTS_DIR/${name}.key" 4096
  openssl req -new \
    -key "$CERTS_DIR/${name}.key" \
    -out "$CERTS_DIR/${name}.csr" \
    -subj "/C=$C/ST=$ST/L=$L/O=$O/CN=$cn"
  openssl x509 -req -days "$DAYS_LEAF" \
    -in  "$CERTS_DIR/${name}.csr" \
    -CA  "$CERTS_DIR/ca.crt" \
    -CAkey "$CERTS_DIR/ca.key" \
    -CAcreateserial \
    -out "$CERTS_DIR/${name}.crt"
  rm -f "$CERTS_DIR/${name}.csr"
}

# ─── Mosquitto server cert (SAN for local dev hostnames) ──────────────────────
echo "[gen-certs] Generating server cert..."
openssl genrsa -out "$CERTS_DIR/server.key" 4096
openssl req -new \
  -key "$CERTS_DIR/server.key" \
  -out "$CERTS_DIR/server.csr" \
  -subj "/C=$C/ST=$ST/L=$L/O=$O/CN=mosquitto"

cat > "$CERTS_DIR/server.ext" <<EOF
subjectAltName=DNS:mosquitto,DNS:localhost,IP:127.0.0.1
EOF

openssl x509 -req -days "$DAYS_LEAF" \
  -in  "$CERTS_DIR/server.csr" \
  -CA  "$CERTS_DIR/ca.crt" \
  -CAkey "$CERTS_DIR/ca.key" \
  -CAcreateserial \
  -extfile "$CERTS_DIR/server.ext" \
  -out "$CERTS_DIR/server.crt"

rm -f "$CERTS_DIR/server.csr" "$CERTS_DIR/server.ext"

# ─── Ingest worker client cert ────────────────────────────────────────────────
issue_cert "ingest" "obdmonai-ingest-worker"

# ─── Sample device cert ───────────────────────────────────────────────────────
issue_cert "device-sample" "device-ESP32-SAMPLE"

chmod 600 "$CERTS_DIR"/*.key

echo ""
echo "✓ Certs written to $CERTS_DIR"
echo "  CA:             ca.crt"
echo "  Server:         server.{key,crt}"
echo "  Ingest worker:  ingest.{key,crt}"
echo "  Sample device:  device-sample.{key,crt}"
echo ""
echo "Mount certs/ into the mosquitto container (already in docker-compose.yml)."
echo "Add MQTT_CA_CERT / MQTT_CLIENT_CERT / MQTT_CLIENT_KEY to .env."
