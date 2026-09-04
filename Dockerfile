FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV BGUTIL_POT_BASE_URL=http://127.0.0.1:4416

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    git \
    curl \
    ca-certificates \
    nodejs \
    npm \
    python3 \
    libcairo2-dev \
    libjpeg62-turbo-dev \
    libpango1.0-dev \
    libgif-dev \
    librsvg2-dev \
    && python -m pip install --upgrade pip \
    && rm -rf /var/lib/apt/lists/*

# Deno is used by yt-dlp's EJS JavaScript challenge solver.
RUN curl -fsSL https://deno.land/install.sh | sh \
    && mv /root/.deno/bin/deno /usr/local/bin/deno \
    && deno --version

# Build the official BgUtils PO-token HTTP provider with Node.js.
# Node mode is the simplest native server mode and avoids the Deno/canvas
# server startup path. The Python plugin is installed from the matching PyPI release.
RUN git clone --single-branch --branch 1.3.2 \
      https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
      /opt/bgutil-ytdlp-pot-provider \
    && cd /opt/bgutil-ytdlp-pot-provider/server \
    && npm ci \
    && npx tsc

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install -r requirements.txt

COPY . .

# Verify all critical components during the image build.
RUN python -m yt_dlp --version \
    && python -c "import bgutil_ytdlp_pot_provider; print('bgutil plugin: OK')" \
    && node --version \
    && deno --version \
    && ffmpeg -version | head -n 1

EXPOSE 10000

# Start the local PO-token provider first, wait for /ping, then start PRIME × BEATS.
CMD ["sh", "-c", "node /opt/bgutil-ytdlp-pot-provider/server/build/main.js --port 4416 > /tmp/bgutil.log 2>&1 & BGUTIL_PID=$!; for i in $(seq 1 30); do if curl -fsS http://127.0.0.1:4416/ping >/dev/null 2>&1; then echo '[bgutil] POT provider ready on 127.0.0.1:4416'; break; fi; if ! kill -0 $BGUTIL_PID 2>/dev/null; then echo '[bgutil] POT provider exited'; cat /tmp/bgutil.log; exit 1; fi; sleep 1; done; if ! curl -fsS http://127.0.0.1:4416/ping >/dev/null 2>&1; then echo '[bgutil] POT provider did not become ready'; cat /tmp/bgutil.log; exit 1; fi; exec python -m primebeats"]
