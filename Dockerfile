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
    unzip \
    nodejs \
    npm \
    && python -m pip install --upgrade pip \
    && rm -rf /var/lib/apt/lists/*

# Deno is the recommended JS runtime for yt-dlp's YouTube EJS challenge solving.
RUN curl -fsSL https://deno.land/install.sh | sh \
    && mv /root/.deno/bin/deno /usr/local/bin/deno \
    && deno --version

# Install the current BgUtils PO-token provider. yt-dlp's current guide
# recommends a PO-token provider for clients that require GVS tokens.
RUN git clone --depth 1 --branch 1.3.2 \
      https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
      /opt/bgutil-ytdlp-pot-provider \
    && cd /opt/bgutil-ytdlp-pot-provider/server \
    && deno install --allow-scripts=npm:canvas --frozen

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install -r requirements.txt

COPY . .

# Start the local PO-token server, then the Telegram bot.
RUN yt-dlp --version && deno --version && ffmpeg -version | head -n 1

EXPOSE 10000

CMD ["sh", "-c", "cd /opt/bgutil-ytdlp-pot-provider/server && deno run --no-prompt --allow-env --allow-net --allow-ffi=. --allow-read=. --allow-sys src/main.ts --port 4416 & exec python -m primebeats"]
