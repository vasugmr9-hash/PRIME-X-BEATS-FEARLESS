FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential ffmpeg git curl ca-certificates \
    && python -m pip install --upgrade pip \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp now uses an external JavaScript runtime for YouTube challenges.
RUN curl -fsSL https://deno.land/install.sh | sh \
    && mv /root/.deno/bin/deno /usr/local/bin/deno \
    && deno --version

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install -r requirements.txt
COPY . .

EXPOSE 10000
CMD ["python", "-m", "primebeats"]
