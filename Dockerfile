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

# Deno is used by yt-dlp for YouTube JavaScript challenge solving.
RUN curl -fsSL https://deno.land/install.sh | sh \
    && ln -sf /root/.deno/bin/deno /usr/local/bin/deno

# Build the BgUtils PO-token HTTP provider.
RUN git clone --depth 1 --branch 1.3.2 \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil \
    && cd /opt/bgutil/server \
    && npm ci \
    && npx tsc

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir -r /app/requirements.txt

COPY start_bgutil.sh /app/start_bgutil.sh
RUN chmod +x /app/start_bgutil.sh

COPY . /app

EXPOSE 10000

CMD ["/app/start_bgutil.sh"]
