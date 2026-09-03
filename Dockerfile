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

# Compatibility fix:
# PyTgCalls 2.3.3 expects legacy Pyrogram exception names
# that are not exported by Pyrogram 2.0.106.
RUN python - <<'PY'
from pathlib import Path

p = Path(
    "/usr/local/lib/python3.12/site-packages/"
    "pytgcalls/mtproto/pyrogram_client.py"
)

s = p.read_text()

s = s.replace(
    "from pyrogram.errors import GroupcallForbidden",
    "from pyrogram.errors import BadRequest\n"
    "\n"
    "class GroupcallForbidden(BadRequest):\n"
    "    pass"
)

s = s.replace(
    "from pyrogram.errors import GroupcallInvalid",
    "from pyrogram.errors import BadRequest\n"
    "\n"
    "class GroupcallInvalid(BadRequest):\n"
    "    pass"
)

p.write_text(s)

print("PyTgCalls compatibility patch applied successfully.")
PY

COPY . .

EXPOSE 10000

CMD ["python", "-m", "primebeats"]
