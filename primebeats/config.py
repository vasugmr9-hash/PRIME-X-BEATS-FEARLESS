from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()

def api_hash_valid(value: str) -> bool:
    return bool(value and value.strip())

def env_int(name: str, default: int = 0) -> int:
    try: return int(os.getenv(name, str(default)).strip())
    except ValueError: raise RuntimeError(f"{name} must be an integer")

@dataclass(frozen=True)
class Config:
    api_id:int; api_hash:str; bot_token:str; assistant_session:str; owner_id:int
    bot_name:str; max_queue:int; default_volume:int; autoplay_default:bool; port:int
    support_group:str; support_channel:str; official_channel:str
    support_group_id:int; support_channel_id:int; official_channel_id:int; discovery_batch:int; playlist_limit:int

    @classmethod
    def from_env(cls):
        req=["API_ID","API_HASH","BOT_TOKEN","ASSISTANT_SESSION","OWNER_ID"]
        missing=[x for x in req if not os.getenv(x)]
        if missing: raise RuntimeError("Missing environment variables: "+", ".join(missing))
        api_id=env_int("API_ID")
        owner_id=env_int("OWNER_ID")
        port=env_int("PORT",10000)
        bot_token=os.environ["BOT_TOKEN"].strip()
        if api_id <= 0: raise RuntimeError("API_ID must be positive")
        if owner_id <= 0: raise RuntimeError("OWNER_ID must be positive")
        if not api_hash_valid(os.environ["API_HASH"]): raise RuntimeError("API_HASH must be a non-empty value")
        if not bot_token or ":" not in bot_token or len(bot_token) < 20: raise RuntimeError("BOT_TOKEN format is invalid")
        if port < 1 or port > 65535: raise RuntimeError("PORT must be between 1 and 65535")
        return cls(
            api_id,os.environ["API_HASH"].strip(),bot_token,
            os.environ["ASSISTANT_SESSION"].strip(),owner_id,
            os.getenv("BOT_NAME","⚝ 𝐏ʀɪᴍᴇ ꭗ 𝐁ᴇᴀᴛѕ ᯤ"),
            max(10,min(500,env_int("MAX_QUEUE",100))),
            max(0,min(200,env_int("DEFAULT_VOLUME",100))),
            os.getenv("AUTOPLAY_DEFAULT","true").lower() in {"1","true","yes","on"},
            port,
            os.getenv("SUPPORT_GROUP","@SPARK_X_NETWORK"),
            os.getenv("SUPPORT_CHANNEL","@SPARK_X_NETWORK_OP"),
            os.getenv("OFFICIAL_CHANNEL","@Prime_Arrived"),
            env_int("SUPPORT_GROUP_ID",-1003448289523),
            env_int("SUPPORT_CHANNEL_ID",-1003809899413),
            env_int("OFFICIAL_CHANNEL_ID",-1003587739198),
            max(4,min(20,env_int("DISCOVERY_BATCH",10))), max(10,min(100,env_int("PLAYLIST_LIMIT",50))),
    )
        
