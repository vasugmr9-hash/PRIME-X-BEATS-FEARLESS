from __future__ import annotations

import os
import re
import urllib.parse
from typing import Any

import aiohttp

try:
    from yukiapi import YukiAPI
except ImportError:  # mirror package name used by the project
    from yukiytapi import YukiAPI

from .state import Track

API_URL = os.environ.get("MEOW_API_URL", "https://music.yukiapi.site").rstrip("/")
API_KEY = os.environ.get("MEOW_API_KEY", "yuki_f13c54a24cae79023a43f41e794a3dfc")

# One Yuki client is shared for search/details/stream generation. Yuki documents
# get_stream() specifically as a direct URL for PyTgCalls/FFmpeg, so playback does
# not need to download or re-encode the media on Render.
_yuki = YukiAPI(base_url=API_URL, timeout=60)


def _get(obj: Any, name: str, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _seconds(value: Any) -> int:
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value or "0:00").strip()
    if text.isdigit():
        return int(text)
    parts = text.split(":")
    try:
        total = 0
        for part in parts:
            total = total * 60 + int(part)
        return max(0, total)
    except Exception:
        return 0


def duration(value: Any) -> str:
    sec = _seconds(value)
    return f"{sec // 60}:{sec % 60:02d}"


def _thumb(item: Any) -> str:
    thumb = _get(item, "thumbnail", "") or ""
    if thumb:
        return str(thumb)
    thumbs = _get(item, "thumbnails", []) or []
    if thumbs:
        first = thumbs[0]
        return str(_get(first, "url", "") or "")
    vid = str(_get(item, "id", "") or _get(item, "vidid", "") or "")
    return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else ""


def _link(item: Any) -> str:
    link = _get(item, "link", "") or _get(item, "webpage_url", "")
    if link:
        return str(link)
    vid = str(_get(item, "id", "") or _get(item, "vidid", "") or "")
    return f"https://www.youtube.com/watch?v={vid}" if vid else ""


def _to_dict(item: Any) -> dict:
    vid = str(_get(item, "id", "") or _get(item, "vidid", "") or "")
    title = str(_get(item, "title", "Unknown") or "Unknown")
    dur = _get(item, "duration", "0:00") or "0:00"
    return {
        "id": vid,
        "title": title,
        "link": _link(item),
        "duration": str(dur),
        "thumbnails": [{"url": _thumb(item)}] if _thumb(item) else [],
    }


def _track(item: Any, requested_by: str, stream_url: str | None = None, video: bool = False) -> Track:
    link = _link(item)
    return Track(
        title=str(_get(item, "title", "Unknown") or "Unknown"),
        webpage_url=link,
        stream_url=stream_url or "",
        duration=_seconds(_get(item, "duration_sec", _get(item, "duration", 0))),
        thumbnail=_thumb(item),
        requested_by=requested_by or "Unknown",
        source="YouTube",
        video=bool(video),
    )


async def search_results(query: str, limit: int = 8) -> list[dict]:
    """Fast Yuki search; no yt-dlp extraction is used here."""
    query = str(query or "").strip()
    if not query:
        return []
    results = await _yuki.search(query, limit=max(1, int(limit)))
    return [_to_dict(x) for x in results[: int(limit)]]


async def _details(query_or_url: str):
    return await _yuki.details(str(query_or_url).strip())


async def _direct_stream(query_or_url: str, video: bool) -> str:
    """Get a tokenized direct Yuki stream URL for PyTgCalls."""
    media_type = "video" if video else "audio"
    try:
        url = await _yuki.get_stream(str(query_or_url).strip(), type=media_type)
        if url:
            return str(url)
    except Exception as e:
        print(f"[Yuki] get_stream {media_type} failed: {e}")

    # Compatibility fallback for the currently-used REST stream endpoint. This
    # still streams directly; it does NOT download a local MP4/MP3 first.
    vid = _extract_video_id(str(query_or_url).strip())
    if not vid or not API_KEY:
        raise RuntimeError(f"Yuki direct {media_type} stream unavailable")
    quality = "720" if video else "360"
    return (
        f"{API_URL}/stream/{vid}"
        f"?key={urllib.parse.quote(API_KEY, safe='')}"
        f"&type={media_type}&quality={quality}"
    )


