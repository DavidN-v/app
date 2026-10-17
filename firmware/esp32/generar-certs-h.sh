#!/usr/bin/env bash
# Genera src/certs.h con los certificados que necesita el ESP32 para conectarse con TLS.
#
# Uso (desde la raíz del proyecto, después de infra/mosquitto/generar-certificados.sh):
#   firmware/esp32/generar-certs-h.sh esp32-env
#
# El archivo contiene la clave privada del dispositivo: está excluido del repositorio.
set -euo pipefail

DEVICE="${1:-esp32-env}"
CERTS="$(cd "$(dirname "$0")/../../infra/mosquitto/certs" && pwd)"
OUT="$(cd "$(dirname "$0")" && pwd)/src/certs.h"

for f in ca.crt "$DEVICE.crt" "$DEVICE.key"; do
  if [ ! -f "$CERTS/$f" ]; then
    echo "Falta $CERTS/$f. Genera antes los certificados con:"
    echo "  infra/mosquitto/generar-certificados.sh <ip-del-servidor> $DEVICE"
    exit 1
  fi
done

{
  echo "// Generado por generar-certs-h.sh para $DEVICE. No subir al repositorio."
  echo "#pragma once"
  echo "static const char CA_CERT[] = R\"PEM($(cat "$CERTS/ca.crt"))PEM\";"
  echo "static const char DEVICE_CERT[] = R\"PEM($(cat "$CERTS/$DEVICE.crt"))PEM\";"
  echo "static const char DEVICE_KEY[] = R\"PEM($(cat "$CERTS/$DEVICE.key"))PEM\";"
} > "$OUT"
echo "Creado $OUT"
