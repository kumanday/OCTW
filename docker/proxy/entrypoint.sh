#!/bin/sh
set -eu

CERT_DIR=/etc/nginx/certs
CERT_FILE="$CERT_DIR/fullchain.pem"
KEY_FILE="$CERT_DIR/privkey.pem"
GENERATED_CERT_DIR=/tmp/nginx-certs
GENERATED_CERT_FILE="$GENERATED_CERT_DIR/fullchain.pem"
GENERATED_KEY_FILE="$GENERATED_CERT_DIR/privkey.pem"

if [ ! -r "$CERT_FILE" ] || [ ! -r "$KEY_FILE" ]; then
  SERVER_NAME="${OCTW_SERVER_NAME:-localhost}"
  echo "Using ephemeral self-signed TLS certificate for ${SERVER_NAME}" >&2
  mkdir -p "$GENERATED_CERT_DIR"
  openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "$GENERATED_KEY_FILE" \
    -out "$GENERATED_CERT_FILE" \
    -days 365 \
    -subj "/CN=${SERVER_NAME}"
  export OCTW_SSL_CERT_FILE="$GENERATED_CERT_FILE"
  export OCTW_SSL_KEY_FILE="$GENERATED_KEY_FILE"
else
  export OCTW_SSL_CERT_FILE="$CERT_FILE"
  export OCTW_SSL_KEY_FILE="$KEY_FILE"
fi

envsubst '${OCTW_SERVER_NAME} ${OCTW_SSL_CERT_FILE} ${OCTW_SSL_KEY_FILE}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

exec "$@"