def _extract_video_id(value: str) -> str | None:
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    for pattern in (
        r"(?:v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        r"/(?:watch/)?([A-Za-z0-9_-]{11})(?:[?&/#]|$)",
    ):
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return None


async def resolve(link_or_query: str, requested_by: str = "Unknown", video: bool = False) -> Track:
    """Resolve metadata and return a direct Yuki URL ready for PyTgCalls."""
    query = str(link_or_query or "").strip()
    if not query:
        raise RuntimeError("Empty YouTube query")

    info = await _details(query)
    if not info:
        raise RuntimeError(f"No YouTube result found for: {query}")

    stream_url = await _direct_stream(_link(info) or query, bool(video))
    if not stream_url.startswith(("http://", "https://")):
        raise RuntimeError("Yuki returned an invalid direct stream URL")

    track = _track(info, requested_by, stream_url, video)
    print(
        f"[Yuki] direct stream ready: video_id={_get(info, 'id', '')} "
        f"type={'video' if video else 'audio'} title={track.title!r}"
    )
    return track


async def resolve_playlist(link: str, requested_by: str = "Unknown", limit: int = 20) -> list[Track]:
    items = await _yuki.playlist(link, limit=max(1, int(limit)))
    result: list[Track] = []
    for item in items[: int(limit)]:
        try:
            result.append(_track(item, requested_by))
        except Exception:
            continue
    return result


def topic_seeds(topic: str) -> list[str]:
    topic = str(topic or "").strip()
    if not topic:
        return []
    return [topic, f"{topic} songs", f"{topic} music", f"{topic} playlist"]


async def discover_topic(topic: str, requested_by: str = "Autoplay", limit: int = 12,
                         exclude=None, round_no: int = 0) -> list[Track]:
    excluded = {str(x).lower() for x in (exclude or set())}
    seeds = topic_seeds(topic)
    if not seeds:
        return []
    queries = [seeds[int(round_no) % len(seeds)]]
    if len(seeds) > 1:
        queries.append(seeds[(int(round_no) + 1) % len(seeds)])

    found: list[Track] = []
    seen: set[str] = set()
    for query in queries:
        try:
            rows = await search_results(query, max(8, int(limit)))
        except Exception as e:
            print(f"[Yuki] discovery search failed: {e}")
            continue
        for row in rows:
            key = (row.get("link") or row.get("id") or "").lower()
            if not key or key in excluded or key in seen:
                continue
            seen.add(key)
            try:
                found.append(_track(row, requested_by))
            except Exception:
                continue
            if len(found) >= int(limit):
                return found
    return found


async def close():
    with_context = getattr(_yuki, "close", None)
    if with_context:
        try:
            await with_context()
        except Exception:
            pass


# Compatibility object for older integrations that import YouTube directly.
class YouTubeAPI:
    async def search(self, query: str, limit: int = 5):
        return await search_results(query, limit)

    async def details(self, link: str, videoid=None):
        if videoid:
            link = f"https://www.youtube.com/watch?v={videoid}"
        item = await _details(link)
        return (
            str(_get(item, "title", "Unknown")),
            str(_get(item, "duration", "0:00")),
            _seconds(_get(item, "duration_sec", _get(item, "duration", 0))),
            _thumb(item),
            str(_get(item, "id", "")),
        )

    async def thumbnail(self, link: str, videoid=None):
        if videoid:
            link = f"https://www.youtube.com/watch?v={videoid}"
        return _thumb(await _details(link))

    async def title(self, link: str, videoid=None):
        if videoid:
            link = f"https://www.youtube.com/watch?v={videoid}"
        return str(_get(await _details(link), "title", ""))

    async def duration(self, link: str, videoid=None):
        if videoid:
            link = f"https://www.youtube.com/watch?v={videoid}"
        return str(_get(await _details(link), "duration", "0:00"))

    async def video(self, link: str, videoid=None):
        if videoid:
            link = f"https://www.youtube.com/watch?v={videoid}"
        track = await resolve(link, "Unknown", True)
        return 1, track.stream_url

    async def download(self, link: str, mystic=None, video=False, videoid=None,
                       songaudio=None, songvideo=None, format_id=None, title=None):
        if videoid:
            link = f"https://www.youtube.com/watch?v={videoid}"
        track = await resolve(link, "Unknown", bool(video or songvideo))
        # This compatibility method is expected to return a path by older bots;
        # PRIME × BEATS itself uses resolve() and the direct URL path above.
        return track.stream_url, True


YouTube = YouTubeAPI()
