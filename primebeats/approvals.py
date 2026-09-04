from __future__ import annotations
import json, asyncio
from pathlib import Path

class ApprovalStore:
    def __init__(self, path="data/approved_chats.json"):
        self.path=Path(path); self.lock=asyncio.Lock(); self.data=set()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        try: self.data=set(json.loads(self.path.read_text()))
        except Exception: self.data=set()
    async def save(self):
        async with self.lock:
            self.path.write_text(json.dumps(sorted(self.data)))
    async def approve(self, chat_id:int):
        async with self.lock:
            self.data.add(int(chat_id))
            self.path.write_text(json.dumps(sorted(self.data)))
    async def revoke(self, chat_id:int):
        async with self.lock:
            self.data.discard(int(chat_id))
            self.path.write_text(json.dumps(sorted(self.data)))
    def is_approved(self, chat_id:int)->bool: return int(chat_id) in self.data
        
