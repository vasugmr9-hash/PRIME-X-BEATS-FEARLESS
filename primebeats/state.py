from __future__ import annotations
import asyncio, random
from dataclasses import dataclass, field
from typing import Optional
@dataclass
class Track:
    title:str; webpage_url:str; stream_url:str; duration:int
    thumbnail:str=""; requested_by:str="Unknown"; source:str="YouTube"; video:bool=False
@dataclass
class Player:
    queue:list[Track]=field(default_factory=list); current:Optional[Track]=None
    paused:bool=False; muted:bool=False; volume:int=100; loop:bool=False
    autoplay:bool=True; autoplay_topic:str=""; history:list[Track]=field(default_factory=list)
    started_at:float=0.0; paused_at:float=0.0; effect:str="normal"; video:bool=False; speed:float=1.0
    lock:asyncio.Lock=field(default_factory=asyncio.Lock)
    autoplay_round:int=0
    autoplay_seen:set[str]=field(default_factory=set)
    announce:bool=True
    auto_leave:bool=False; loop_mode:str="track"
    crossfade:bool=False; max_history:int=50; requester_only:bool=False
    def add(self,t,limit):
        if len(self.queue)>=limit: raise OverflowError("Queue limit reached")
        self.queue.append(t); return len(self.queue)
    def next(self): return self.queue.pop(0) if self.queue else None
    def clear(self): self.queue.clear()
    def shuffle(self): random.shuffle(self.queue)
    def remember(self,t):
        self.history.insert(0,t); del self.history[20:]
class PlayerStore:
    def __init__(self,default_volume=100,autoplay=True):
        self.players={}; self.default_volume=default_volume; self.autoplay=autoplay
    def get(self,chat_id):
        if chat_id not in self.players:self.players[chat_id]=Player(volume=self.default_volume,autoplay=self.autoplay)
        return self.players[chat_id]
