#!/usr/bin/env bash
# Genera los certificados para conectar los dispositivos físicos con cifrado TLS.
#
# Uso (desde la raíz del proyecto, en Linux, macOS o Git Bash en Windows):
#   infra/mosquitto/generar-certificados.sh <ip-o-nombre-del-servidor> [dispositivo ...]
# Ejemplo:
#   infra/mosquitto/generar-certificados.sh 192.168.1.50 rpi5-vision rpi5-genai rpi5-agent uno-q esp32-env
#
# Se crean en infra/mosquitto/certs/:
#   ca.crt / ca.key                autoridad de certificación del laboratorio (guardar ca.key en lugar seguro)
#   server.crt / server.key        certificado del broker, válido para "mosquitto", "localhost" y el servidor indicado
#   governance-api.crt / .key      certificado con el que se identifica la API
#   <dispositivo>.crt / .key       uno por dispositivo; su nombre debe coincidir con el identificador
#                                  registrado en la plataforma, porque el broker lo usa como usuario
#
# Volver a ejecutarlo conserva la autoridad existente y solo crea los certificados que falten.
set -euo pipefail

if [ $# -lt 1 ]; then
  sed -n 2,17p "$0"
  exit 1
fi

SERVER="$1"; shift
DIR="$(cd "$(dirname "$0")" && pwd)/certs"
DAYS=825
mkdir -p "$DIR"
cd "$DIR"
# En Git Bash para Windows, evita que "/CN=..." se interprete como una ruta
export MSYS_NO_PATHCONV=1

if [ ! -f ca.key ]; then
  openssl req -x509 -newkey rsa:4096 -nodes -days 3650 -keyout ca.key -out ca.crt \
    -subj "/CN=Edge Governance CA"
  echo "Autoridad de certificación creada"
fi

# Firma un certificado nuevo con la autoridad. $1 = nombre, $2 = extensiones opcionales
sign() {
  local name="$1" ext="${2:-}"
  if [ -f "$name.crt" ]; then
    echo "Ya existe $name.crt (no se modifica)"
    return
  fi
  openssl req -newkey rsa:2048 -nodes -keyout "$name.key" -out "$name.csr" -subj "/CN=$name"
  if [ -n "$ext" ]; then
    printf '%s\n' "$ext" > "$name.ext"
    openssl x509 -req -in "$name.csr" -CA ca.crt -CAkey ca.key -CAcreateserial -days "$DAYS" \
      -out "$name.crt" -extfile "$name.ext"
    rm -f "$name.ext"
  else
    openssl x509 -req -in "$name.csr" -CA ca.crt -CAkey ca.key -CAcreateserial -days "$DAYS" -out "$name.crt"
  fi
  rm -f "$name.csr"
  # El broker se ejecuta con otro usuario dentro del contenedor y necesita poder leer su clave
  chmod 644 "$name.key"
  echo "Creado $name.crt"
}

# El certificado del servidor debe incluir todas las direcciones por las que se le llama
if [[ "$SERVER" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  SAN="subjectAltName=DNS:mosquitto,DNS:localhost,IP:127.0.0.1,IP:$SERVER"
else
  SAN="subjectAltName=DNS:mosquitto,DNS:localhost,IP:127.0.0.1,DNS:$SERVER"
fi
sign server "$SAN"
sign governance-api
for device in "$@"; do
  sign "$device"
done

echo
echo "Certificados en $DIR"
echo "Copia a cada dispositivo: ca.crt, <dispositivo>.crt y <dispositivo>.key"
