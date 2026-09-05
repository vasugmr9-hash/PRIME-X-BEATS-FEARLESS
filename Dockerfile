FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=10000

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    curl \
    ca-certificates \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Modern yt-dlp YouTube extraction uses an external JavaScript runtime.
RUN curl -fsSL https://deno.land/install.sh | sh \
    && ln -sf /root/.deno/bin/deno /usr/local/bin/deno \
    && deno --version

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -r requirements.txt

# primebeats/ is already the real Python package in the repository.
COPY primebeats ./primebeats

# Fail the build early instead of deploying a broken package.
RUN test -f /app/primebeats/__init__.py \
    && test -f /app/primebeats/app.py \
    && test -f /app/primebeats/youtube.py \
    && test -f /app/primebeats/ui.py \
    && python -m py_compile /app/primebeats/*.py \
    && python -c "import py_yt, yt_dlp; print('dependencies: OK'); print('yt-dlp:', yt_dlp.version.__version__)"

EXPOSE 10000

CMD ["sh", "-c", "exec python -m primebeats"]
