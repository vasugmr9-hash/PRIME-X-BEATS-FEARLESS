FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PORT=10000 \
    BGUTIL_POT_PROVIDER_URL=http://127.0.0.1:4416

WORKDIR /app

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

# Install Deno for yt-dlp JavaScript challenge solving
RUN curl -fsSL https://deno.land/install.sh | sh \
    && ln -sf /root/.deno/bin/deno /usr/local/bin/deno

# Build BgUtils PO-token provider
RUN git clone --depth 1 --branch 1.3.2 \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil \
    && cd /opt/bgutil/server \
    && npm ci \
    && npx tsc

COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 10000

CMD ["sh", "-c", \
"cd /opt/bgutil/server && \
 node build/main.js > /tmp/bgutil.log 2>&1 & \
 BGUTIL_PID=$!; \
 echo '[startup] BgUtils starting...'; \
 for i in $(seq 1 60); do \
   if curl -fsS http://127.0.0.1:4416/ping >/dev/null 2>&1; then \
     echo '[startup] BgUtils READY'; \
     break; \
   fi; \
   sleep 1; \
 done; \
 if ! curl -fsS http://127.0.0.1:4416/ping >/dev/null 2>&1; then \
   echo '[startup] ERROR: BgUtils did not start'; \
   cat /tmp/bgutil.log || true; \
   kill $BGUTIL_PID 2>/dev/null || true; \
   exit 1; \
 fi; \
 echo '[startup] Starting PRIME x BEATS...'; \
 exec python -m primebeats.app"]
