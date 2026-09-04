FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=10000 \
    BGUTIL_POT_PROVIDER_URL=http://127.0.0.1:4416

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    ffmpeg \
    git \
    curl \
    ca-certificates \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Deno
RUN curl -fsSL https://deno.land/install.sh | sh \
    && ln -sf /root/.deno/bin/deno /usr/local/bin/deno

# Install BgUtils PO-token provider
RUN git clone --depth 1 --branch 1.3.2 \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil \
    && cd /opt/bgutil/server \
    && npm ci \
    && npx tsc

# Python dependencies
COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -r /app/requirements.txt

# Copy the actual PRIME × BEATS package
COPY primebeats /app/primebeats

# Make sure it is a Python package
RUN touch /app/primebeats/__init__.py

# Verify required files and compile everything
RUN set -eux; \
    test -f /app/primebeats/app.py; \
    test -f /app/primebeats/youtube.py; \
    test -f /app/primebeats/config.py; \
    test -f /app/primebeats/state.py; \
    test -f /app/primebeats/ui.py; \
    python -m py_compile /app/primebeats/*.py; \
    echo "===== PRIME × BEATS FILES ====="; \
    ls -la /app/primebeats

EXPOSE 10000

# Start BgUtils and then PRIME × BEATS
CMD ["sh", "-c", "\
set -eu; \
echo '[startup] BgUtils starting...'; \
cd /opt/bgutil/server; \
node build/main.js > /tmp/bgutil.log 2>&1 & \
BGUTIL_PID=$!; \
i=0; \
while [ $i -lt 60 ]; do \
    if curl -fsS http://127.0.0.1:4416/ping >/dev/null 2>&1; then \
        echo '[startup] BgUtils READY'; \
        break; \
    fi; \
    i=$((i + 1)); \
    sleep 1; \
done; \
if ! curl -fsS http://127.0.0.1:4416/ping >/dev/null 2>&1; then \
    echo '[startup] ERROR: BgUtils failed'; \
    cat /tmp/bgutil.log || true; \
    exit 1; \
fi; \
echo '[startup] Starting PRIME × BEATS...'; \
cd /app; \
exec python -m primebeats.app \
"]
