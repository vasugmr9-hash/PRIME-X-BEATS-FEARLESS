import asyncio
import os
import random
import re
import shutil
from pathlib import Path
import urllib.parse
from typing import Union

import aiohttp
from py_yt import VideosSearch, Playlist

API_URL = os.environ.get("MEOW_API_URL", "https://music.yukiapi.site")

API_KEY = os.environ.get("MEOW_API_KEY", "YOUR_API_KEY") ## Get This API KEY FROM TELEGRAM BOT USERNAME: @MeowApiRobot
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
        # Direct YouTube URLs used to fall back to oEmbed immediately, which has
        # no duration field. Try the search providers first so /play and /vplay
        # can display the real duration.
        try:
            vercel = await _search_vercel(vid, limit=1)
            if vercel and vercel[0].get("id") == vid:
                return vercel[0]
        except Exception:
            pass
        try:
            s = VideosSearch(vid, limit=1)
            res = await s.next()
            items = res.get("result", [])
            if items:
                r = items[0]
                if r.get("id") == vid:
                    thumb = (
                        r["thumbnails"][0]["url"].split("?")[0]
                        if r.get("thumbnails")
                        else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                    )
                    return {
                        "id": vid,
                        "title": r.get("title", f"YouTube Video ({vid})"),
                        "link": r.get("link", f"https://www.youtube.com/watch?v={vid}"),
                        "duration": r.get("duration", "0:00"),
                        "thumbnails": [{"url": thumb}],
                    }
        except Exception:
            pass
        oembed = await _fetch_oembed(vid)
        if oembed:
            return oembed

    try:
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
    """Fast YouTube search with parallel independent providers.

    A slow/dead search provider must never block the other providers.  The
    first provider returning a usable result set wins; the remaining tasks are
    cancelled.  This keeps /search responsive while preserving py-yt-search,
    Vercel and yt-dlp fallbacks.
    """
    clean_query = str(query or "").strip()
    limit = max(1, min(int(limit), 25))
    if not clean_query:
        return []

    async def pyyt_provider():
        s = VideosSearch(clean_query, limit=limit)
        res = await asyncio.wait_for(s.next(), timeout=8)
        items = res.get("result", []) if isinstance(res, dict) else []
        out=[]
        for r in items:
            if not r or not r.get("id"):
                continue
            vid=str(r["id"])
            thumbs=r.get("thumbnails") or []
            thumb=(thumbs[0].get("url", "").split("?")[0]
                   if thumbs and isinstance(thumbs[0],dict)
                   else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg")
            out.append({
                "id":vid,
                "title":r.get("title") or clean_query,
                "link":r.get("link") or f"https://www.youtube.com/watch?v={vid}",
                "webpage_url":r.get("link") or f"https://www.youtube.com/watch?v={vid}",
                "duration":r.get("duration") or "0:00",
                "thumbnails":[{"url":thumb}],
                "thumbnail":thumb,
            })
        return out[:limit]

    async def vercel_provider():
        return await _search_vercel(clean_query, limit=limit)

    async def ytdlp_provider():
        import yt_dlp
        loop=asyncio.get_running_loop()
        def worker():
            opts={
                "quiet":True,
                "no_warnings":True,
                "extract_flat":True,
                "skip_download":True,
                "ignoreerrors":True,
                "noplaylist":True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(f"ytsearch{limit}:{clean_query}",download=False) or {}
        info=await asyncio.wait_for(loop.run_in_executor(None,worker),timeout=15)
        out=[]; seen=set()
        for r in (info.get("entries",[]) if isinstance(info,dict) else []):
            if not r or not r.get("id"): continue
            vid=str(r["id"])
            if vid in seen: continue
            seen.add(vid)
            ds=int(r.get("duration") or 0)
            out.append({
                "id":vid,
                "title":r.get("title") or clean_query,
                "link":f"https://www.youtube.com/watch?v={vid}",
                "webpage_url":f"https://www.youtube.com/watch?v={vid}",
                "duration":f"{ds//60}:{ds%60:02d}" if ds else "0:00",
                "thumbnails":[{"url":f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"}],
                "thumbnail":f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            })
            if len(out)>=limit: break
        return out

    tasks=[asyncio.create_task(c()) for c in (pyyt_provider,vercel_provider,ytdlp_provider)]
    try:
        for task in asyncio.as_completed(tasks):
            try:
                result=await task
            except Exception as exc:
                print(f"[YouTube search] provider failed: {type(exc).__name__}: {exc}")
                continue
            if result:
                for other in tasks:
                    if not other.done(): other.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
                print(f"[YouTube search] result provider returned {len(result)} results")
                return result[:limit]
        return []
    finally:
        for task in tasks:
            if not task.done(): task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)


async def _media_duration(path: str) -> int:
    """Read the actual downloaded file duration when search metadata is missing."""
    if not os.path.exists(path) or not shutil.which("ffprobe"):
        return 0
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
        return max(0, int(float(out.decode().strip()))) if out.strip() else 0
    except Exception:
        return 0


async def _probe_media(path: str, require_video: bool) -> bool:
    """Verify that the downloaded file really contains the requested media stream."""
    if not os.path.exists(path) or os.path.getsize(path) < 10000:
        return False
    if not shutil.which("ffprobe"):
        return True
    wanted = "v:0" if require_video else "a:0"
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-select_streams", wanted,
            "-show_entries", "stream=codec_type", "-of", "csv=p=0", path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
        return proc.returncode == 0 and bool(out.strip())
    except Exception:
        return False


def _writable_youtube_cookie_file() -> str | None:
    source = os.environ.get("YOUTUBE_COOKIES_FILE", "").strip()
    if not source or not os.path.isfile(source):
        return None
    writable = "/tmp/primebeats_youtube_cookies.txt"
    if os.path.abspath(source) == writable:
        return writable
    try:
        st = os.stat(source)
        if (not os.path.exists(writable) or os.path.getsize(writable) != st.st_size
                or os.path.getmtime(writable) < st.st_mtime):
            shutil.copyfile(source, writable)
            os.chmod(writable, 0o600)
        return writable
    except Exception as exc:
        print(f"[yt-dlp] cookie copy failed: {exc}")
        return None


def _ytdlp_opts(is_video: bool, outtmpl: str) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": False,
        "noplaylist": True,
        "nocheckcertificate": True,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 3,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 4,
        "outtmpl": outtmpl,
        "overwrites": False,
    }
    cookies = _writable_youtube_cookie_file()
    if cookies:
        opts["cookiefile"] = cookies
        print(f"[yt-dlp] using writable cookies: {cookies}")
    if is_video:
        opts.update({
            "format": "bestvideo[height<=720][fps>=60]+bestaudio/bestvideo[height<=720]+bestaudio/best[height<=720]/best",
            "format_sort": ["res:720", "fps", "br"],
            "merge_output_format": "mp4",
        })
    else:
        opts["format"] = "bestaudio/best"
    return opts


async def download_media(video_id: str, is_video: bool = False) -> str:
    """Resolve a playable media URL with yt-dlp, without the Yuki API.

    yt-dlp is used as the only media provider.  Returning the direct YouTube
    media URL avoids waiting for a full file download before /play or /vplay
    can start.  If direct extraction is unavailable, a local yt-dlp download is
    used as a reliable fallback.
    """
    import yt_dlp
    video_id=_extract_video_id(str(video_id)) or str(video_id).strip()
    if not video_id:
        raise RuntimeError("Invalid YouTube video id")
    url=f"https://www.youtube.com/watch?v={video_id}"
    kind="video" if is_video else "audio"
    loop=asyncio.get_running_loop()

    def _extract_direct():
        opts=_ytdlp_opts(is_video, "unused.%(ext)s")
        opts.update({"skip_download":True,"outtmpl":"unused.%(ext)s"})
        # For video, request one combined format first so MediaStream receives
        # one URL.  If YouTube exposes separate streams only, fall back to the
        # best single progressive stream.
        if is_video:
            opts["format"]=(
                "best[height<=720]/bestvideo[height<=720]+bestaudio/"
                "best[height<=720]"
            )
        else:
            opts["format"]="bestaudio/best"
        with yt_dlp.YoutubeDL(opts) as ydl:
            info=ydl.extract_info(url,download=False)
            if not isinstance(info,dict):
                raise RuntimeError("yt-dlp returned no media metadata")
            direct=info.get("url")
            if direct:
                return direct
            formats=info.get("formats") or []
            if is_video:
                candidates=[f for f in formats if f.get("url") and f.get("height") and f.get("height")<=720]
                candidates.sort(key=lambda f:(int(f.get("height") or 0),int(f.get("fps") or 0),int(f.get("tbr") or 0)),reverse=True)
            else:
                candidates=[f for f in formats if f.get("url") and (f.get("acodec") not in (None,"none"))]
                candidates.sort(key=lambda f:float(f.get("abr") or f.get("tbr") or 0),reverse=True)
            if candidates:
                return candidates[0]["url"]
            raise RuntimeError("yt-dlp returned no direct media URL")

    try:
        direct=await asyncio.wait_for(loop.run_in_executor(None,_extract_direct),timeout=45)
        if direct:
            print(f"[yt-dlp] DIRECT {kind} ready: video_id={video_id}")
            return direct
    except Exception as exc:
        print(f"[yt-dlp] direct {kind} extraction failed for {video_id}: {exc}")

    # Reliable fallback: local download.  This is still yt-dlp-only.
    os.makedirs(DOWNLOAD_DIR,exist_ok=True)
    base=os.path.join(DOWNLOAD_DIR,f"{video_id}.ytdlp.{kind}")
    marker=base+".path"
    if os.path.isfile(marker):
        try:
            cached=Path(marker).read_text().strip()
            if os.path.isfile(cached) and os.path.getsize(cached)>10000 and await _probe_media(cached,is_video):
                print(f"[yt-dlp] cache hit: {cached}")
                return cached
        except Exception:
            pass

    def _download():
        opts=_ytdlp_opts(is_video,base+".%(ext)s")
        with yt_dlp.YoutubeDL(opts) as ydl:
            info=ydl.extract_info(url,download=True)
            candidates=[]
            if isinstance(info,dict) and info.get("_filename"):
                candidates.append(info["_filename"])
            for item in (info.get("requested_downloads") or []) if isinstance(info,dict) else []:
                if isinstance(item,dict) and item.get("filepath"): candidates.append(item["filepath"])
            for candidate in candidates:
                if candidate and os.path.isfile(candidate): return candidate
            parent=os.path.dirname(base) or "."; prefix=os.path.basename(base)+"."
            files=[os.path.join(parent,f) for f in os.listdir(parent) if f.startswith(prefix) and not f.endswith(".path") and os.path.isfile(os.path.join(parent,f))]
            if files: return max(files,key=os.path.getmtime)
            raise RuntimeError("yt-dlp completed but no media file was found")

    print(f"[yt-dlp] DOWNLOAD FALLBACK {kind}: video_id={video_id}")
    path=await asyncio.wait_for(loop.run_in_executor(None,_download),timeout=240)
    if not os.path.isfile(path) or os.path.getsize(path)<=10000 or not await _probe_media(path,is_video):
        raise RuntimeError("yt-dlp produced an invalid media file")
    try: Path(marker).write_text(path)
    except Exception: pass
    return path


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


async def resolve(link_or_query: str, requested_by: str = "Unknown",
                  video: bool = False):
    """
    Resolve a YouTube URL/search term and prepare local media through the
    uploaded Yuki API downloader. Local media is passed to PyTgCalls.
    """
    info = await _search_one(_clean_link(str(link_or_query).strip()))
    if not info:
        raise RuntimeError(f"No YouTube result found for: {link_or_query}")

    track = _make_prime_track(info, requested_by)

    # Download once here. download_media() has a persistent per-video cache,
    # so subsequent resolve() calls do not redownload the same media.
    media_path = await download_media(info["id"], is_video=bool(video))
    actual_duration = await _media_duration(media_path)
    metadata_duration = _seconds(info.get("duration"))
    resolved_duration = actual_duration or metadata_duration

    # Track may be a dataclass with fixed fields, so set attributes safely.
    for name, value in (
        ("stream_url", media_path),
        ("title", info.get("title") or "Unknown"),
        ("duration", resolved_duration),
        ("thumbnail", (info.get("thumbnails") or [{}])[0].get("url", "")),
        ("webpage_url", info.get("link")),
        ("video", bool(video)),
    ):
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
