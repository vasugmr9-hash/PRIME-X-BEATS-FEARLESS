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


async def _request_json(path: str, params: dict | None = None) -> dict:
    """Call Yuki's public REST API directly.

    The installed SDK can be ahead/behind the public API deployment.  In particular,
    some SDK builds call /details while the live service may not expose that route.
    Playback therefore uses only the stable /search + /download + /stream contract.
    """
    timeout = aiohttp.ClientTimeout(total=25, connect=8, sock_read=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        last = None
        for base in (API_URL, "https://yukiapi.site/music"):
            try:
                async with session.get(f"{base.rstrip('/')}{path}", params=params) as resp:
                    text = await resp.text()
                    if resp.status == 200:
                        try:
                            return await _json_from_text(text)
                        except Exception as e:
                            raise RuntimeError(f"Yuki returned invalid JSON: {e}") from e
                    last = f"HTTP {resp.status}: {text[:180]}"
            except Exception as e:
                last = str(e)
        raise RuntimeError(f"Yuki API request failed: {last}")


async def _json_from_text(text: str) -> dict:
    import json
    data = json.loads(text)
    if not isinstance(data, dict):
        raise RuntimeError("Yuki response is not an object")
    return data


async def search_results(query: str, limit: int = 8) -> list[dict]:
    """Search YouTube through Yuki's stable REST search endpoint."""
    query = str(query or "").strip()
    if not query:
        return []
    data = await _request_json("/search", {"q": query, "limit": max(1, int(limit))})
    rows = data.get("results") or []
    return [_to_dict(x) for x in rows[: int(limit)]]


async def _direct_stream_by_id(video_id: str, video: bool) -> str:
    """Get a tokenized Yuki stream without touching /details."""
    vid = str(video_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
        raise RuntimeError("Invalid YouTube video id")
    media_type = "video" if video else "audio"

    # /download returns the short-lived token used by /stream/{video_id}.
    data = await _request_json("/download", {"url": vid, "type": media_type})
    token = str(data.get("download_token") or data.get("token") or "").strip()
    if not token:
        raise RuntimeError("Yuki did not return a streaming token")

    return (
        f"{API_URL}/stream/{vid}"
        f"?type={urllib.parse.quote(media_type)}"
        f"&token={urllib.parse.quote(token, safe='')}"
    )


def _entry_from_id(video_id: str, requested: str = "YouTube") -> dict:
    return {
        "id": video_id,
        "title": requested or "YouTube",
        "link": f"https://www.youtube.com/watch?v={video_id}",
        "duration": "0:00",
        "thumbnails": [{"url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"}],
    }


async def resolve_result(item: Any, requested_by: str = "Unknown", video: bool = False) -> Track:
    """Play a previously returned search result without a second metadata lookup."""
    if isinstance(item, dict):
        row = item
    else:
        row = _to_dict(item)
    vid = str(_get(row, "id", "") or _get(row, "vidid", "") or "").strip()
    if not vid:
        vid = _extract_video_id(_link(row)) or ""
    if not vid:
        raise RuntimeError("Search result has no YouTube video id")
    stream_url = await _direct_stream_by_id(vid, bool(video))
    track = _track(row, requested_by, stream_url, video)
    print(f"[Yuki] direct stream ready from search: id={vid} type={'video' if video else 'audio'} title={track.title!r}")
    return track


async def resolve(link_or_query: str, requested_by: str = "Unknown", video: bool = False) -> Track:
    """Resolve a query/URL using search + tokenized direct streaming only.

    IMPORTANT: this intentionally does not call yuki.details().  The live Yuki
    deployment currently returns 404 for /details, which caused the previous
    /play and /vplay failures.
    """
    query = str(link_or_query or "").strip()
    if not query:
        raise RuntimeError("Empty YouTube query")

    vid = _extract_video_id(query)
    if vid:
        # A direct URL already gives us the ID, so there is no reason to hit the
        # broken /details endpoint.  Search the ID only for nicer metadata; if it
        # returns nothing, fall back to a thumbnail + URL immediately.
        row = None
        try:
            rows = await search_results(vid, 1)
            if rows:
                row = rows[0]
        except Exception as e:
            print(f"[Yuki] metadata search for {vid} skipped: {e}")
        if not row:
            row = _entry_from_id(vid, query)
    else:
        rows = await search_results(query, 1)
        if not rows:
            raise RuntimeError(f"No YouTube result found for: {query}")
        row = rows[0]
        vid = str(row.get("id") or "").strip()
        if not vid:
            raise RuntimeError("Yuki search returned a result without video id")

    return await resolve_result(row, requested_by, video)


async def _details(query_or_url: str):
    """Compatibility metadata helper implemented without Yuki /details."""
    vid = _extract_video_id(str(query_or_url or "").strip())
    if vid:
        try:
            rows = await search_results(vid, 1)
            if rows:
                return rows[0]
        except Exception:
            pass
    rows = await search_results(str(query_or_url or "").strip(), 1)
    if not rows:
        raise RuntimeError(f"No YouTube result found for: {query_or_url}")
    return rows[0]


async def _direct_stream(query_or_url: str, video: bool) -> str:
    vid = _extract_video_id(str(query_or_url or "").strip())
    if not vid:
        row = await _details(query_or_url)
        vid = str(_get(row, "id", "") or _get(row, "vidid", "") or "")
    return await _direct_stream_by_id(vid, bool(video))

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
