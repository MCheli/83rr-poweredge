#!/bin/sh
# Generate a self-signed SSL certificate for PostgreSQL on fresh volumes
set -e

DATADIR="/var/lib/postgresql/data"

if [ ! -f "$DATADIR/server.key" ]; then
    echo "Generating self-signed SSL certificate for PostgreSQL..."
    openssl req -new -x509 -days 3650 -nodes \
        -subj "/CN=tallied-postgres" \
        -keyout "$DATADIR/server.key" \
        -out "$DATADIR/server.crt"
    chmod 600 "$DATADIR/server.key"
    echo "SSL certificate generated."
else
    echo "SSL certificate already exists, skipping generation."
fi
