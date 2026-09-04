from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path


class ApprovalStore:
    """Lifetime approval store for the running deployment.

    Approvals are keyed by Telegram chat ID and are not tied to usernames.
    The JSON file survives normal process restarts. On Render Free, the local
    filesystem is ephemeral across some redeploys, so a persistent Render Disk
    or external storage is required if approvals must survive every redeploy.
    """

    def __init__(self, path: str | None = None):
        self.path = Path(path or os.getenv("APPROVAL_FILE", "data/approved_chats.json"))
        self.lock = asyncio.Lock()
        self.data: set[int] = set()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                self.data = {int(x) for x in raw}
            elif isinstance(raw, dict):
                self.data = {int(x) for x, enabled in raw.items() if enabled}
        except (OSError, ValueError, TypeError):
            self.data = set()

    async def _write_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(sorted(self.data), separators=(",", ":")),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    async def approve(self, chat_id: int) -> None:
        async with self.lock:
            self.data.add(int(chat_id))
            await self._write_locked()

    async def revoke(self, chat_id: int) -> None:
        async with self.lock:
            self.data.discard(int(chat_id))
            await self._write_locked()

    def is_approved(self, chat_id: int) -> bool:
        return int(chat_id) in self.data

    def all(self) -> set[int]:
        return set(self.data)
