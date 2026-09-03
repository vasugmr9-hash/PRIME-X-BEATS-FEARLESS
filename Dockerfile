FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    git \
    curl \
    ca-certificates \
    fonts-dejavu-core \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir -r requirements.txt

# PyTgCalls 2.3.3 expects this legacy Pyrogram error class.
# Pyrogram 2.0.106 no longer exports it.
RUN python -c "from pathlib import Path; p=Path('/usr/local/lib/python3.12/site-packages/pyrogram/errors/__init__.py'); s=p.read_text(); s += '\n\n# Compatibility for PyTgCalls 2.3.3\ntry:\n    from pyrogram.errors import BadRequest\n    GroupcallForbidden = BadRequest\nexcept ImportError:\n    pass\n'; p.write_text(s)"

COPY . .

EXPOSE 10000

CMD ["python", "-m", "primebeats"]
