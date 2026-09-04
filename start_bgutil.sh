#!/bin/sh
set -eu

echo "[startup] Starting BgUtils PO-token HTTP provider..."

cd /opt/bgutil/server
node build/main.js > /tmp/bgutil.log 2>&1 &
BGUTIL_PID=$!

echo "[startup] Waiting for BgUtils on 127.0.0.1:4416..."

i=0
while [ "$i" -lt 60 ]; do
    if curl -fsS http://127.0.0.1:4416/ping >/dev/null 2>&1; then
        echo "[startup] BgUtils is READY."
        break
    fi
    i=$((i + 1))
    sleep 1
done

if ! curl -fsS http://127.0.0.1:4416/ping >/dev/null 2>&1; then
    echo "[startup] ERROR: BgUtils failed to start."
    echo "----- BgUtils log -----"
    cat /tmp/bgutil.log || true
    exit 1
fi

echo "[startup] Starting PRIME × BEATS..."
cd /app
exec python app.py
