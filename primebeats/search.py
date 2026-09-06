from __future__ import annotations

import asyncio
import secrets
import time
from contextlib import suppress

from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .ui import player_keyboard
from .youtube import resolve_result, search_results


CACHE_TTL = 300.0
CACHE_MAX = 64


def register_search_commands(app) -> None:
    """
    Register /search separately from the large PrimeBeats command registry.

    The current app.py has the search engine imported but does not register a
    /search message handler or search-result callback. Keeping this isolated
    avoids rewriting the large app.py file and preserves all existing commands.
    """

    @app.bot.on_message(filters.command("search"))
    async def search_command(_, m):
        if not await app.require_admin(m):
            return

        parts = (m.text or "").split(maxsplit=1)
        query = parts[1].strip() if len(parts) > 1 else ""

        if not query:
            await m.reply_text(
                "🔎 <b>SEARCH</b>\n\n"
                "Use <code>/search song name</code>"
            )
            return

        status = await m.reply_text(
            "<b>╭━━〔 🔎 PRIME SEARCH 〕━━╮</b>\n"
            "┃ 🔍 Searching YouTube...\n"
            "┃ ⚡ Preparing playable results...\n"
            "<b>╰━━━━━━━━━━━━━━━━━━━━╯</b>"
        )

        chat_id = m.chat.id
        app._search_cache = getattr(app, "_search_cache", {})

        try:
            app.log.info("SEARCH RECEIVED chat=%s query=%r", chat_id, query) if hasattr(app, "log") else None

            entries = await asyncio.wait_for(search_results(query, 8), timeout=25)

            if not entries:
                await status.edit_text(
                    "❌ <b>NO SEARCH RESULTS</b>\n\n"
                    f"Query: <code>{query[:100]}</code>\n\n"
                    "Try another song or artist name."
                )
                return

            now = time.monotonic()
            key = secrets.token_urlsafe(9).replace("-", "_").replace("/", "_")

            # Keep only recent entries and cap memory.
            app._search_cache = {
                k: v
                for k, v in app._search_cache.items()
                if now - v[0] < CACHE_TTL
            }

            if len(app._search_cache) >= CACHE_MAX:
                oldest = min(
                    app._search_cache,
                    key=lambda k: app._search_cache[k][0],
                )
                app._search_cache.pop(oldest, None)

            app._search_cache[key] = (now, entries)

            rows = []
            for index, entry in enumerate(entries, 1):
                title = str(entry.get("title") or "Unknown").strip()
                if len(title) > 55:
                    title = title[:52] + "..."

                rows.append(
                    [
                        InlineKeyboardButton(
                            f"▶ {index:02} • {title}",
                            callback_data=f"fearsearch:{key}:{index - 1}",
                        )
                    ]
                )

            rows.append(
                [
                    InlineKeyboardButton(
                        "✕ Close",
                        callback_data=f"fearsearch_close:{key}",
                    )
                ]
            )

            await status.edit_text(
                "<b>╭━━〔 🔎 PRIME SEARCH 〕━━╮</b>\n"
                f"┃ 🎵 Query: <code>{query[:80]}</code>\n"
                f"┃ 📋 Results: <code>{len(entries)}</code>\n"
                "┃ ⚡ Tap a result to play/queue\n"
                "<b>╰━━━━━━━━━━━━━━━━━━━━╯</b>",
                reply_markup=InlineKeyboardMarkup(rows),
            )

        except asyncio.TimeoutError:
            await status.edit_text(
                "⏱️ <b>SEARCH TIMEOUT</b>\n\n"
                "YouTube search took too long. Please try again."
            )
        except Exception as exc:
            app_log = getattr(app, "log", None)
            if app_log:
                app_log.exception(
                    "SEARCH FAILED chat=%s query=%r",
                    chat_id,
                    query,
                )
            else:
                print(f"[SEARCH FAILED] chat={chat_id} query={query!r}: {exc}")

            await status.edit_text(
                "❌ <b>SEARCH FAILED</b>\n\n"
                "The search providers did not return a usable result.\n"
                "Please try again with a different query."
            )

    @app.bot.on_callback_query(filters.regex(r"^fearsearch:"))
    async def search_result_callback(_, q):
        data = q.data or ""

        if data.startswith("fearsearch_close:"):
            with suppress(Exception):
                await q.answer("Closed")
            with suppress(Exception):
                await q.message.delete()
            return

        if not await app.require_admin(q.message):
            with suppress(Exception):
                await q.answer("Admin only", show_alert=True)
            return

        try:
            _, key, index_text = data.split(":", 2)
            cached = app._search_cache.get(key)

            if not cached:
                raise RuntimeError("Search results expired. Run /search again.")

            created_at, entries = cached
            if time.monotonic() - created_at >= CACHE_TTL:
                app._search_cache.pop(key, None)
                raise RuntimeError("Search results expired. Run /search again.")

            index = int(index_text)
            if index < 0 or index >= len(entries):
                raise RuntimeError("Invalid search result.")

            entry = entries[index]

            await q.answer("⏳ Loading…")

            track = await asyncio.wait_for(
                resolve_result(
                    entry,
                    app._requester_name(q.from_user),
                    False,
                ),
                timeout=40,
            )
            track.video = False

            chat_id = q.message.chat.id
            p = app.store.get(chat_id)

            async with p.lock:
                if p.current:
                    position = p.add(track, app.cfg.max_queue)
                    await q.answer(f"📥 Queued at #{position}")
                else:
                    await asyncio.wait_for(
                        app.stream(chat_id, track, False, p.effect),
                        timeout=45,
                    )
                    await q.answer("▶️ Playing ⚡")

            await app._announce_track(chat_id, track, p)

            with suppress(Exception):
                await q.message.delete()

        except Exception as exc:
            app_log = getattr(app, "log", None)
            if app_log:
                app_log.exception(
                    "SEARCH RESULT FAILED data=%s",
                    data,
                )
            else:
                print(f"[SEARCH RESULT FAILED] {data}: {exc}")

            with suppress(Exception):
                await q.answer(
                    f"❌ {str(exc)[:180]}",
                    show_alert=True,
                )
