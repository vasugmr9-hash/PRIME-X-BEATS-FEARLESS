import asyncio
import os
import random
import re
import urllib.parse
import time
from typing import Union

import aiohttp
try:
    from py_yt import VideosSearch, Playlist
except Exception:
    VideosSearch = None
    Playlist = None

API_URL = os.environ.get("MEOW_API_URL", "https://music.yukiapi.site")

API_KEY = os.environ.get("MEOW_API_KEY", "yuki_f13c54a24cae79023a43f41e794a3dfc")
DOWNLOAD_DIR = "downloads"

_global_session: aiohttp.ClientSession | None = None
_session_lock = asyncio.Lock()


async def get_session() -> aiohttp.ClientSession:
    global _global_session
    if _global_session is not None and not _global_session.closed:
        return _global_session

    async with _session_lock:
        if _global_session is not None and not _global_session.closed:
            return _global_session

        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=50,
            ttl_dns_cache=600,
            keepalive_timeout=300,
            enable_cleanup_closed=True,
            force_close=False,
        )
        timeout = aiohttp.ClientTimeout(total=180, connect=10, sock_read=60)
        _global_session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
        )
        return _global_session


_thumb_cache: dict[str, str] = {}
_THUMB_CACHE_MAX = 1000
_RESOLVE_SEMAPHORE = asyncio.Semaphore(4)
_RESOLVE_CACHE: dict[tuple[str, bool], tuple[float, dict]] = {}
_RESOLVE_CACHE_TTL = 15.0
_RESOLVE_CACHE_MAX = 128


def _cache_thumb(vidid: str, url: str) -> str:
    if len(_thumb_cache) >= _THUMB_CACHE_MAX:
        del _thumb_cache[next(iter(_thumb_cache))]
    _thumb_cache[vidid] = url
    return url


def _extract_video_id(link: str) -> str | None:
    if not link:
        return None
    for pat in [
        r"(?:v=|/)([0-9A-Za-z_-]{11})(?:[&?]|$)",
        r"youtu\.be/([0-9A-Za-z_-]{11})",
        r"embed/([0-9A-Za-z_-]{11})",
        r"shorts/([0-9A-Za-z_-]{11})",
    ]:
        m = re.search(pat, link)
        if m:
            return m.group(1)
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", link.strip()):
        return link.strip()
    return None


def _clean_link(link: str) -> str:
    return link.split("&")[0] if "&" in link else link


def time_to_seconds(time_str: str) -> int:
    if not time_str:
        return 0
    parts = time_str.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return int(parts[0]) if parts[0].isdigit() else 0


