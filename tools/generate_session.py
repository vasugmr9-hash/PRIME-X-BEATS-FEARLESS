#!/usr/bin/env python3
"""⚝ 𝐅ᴇᴀʀʟᴇss ꭗ 𝐌ᴜsɪᴄ ᯤ — Fast Telegram assistant session generator.

Compatible with Pyrofork/Pyrogram-style Client APIs.

Security:
- Uses in-memory sessions; no .session file is created.
- Never prints API hash, phone number, login code, or 2FA password.
- Prints only the final ASSISTANT_SESSION value so it can be copied to Render.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = lambda: None

try:
    from pyrogram import Client
except ImportError:
    print("❌ ᴘʏʀᴏɢʀᴀᴍ ɪs ɴᴏᴛ ɪɴsᴛᴀʟʟᴇᴅ.")
    print("❏ ʀᴜɴ: pip install pyrofork tgcrypto python-dotenv")
    raise SystemExit(1)


BANNER = r"""
⚝ 𝐅ᴇᴀʀʟᴇss ꭗ 𝐌ᴜsɪᴄ ᯤ
automated assistant session generator

🚀 ᴘᴏᴡᴇʀғᴜʟ • ғᴀsᴛ • sᴇᴄᴜʀᴇ
❏ ɪɴ-ᴍᴇᴍᴏʀʏ sᴇssɪᴏɴ
❏ ɴᴏ .session ғɪʟᴇ
❏ ʟᴏᴄᴀʟ ᴏɴʟʏ
"""


def _clean(value: str) -> str:
    return value.strip().strip('"').strip("'")


def get_api_id(cli_value: str | None) -> int:
    raw = _clean(cli_value or os.getenv("API_ID", ""))
    if not raw:
        raw = input("\n🔹 𝐀ᴘɪ 𝐈ᴅ: ").strip()
    try:
        api_id = int(raw)
    except ValueError:
        raise SystemExit("❌ 𝐀ᴘɪ 𝐈ᴅ ᴍᴜsᴛ ʙᴇ ᴀ ɴᴜᴍʙᴇʀ.")
    if api_id <= 0:
        raise SystemExit("❌ 𝐀ᴘɪ 𝐈ᴅ ᴍᴜsᴛ ʙᴇ ᴘᴏsɪᴛɪᴠᴇ.")
    return api_id


def get_api_hash(cli_value: str | None) -> str:
    value = _clean(cli_value or os.getenv("API_HASH", ""))
    if not value:
        value = getpass.getpass("🔹 𝐀ᴘɪ 𝐇ᴀsʜ: ")
    if not value:
        raise SystemExit("❌ 𝐀ᴘɪ 𝐇ᴀsʜ ᴄᴀɴɴᴏᴛ ʙᴇ ᴇᴍᴘᴛʏ.")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate an in-memory Telegram assistant session string."
    )
    parser.add_argument("--api-id", help="Telegram API ID; otherwise API_ID is used.")
    parser.add_argument("--api-hash", help="Telegram API hash; otherwise API_HASH is used.")
    parser.add_argument(
        "--name",
        default="fearless_assistant_generator",
        help="Temporary local client name. No session file is written.",
    )
    return parser


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()

    print(BANNER)
    print("╭━━━━━━━━━━━━━━━━━━━━╮")
    print("🔸 𝐓ᴇʟᴇɢʀᴀᴍ 𝐀ssɪsᴛᴀɴᴛ")
    print("╰━━━━━━━━━━━━━━━━━━━━╯")
    print("❏ ᴇɴᴛᴇʀ ʏᴏᴜʀ ᴏᴡɴ ᴛᴇʟᴇɢʀᴀᴍ ᴀᴄᴄᴏᴜɴᴛ ᴅᴇᴛᴀɪʟs")
    print("❏ ᴛʜᴇ ᴄᴏᴅᴇ ᴡɪʟʟ ʙᴇ ᴀsᴋᴇᴅ ɪɴ ᴛʜɪs ᴛᴇʀᴍɪɴᴀʟ")
    print("❏ ɪғ 2-Fᴀᴄᴛᴏʀ ᴀᴜᴛʜᴇɴᴛɪᴄᴀᴛɪᴏɴ ɪs ᴇɴᴀʙʟᴇᴅ, ᴇɴᴛᴇʀ ɪᴛ ᴡʜᴇɴ ᴀsᴋᴇᴅ")
    print("❏ ɴᴇᴠᴇʀ sᴇɴᴅ ʏᴏᴜʀ ᴄᴏᴅᴇ ᴏʀ 2-Fᴀ ᴘᴀssᴡᴏʀᴅ ᴛᴏ ᴀɴʏᴏɴᴇ")

    api_id = get_api_id(args.api_id)
    api_hash = get_api_hash(args.api_hash)

    print("\n🚀 ᴘᴏᴡᴇʀғᴜʟ • ғᴀsᴛ • sᴛᴀʙʟᴇ")
    print("❏ ᴄᴏɴɴᴇᴄᴛɪɴɢ ᴛᴏ ᴛᴇʟᴇɢʀᴀᴍ...")

    try:
        # in_memory=True is intentional: the generator never leaves a local
        # .session/.session-journal file behind.
        with Client(
            args.name,
            api_id=api_id,
            api_hash=api_hash,
            in_memory=True,
        ) as app:
            me = app.get_me()
            username = f"@{me.username}" if me.username else "(no username)"

            print("\n╭━━━━━━━━━━━━━━━━━━━━╮")
            print("🔸 𝐀ssɪsᴛᴀɴᴛ 𝐀ᴜᴛʜᴇɴᴛɪᴄᴀᴛᴇᴅ")
            print("╰━━━━━━━━━━━━━━━━━━━━╯")
            print(f"❏ 𝐔sᴇʀ: {me.first_name or 'Telegram User'}")
            print(f"❏ 𝐔sᴇʀɴᴀᴍᴇ: {username}")
            print("❏ 𝐒ᴛᴀᴛᴜs: ᴏɴʟɪɴᴇ ✅")

            session = app.export_session_string()
            if not session:
                raise RuntimeError("Telegram returned an empty session string")

            print("\n╭━━━━━━━━━━━━━━━━━━━━╮")
            print("🔸 𝐀ssɪsᴛᴀɴᴛ 𝐒ᴇssɪᴏɴ 𝐑ᴇᴀᴅʏ")
            print("╰━━━━━━━━━━━━━━━━━━━━╯")
            print("🚀 ᴘᴏᴡᴇʀғᴜʟ • ғᴀsᴛ • sᴇᴄᴜʀᴇ")
            print("❏ ᴄᴏᴘʏ ᴛʜᴇ ʟɪɴᴇ ʙᴇʟᴏᴡ ᴛᴏ ʀᴇɴᴅᴇʀ:")
            print("\nASSISTANT_SESSION=" + session)
            print("\n⚠️ 𝐒ᴇᴄᴜʀɪᴛʏ")
            print("❏ ᴛʀᴇᴀᴛ ᴛʜɪs sᴇssɪᴏɴ ʟɪᴋᴇ ᴀ ᴘᴀssᴡᴏʀᴅ")
            print("❏ ᴅᴏ ɴᴏᴛ ᴘᴜsʜ ɪᴛ ᴛᴏ ɢɪᴛʜᴜʙ")
            print("❏ ᴅᴏ ɴᴏᴛ sʜᴀʀᴇ ɪᴛ ɪɴ ᴛᴇʟᴇɢʀᴀᴍ")
            print("❏ ᴘᴜᴛ ɪᴛ ɪɴ ʀᴇɴᴅᴇʀ → 𝐄ɴᴠɪʀᴏɴᴍᴇɴᴛ → ASSISTANT_SESSION")
            print("\nᯤ 𝐏ʀɪᴍᴇ × 𝐁ᴇᴀᴛs")

    except KeyboardInterrupt:
        print("\n\n❏ ᴘʀᴏᴄᴇss ᴄᴀɴᴄᴇʟʟᴇᴅ — ɴᴏ sᴇssɪᴏɴ ғɪʟᴇ ᴡᴀs ᴄʀᴇᴀᴛᴇᴅ.")
        return 130
    except Exception as exc:
        print("\n╭━━━━━━━━━━━━━━━━━━━━╮")
        print("🔸 𝐀ᴜᴛʜᴇɴᴛɪᴄᴀᴛɪᴏɴ 𝐅ᴀɪʟᴇᴅ")
        print("╰━━━━━━━━━━━━━━━━━━━━╯")
        print("❌ " + str(exc))
        print("❏ ᴄʜᴇᴄᴋ API_ID / API_HASH ᴀɴᴅ ʀᴇᴛʀʏ.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
        
