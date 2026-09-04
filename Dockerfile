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
    unzip \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# JavaScript runtime required by modern yt-dlp
RUN curl -fsSL https://deno.land/install.sh | sh \
    && ln -sf /root/.deno/bin/deno /usr/local/bin/deno

# BgUtils PO-token provider
RUN git clone --depth 1 --branch 1.3.2 \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil \
    && cd /opt/bgutil/server \
    && npm ci \
    && npx tsc

# Python dependencies
COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -r /app/requirements.txt

# Create package
RUN mkdir -p /app/primebeats

# Copy repository Python files
COPY *.py /app/primebeats/

# Normalize filenames used by PRIME x BEATS
RUN set -eux; \
    if [ ! -f /app/primebeats/app.py ]; then \
        if [ -f "/app/primebeats/app (4).py" ]; then \
            mv "/app/primebeats/app (4).py" /app/primebeats/app.py; \
        elif [ -f /app/primebeats/PRIME_X_BEATS_app_FIXED.py ]; then \
            mv /app/primebeats/PRIME_X_BEATS_app_FIXED.py /app/primebeats/app.py; \
        else \
            echo "ERROR: app.py was not found"; \
            ls -la /app/primebeats; \
            exit 1; \
        fi; \
    fi; \
    if [ ! -f /app/primebeats/youtube.py ]; then \
        if [ -f "/app/primebeats/youtube (3).py" ]; then \
            mv "/app/primebeats/youtube (3).py" /app/primebeats/youtube.py; \
        elif [ -f /app/primebeats/PRIME_X_BEATS_youtube_FIXED.py ]; then \
            mv /app/primebeats/PRIME_X_BEATS_youtube_FIXED.py /app/primebeats/youtube.py; \
        else \
            echo "ERROR: youtube.py was not found"; \
            ls -la /app/primebeats; \
            exit 1; \
        fi; \
    fi; \
    if [ ! -f /app/primebeats/ui.py ] && [ -f "/app/primebeats/ui (1).py" ]; then \
        mv "/app/primebeats/ui (1).py" /app/primebeats/ui.py; \
    fi

# Mark as Python package
RUN touch /app/primebeats/__init__.py

# Verify package and syntax
RUN set -eux; \
    test -f /app/primebeats/app.py; \
    test -f /app/primebeats/youtube.py; \
    test -f /app/primebeats/config.py; \
    test -f /app/primebeats/state.py; \
    test -f /app/primebeats/ui.py; \
    python -m py_compile /app/primebeats/*.py

EXPOSE 10000

# Start BgUtils, wait until ready, then start PRIME × BEATS
CMD ["sh", "-c", "set -eu; cd /opt/bgutil/server; node build/main.js > /tmp/bgutil.log 2>&1 & BGUTIL_PID=$!; trap 'kill $BGUTIL_PID 2>/dev/null || true' EXIT TERM INT; echo '[startup] BgUtils starting...'; ready=0; for i in $(seq 1 60); do if curl -fsS http://127.0.0.1:4416/ping >/dev/null 2>&1; then ready=1; echo '[startup] BgUtils READY'; break; fi; sleep 1; done; if [ \"$ready\" -ne 1 ]; then echo '[startup] ERROR: BgUtils did not start'; cat /tmp/bgutil.log || true; exit 1; fi; echo '[startup] Starting PRIME x BEATS...'; cd /app; exec python -m primebeats.app"]