async def _fetch_oembed(video_id: str) -> dict | None:
    session = await get_session()
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
            if resp.status == 200:
                data = await resp.json()
                title = data.get("title", "")
                thumb = data.get("thumbnail_url", f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg")
                return {
                    "id": video_id,
                    "title": title,
                    "link": f"https://www.youtube.com/watch?v={video_id}",
                    "duration": "0:00",
                    "thumbnails": [{"url": thumb}],
                }
    except Exception:
        pass
    return None


async def _search_vercel(query: str, limit: int = 1) -> list[dict]:
    session = await get_session()
    url = f"https://yt-music-api-seven.vercel.app/search/musics?query={urllib.parse.quote(query)}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                data = await resp.json()
                out = []
                for item in data.get("content", []):
                    vid_id = item.get("id")
                    title = item.get("title")
                    if not vid_id or not title:
                        continue
                    dur_obj = item.get("duration", {})
                    dur_str = dur_obj.get("formatted") if isinstance(dur_obj, dict) else "0:00"
                    thumbs = item.get("thumbnails", [])
                    thumb = thumbs[-1].get("url") if thumbs else f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg"
                    out.append({
                        "id": vid_id,
                        "title": title,
                        "link": f"https://www.youtube.com/watch?v={vid_id}",
                        "duration": dur_str or "0:00",
                        "thumbnails": [{"url": thumb}],
                    })
                    if len(out) >= limit:
                        break
                return out
    except Exception:
        pass
    return []


async def _search_one(query: str) -> dict | None:
    vid = _extract_video_id(query)
    if vid:
        oembed = await _fetch_oembed(vid)
        if oembed:
            return oembed

    try:
        if VideosSearch is None:
            raise RuntimeError("py_yt unavailable")
        s = VideosSearch(query, limit=1)
        res = await s.next()
        items = res.get("result", [])
        if items and items[0].get("id"):
            r = items[0]
            thumb = (
                r["thumbnails"][0]["url"].split("?")[0]
                if r.get("thumbnails")
                else f"https://i.ytimg.com/vi/{r['id']}/hqdefault.jpg"
            )
            return {
                "id": r["id"],
                "title": r.get("title", query),
                "link": r.get("link", f"https://www.youtube.com/watch?v={r['id']}"),
                "duration": r.get("duration", "0:00"),
                "thumbnails": [{"url": thumb}],
            }
    except Exception:
        pass

    vercel_results = await _search_vercel(query, limit=1)
    if vercel_results:
        return vercel_results[0]

    try:
        import yt_dlp
        loop = asyncio.get_running_loop()

        def _ytdlp_flat():
            opts = {"extract_flat": True, "quiet": True, "no_warnings": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                target = query if vid else f"ytsearch1:{query}"
                info = ydl.extract_info(target, download=False)
                if "entries" in info and info["entries"]:
                    return info["entries"][0]
                return info

        info = await loop.run_in_executor(None, _ytdlp_flat)
        if info and info.get("id"):
            v_id = info["id"]
            dur_s = int(info.get("duration") or 0)
            dur_str = f"{dur_s//60}:{dur_s%60:02d}" if dur_s else "0:00"
            thumb = f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg"
            return {
                "id": v_id,
                "title": info.get("title", query),
                "link": f"https://www.youtube.com/watch?v={v_id}",
                "duration": dur_str,
                "thumbnails": [{"url": thumb}],
            }
    except Exception:
        pass

    if vid:
        return {
            "id": vid,
            "title": f"YouTube Video ({vid})",
            "link": f"https://www.youtube.com/watch?v={vid}",
            "duration": "0:00",
            "thumbnails": [{"url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"}],
        }
    return None


async def _search_many(query: str, limit: int = 10) -> list[dict]:
    try:
        if VideosSearch is None:
            raise RuntimeError("py_yt unavailable")
        s = VideosSearch(query, limit=limit)
        res = await s.next()
        items = res.get("result", [])
        out = []
        for r in items:
            if not r.get("id"):
                continue
            thumb = (
                r["thumbnails"][0]["url"].split("?")[0]
                if r.get("thumbnails")
                else f"https://i.ytimg.com/vi/{r['id']}/hqdefault.jpg"
            )
            out.append({
                "id": r["id"],
                "title": r.get("title", ""),
                "link": r.get("link", f"https://www.youtube.com/watch?v={r['id']}"),
                "duration": r.get("duration", "0:00"),
                "thumbnails": [{"url": thumb}],
            })
        if out:
            return out
    except Exception:
        pass

    vercel_results = await _search_vercel(query, limit=limit)
    if vercel_results:
        return vercel_results

    return []


async def download_media(video_id: str, is_video: bool = False) -> str:
    if not API_KEY or API_KEY == "YOUR_API_KEY":
        print("[Yuki API] Error: API_KEY is not set in environment or config.")
        raise RuntimeError("API_KEY missing. Please set MEOW_API_KEY in .env or get from @MeowApiRobot")

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    ext = "mp4" if is_video else "mp3"
    req_type = "video" if is_video else "audio"
    out_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")

    if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
        return out_path

    session = await get_session()
    stream_url = f"{API_URL}/stream/{video_id}?key={API_KEY}&type={req_type}&quality=360"

    tmp_path = f"{out_path}.tmp.{random.randint(1000, 9999)}"
    try:
        async with session.get(stream_url) as resp:
            if resp.status == 200:
                with open(tmp_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(65536):
                        f.write(chunk)

                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10000:
                    os.replace(tmp_path, out_path)
                    return out_path
            elif resp.status == 401:
                raise RuntimeError("Invalid API_KEY. Please get a valid key from @MeowApiRobot")
    except Exception as e:
        print(f"[Yuki API] Stream error for {video_id}: {e}")
        raise
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
        return out_path
    raise RuntimeError(f"Yuki API download failed for {video_id}")


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://www.youtube.com/playlist?list="

    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
        vid = _extract_video_id(link) if not videoid else link
        return bool(vid)

    async def url(self, message_or_text) -> str | None:
        text = message_or_text.text if hasattr(message_or_text, "text") else str(message_or_text)
        vid = _extract_video_id(text)
        return f"https://www.youtube.com/watch?v={vid}" if vid else None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        clean = _clean_link(link)
        r = await _search_one(clean)
        if not r:
            raise RuntimeError(f"No track details found for: {link}")

        title = r["title"]
        dur_str = r["duration"]
        dur_sec = time_to_seconds(dur_str)
        thumb = r["thumbnails"][0]["url"]
        vid = r["id"]
        _cache_thumb(vid, thumb)
        return title, dur_str, dur_sec, thumb, vid

    async def title(self, link: str, videoid: Union[bool, str] = None) -> str:
        if videoid:
            link = self.base + link
        r = await _search_one(_clean_link(link))
        return r["title"] if r else ""

    async def duration(self, link: str, videoid: Union[bool, str] = None) -> str:
        if videoid:
            link = self.base + link
        r = await _search_one(_clean_link(link))
        return r["duration"] if r else "0:00"

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None) -> str:
        if videoid:
            link = self.base + link
        vid = _extract_video_id(link)
        if vid and vid in _thumb_cache:
            return _thumb_cache[vid]
        r = await _search_one(_clean_link(link))
        if r:
            thumb = r["thumbnails"][0]["url"]
            if vid:
                _cache_thumb(vid, thumb)
            return thumb
        return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else ""

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        r = await _search_one(_clean_link(link))
        if not r:
            raise RuntimeError(f"No track found for: {link}")
        thumb = r["thumbnails"][0]["url"]
        _cache_thumb(r["id"], thumb)
        return {
            "title": r["title"],
            "link": r["link"],
            "vidid": r["id"],
            "duration_min": r["duration"],
            "thumb": thumb,
        }, r["id"]

    async def playlist(self, link: str, limit: int, user_id: int, videoid: Union[bool, str] = None) -> list[str]:
        if videoid:
            link = self.listbase + link
        clean = _clean_link(link)

        list_id = None
        if "list=" in link:
            m = re.search(r"[?&]list=([0-9A-Za-z_-]+)", link)
            if m:
                list_id = m.group(1)

        targets = [clean]
        if list_id and list_id.startswith("RD"):
            seed_vid = list_id[2:]
            if "_" in seed_vid:
                seed_vid = seed_vid.split("_")[-1]
            elif len(seed_vid) >= 11:
                seed_vid = seed_vid[:11]
            if seed_vid:
                targets.insert(0, f"https://www.youtube.com/watch?v={seed_vid}&list={list_id}")

        try:
            import yt_dlp
            for tgt in targets:
                try:
                    loop = asyncio.get_running_loop()

                    def _extract_pl(url_to_extract):
                        opts = {"extract_flat": True, "quiet": True, "no_warnings": True, "playlistend": limit}
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            info = ydl.extract_info(url_to_extract, download=False) or {}
                            entries = info.get("entries") or []
                            return [
                                f"https://www.youtube.com/watch?v={e['id']}"
                                for e in entries
                                if e and e.get("id")
                            ]

                    res = await loop.run_in_executor(None, _extract_pl, tgt)
                    if res:
                        return res[:limit]
                except Exception:
                    pass
        except ImportError:
            pass

        try:
            if Playlist is None:
                raise RuntimeError("py_yt unavailable")
            plist = Playlist(clean)
            while plist.hasMore():
                await plist.getNext()
                if len(plist.videos) >= limit:
                    break
            if plist.videos:
                return [v["link"] for v in plist.videos[:limit]]
        except Exception:
            pass
        return []

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return [], link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        items = await _search_many(_clean_link(link), limit=10)
        if not items:
            raise RuntimeError(f"No search results for: {link}")
        if query_type >= len(items):
            query_type = 0
        r = items[query_type]
        thumb = r["thumbnails"][0]["url"]
        _cache_thumb(r["id"], thumb)
        return r["title"], r["duration"], thumb, r["id"]

    async def video(self, link: str, videoid: Union[bool, str] = None):
        vid = _extract_video_id(link) or (link if videoid else None)
        if not vid:
            return 0, None
        try:
            path = await download_media(vid, is_video=True)
            return 1, path
        except Exception as e:
            print(f"[video] Error: {e}")
            return 0, None

    async def is_live(self, link: str, videoid: Union[bool, str] = None) -> bool:
        return False

    async def download(
        self,
        link: str,
        mystic=None,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> tuple[str, bool]:
        is_vid = bool(video or songvideo)
        vid = _extract_video_id(link) or link
        path = await download_media(vid, is_video=is_vid)
        return path, True


YouTube = YouTubeAPI()


async def download_song(link: str) -> str:
    vid = _extract_video_id(link) or link
    return await download_media(vid, is_video=False)


async def download_video(link: str) -> str:
    vid = _extract_video_id(link) or link
    return await download_media(vid, is_video=True)


# ---------------------------------------------------------------------------
# PRIME × BEATS compatibility layer
# The uploaded YouTubeAPI is retained above. The current PRIME × BEATS app
# imports these functions from primebeats.youtube, so expose the same API.
# ---------------------------------------------------------------------------

import inspect
from urllib.parse import urlparse

try:
    from .state import Track
except Exception:
    Track = None


def _seconds(value) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    return time_to_seconds(str(value or "0:00"))


def _make_prime_track(info: dict, requested_by: str):
    """Create the project's Track object without assuming one exact signature."""
    if Track is None:
        return info

    url = info.get("link") or f"https://www.youtube.com/watch?v={info.get('id')}"
    duration_str = info.get("duration") or "0:00"
    duration_sec = _seconds(duration_str)
    thumb = (info.get("thumbnails") or [{}])[0].get("url", "")
    vid = info.get("id", "")

    values = {
        "title": info.get("title") or "Unknown",
        "webpage_url": url,
        "requested_by": requested_by or "Unknown",
        "requested_by_id": None,
        "stream_url": None,
        "duration": duration_sec,
        "thumbnail": thumb,
        "video": False,
        "vidid": vid,
        "id": vid,
        "duration_min": duration_str,
        "link": url,
        "thumb": thumb,
    }

    # Build only fields accepted by the installed Track dataclass/class.
    try:
        sig = inspect.signature(Track)
        kwargs = {
            name: values[name]
            for name in sig.parameters
            if name != "self" and name in values
        }
        return Track(**kwargs)
    except Exception:
        # Fallback for positional/simple Track implementations.
        for args in (
            (values["title"], url, requested_by, duration_sec, thumb),
            (values["title"], url, requested_by),
            (values["title"], url),
        ):
            try:
                return Track(*args)
            except Exception:
                pass
        raise RuntimeError("Could not construct PRIME × BEATS Track object")


async def search_results(query: str, limit: int = 8) -> list[dict]:
    """Search using the uploaded YouTube implementation."""
    return await _search_many(query, limit=max(1, int(limit)))


async def _ytdlp_resolve(link_or_query: str, video: bool = False) -> dict:
    """Robust YouTube resolver for current yt-dlp/YouTube extraction changes."""
    import yt_dlp

    target = str(link_or_query).strip()
    if not _extract_video_id(target):
        target = f"ytsearch1:{target}"

    cookie_file = os.getenv("YOUTUBE_COOKIES_FILE", "")

    def _extract():
        base_opts = {
            "quiet": False,
            "no_warnings": False,
            "noplaylist": True,
            "skip_download": True,
            "nocheckcertificate": True,
            "extractor_retries": 3,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 20,
            # Let yt-dlp use the installed JS runtime for current YouTube
            # challenge solving. Do not force a client here.
            "js_runtimes": {"deno": {}, "node": {}},
            "remote_components": ["ejs:npm"],
        }
        if cookie_file and os.path.isfile(cookie_file):
            base_opts["cookiefile"] = cookie_file

        if video:
            base_opts["format"] = (
                "best[height<=720][ext=mp4][vcodec!=none][acodec!=none]/"
                "best[height<=720][vcodec!=none][acodec!=none]/best"
            )
        else:
            base_opts["format"] = "ba[ext=m4a]/ba/bestaudio/best"

        # Keep the first attempt on yt-dlp's maintained defaults. The fallbacks
        # are deliberately isolated because YouTube can treat each client
        # differently and a failing client should not poison the next attempt.
        attempts = [
            ("default+bgutil", None),
            # mweb is the client for which yt-dlp recommends a PO-token
            # provider when GVS requires attestation.
            ("mweb+bgutil", ["mweb"]),
            # web_safari can expose HLS formats that currently do not require
            # a GVS PO token in many cases.
            ("web_safari+bgutil", ["web_safari"]),
            ("web_embedded", ["web_embedded"]),
        ]
        errors = []

        for name, clients in attempts:
            local_opts = dict(base_opts)
            local_opts["extractor_args"] = {
                "youtubepot-bgutilhttp": {
                    "base_url": os.getenv("BGUTIL_POT_PROVIDER_URL",
                                           os.getenv("BGUTIL_POT_BASE_URL",
                                                     "http://127.0.0.1:4416"))
                }
            }
            if clients:
                local_opts["extractor_args"]["youtube"] = {"player_client": clients}

            try:
                with yt_dlp.YoutubeDL(local_opts) as ydl:
                    info = ydl.extract_info(target, download=False)
                    if info and info.get("entries"):
                        info = next((x for x in info["entries"] if x), None)
                    if not info or not info.get("id") or not info.get("url"):
                        raise RuntimeError("yt-dlp returned no playable media")

                    vid = info["id"]
                    thumb = info.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                    return {
                        "id": vid,
                        "title": info.get("title") or "Unknown",
                        "link": info.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}",
                        "duration": int(info.get("duration") or 0),
                        "duration_string": info.get("duration_string") or "",
                        "thumbnails": [{"url": thumb}],
                        "stream_url": info["url"],
                    }
            except Exception as exc:
                text = str(exc).strip().replace("\n", " ")
                errors.append(f"{name}: {text[-500:]}")

        raise RuntimeError("YouTube extraction failed | " + " || ".join(errors))

    key = (target.lower(), bool(video))
    cached = _RESOLVE_CACHE.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < _RESOLVE_CACHE_TTL:
        return dict(cached[1])

    async with _RESOLVE_SEMAPHORE:
        cached = _RESOLVE_CACHE.get(key)
        now = time.monotonic()
        if cached and now - cached[0] < _RESOLVE_CACHE_TTL:
            return dict(cached[1])

        # A slightly longer budget is useful because EJS initialization can
        # take a few seconds on a cold Render instance.
        try:
            result = await asyncio.wait_for(asyncio.to_thread(_extract), timeout=55)
        except Exception as exc:
            # Optional last-resort Yuki API. This is only used when the user
            # has configured MEOW_API_KEY and a direct video ID is available.
            if not video and API_KEY and API_KEY != "YOUR_API_KEY":
                vid = _extract_video_id(target)
                if vid:
                    try:
                        path = await download_media(vid, is_video=False)
                        if os.path.exists(path) and os.path.getsize(path) > 10000:
                            title = f"YouTube Audio ({vid})"
                            details = await _fetch_oembed(vid)
                            if details:
                                title = details.get("title") or title
                            result = {
                                "id": vid,
                                "title": title,
                                "link": f"https://www.youtube.com/watch?v={vid}",
                                "duration": 0,
                                "duration_string": "",
                                "thumbnails": [{"url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"}],
                                "stream_url": path,
                            }
                        else:
                            raise RuntimeError("Yuki returned an empty audio file")
                    except Exception as yuki_exc:
                        raise RuntimeError(
                            f"{exc} | Yuki fallback failed: {yuki_exc}"
                        ) from exc
                else:
                    raise
            else:
                raise

        if len(_RESOLVE_CACHE) >= _RESOLVE_CACHE_MAX:
            oldest = min(_RESOLVE_CACHE, key=lambda k: _RESOLVE_CACHE[k][0])
            _RESOLVE_CACHE.pop(oldest, None)
        _RESOLVE_CACHE[key] = (time.monotonic(), dict(result))
        return result


async def resolve(link_or_query: str, requested_by: str = "Unknown",
                  video: bool = False):
    """Resolve a YouTube query/URL to a PyTgCalls-ready direct media URL."""
    info = await _ytdlp_resolve(link_or_query, video=bool(video))
    track = _make_prime_track(info, requested_by)

    values = (
        ("stream_url", info.get("stream_url")),
        ("title", info.get("title") or "Unknown"),
        ("duration", _seconds(info.get("duration"))),
        ("thumbnail", (info.get("thumbnails") or [{}])[0].get("url", "")),
        ("webpage_url", info.get("link")),
        ("video", bool(video)),
    )
    for name, value in values:
        try:
            setattr(track, name, value)
        except Exception:
            pass
    return track


async def resolve_playlist(link: str, requested_by: str = "Unknown",
                           limit: int = 20) -> list:
    urls = await YouTubeAPI().playlist(link, int(limit), 0)
    result = []
    for url in urls[:int(limit)]:
        try:
            # Playlist import should not download everything immediately.
            info = await _search_one(_clean_link(url))
            if info:
                result.append(_make_prime_track(info, requested_by))
        except Exception:
            continue
    return result


def duration(link_or_value) -> str:
    """Normalize duration to the format expected by the player UI."""
    if isinstance(link_or_value, (int, float)):
        sec = int(link_or_value)
        return f"{sec // 60}:{sec % 60:02d}"

    value = str(link_or_value or "0:00")
    if ":" in value and all(p.isdigit() for p in value.split(":")):
        sec = time_to_seconds(value)
        return f"{sec // 60}:{sec % 60:02d}"
    return value


def topic_seeds(topic: str) -> list[str]:
    topic = (topic or "").strip()
    if not topic:
        return []
    return [
        topic,
        f"{topic} songs",
        f"{topic} music",
        f"{topic} playlist",
    ]


async def discover_topic(topic: str, requested_by: str = "Autoplay",
                         limit: int = 12, exclude=None, round_no: int = 0):
    exclude = {str(x).lower() for x in (exclude or set())}
    found = []
    seen = set()

    seeds = topic_seeds(topic)
    if seeds:
        seed = seeds[int(round_no) % len(seeds)]
    else:
        seed = "music"

    # Use several queries so autoplay remains a real discovery system.
    queries = [seed]
    if len(seeds) > 1:
        queries.append(seeds[(int(round_no) + 1) % len(seeds)])

    for query in queries:
        try:
            rows = await _search_many(query, limit=max(8, int(limit)))
        except Exception:
            rows = []

        for row in rows:
            url = (row.get("link") or "").lower()
            vid = str(row.get("id") or "").lower()
            key = url or vid
            if not key or key in exclude or key in seen:
                continue
            seen.add(key)
            found.append(_make_prime_track(row, requested_by))
            if len(found) >= int(limit):
                return found

    return found
