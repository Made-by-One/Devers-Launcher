"""Steam store metadata, achievements, videos and local screenshots.

Everything here is best-effort and runs off the UI thread.  The public
endpoints need no API key, so the launcher can enrich any Steam game that is
already in the library.  Results are cached as JSON for a few hours.
"""

import hashlib
import html
import json
import logging
import math
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from .paths import CACHE_DIR, USER_AGENT
from .utils import save_json

log = logging.getLogger("Devers")

STEAM_CACHE_DIR = CACHE_DIR / "steam_info"
CLIP_CACHE_DIR = CACHE_DIR / "clips"
CACHE_TTL = 6 * 60 * 60
# Bump whenever the payload shape changes so stale JSON is refreshed instead
# of being shown with empty media URLs.
CACHE_SCHEMA = 3

STEAM_LANGUAGES = {
    "en": "english",
    "ru": "russian",
    "uk": "ukrainian",
    "de": "german",
    "fr": "french",
    "es": "spanish",
    "pt": "portuguese",
    "zh": "schinese",
}

_TAG_RE = re.compile(r"<[^>]+>")
_BREAK_RE = re.compile(r"(?i)<br\s*/?>")
_PARA_RE = re.compile(r"(?i)</p\s*>")
_SSR_RE = re.compile(
    r'<script[^>]*id="valve-ssr-data"[^>]*>(.*?)</script>', re.S)


def steam_language(code=None) -> str:
    """Maps a launcher language code to the Steam endpoint name."""
    if code is None:
        try:
            from .i18n import L
            code = L.current_lang
        except Exception:
            code = "en"
    return STEAM_LANGUAGES.get(str(code or "en").lower(), "english")


def _request(url: str, timeout: int = 20):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.8",
            "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _json(url: str, timeout: int = 20):
    return json.loads(_request(url, timeout).decode("utf-8", "ignore"))


def _text(url: str, timeout: int = 20) -> str:
    return _request(url, timeout).decode("utf-8", "ignore")


def strip_html(value: str) -> str:
    """Turns a Steam HTML blurb into readable plain text."""
    if not value:
        return ""
    text = _BREAK_RE.sub("\n", value)
    text = _PARA_RE.sub("\n\n", text)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def achievement_icon_url(appid, icon: str) -> str:
    if not icon:
        return ""
    if icon.startswith("http://") or icon.startswith("https://"):
        return icon
    return ("https://cdn.fastly.steamstatic.com/steamcommunity/public/"
            f"images/apps/{appid}/{icon}")


# ---------------------------------------------------------------------------
#  Local Steam data
# ---------------------------------------------------------------------------
_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
_CLIP_STAMP_RE = re.compile(r"_(\d{8})_(\d{6})$")


def _clip_label(name: str) -> str:
    match = _CLIP_STAMP_RE.search(str(name or ""))
    if not match:
        return str(name or "")
    day, clock = match.group(1), match.group(2)
    return f"{day[6:8]}.{day[4:6]}.{day[0:4]} {clock[0:2]}:{clock[2:4]}"


def _user_roots(steam_path):
    if not steam_path:
        return []
    root = Path(steam_path) / "userdata"
    if not root.is_dir():
        return []
    try:
        return [p for p in root.iterdir() if p.is_dir()]
    except OSError:
        return []


def local_user_media(steam_path: str, appid) -> dict:
    """Player-made screenshots and recorded clips for one appid.

    Steam keeps both under ``userdata``.  Screenshots are plain images, while
    game recordings are HEVC DASH clips (``session.mpd`` + fMP4 chunks) that
    QMediaPlayer cannot open directly, so the clip dict carries the manifest
    path and the viewer builds a local HLS playlist on demand.
    """
    result = {"screenshots": [], "videos": []}
    appid = str(appid)
    shots = []
    clips = []
    for user in _user_roots(steam_path):
        folder = user / "760" / "remote" / appid / "screenshots"
        if folder.is_dir():
            try:
                files = list(folder.iterdir())
            except OSError:
                files = []
            for item in files:
                if item.suffix.lower() not in _IMAGE_SUFFIXES:
                    continue
                try:
                    shots.append((item.stat().st_mtime, str(item)))
                except OSError:
                    continue

        recordings = user / "gamerecordings" / "clips"
        if not recordings.is_dir():
            continue
        try:
            folders = [p for p in recordings.iterdir() if p.is_dir()]
        except OSError:
            folders = []
        for clip in folders:
            if not clip.name.startswith(f"clip_{appid}_"):
                continue
            mpd = None
            try:
                candidates = sorted(clip.glob("video/*/session.mpd"))
                if not candidates:
                    candidates = sorted(clip.rglob("session.mpd"))
                if candidates:
                    mpd = candidates[0]
            except OSError:
                mpd = None
            if mpd is None:
                continue
            thumb = clip / "thumbnail.jpg"
            try:
                stamp = clip.stat().st_mtime
            except OSError:
                stamp = 0
            clips.append({
                "path": str(clip),
                "mpd": str(mpd),
                "thumb": str(thumb) if thumb.exists() else "",
                "name": clip.name,
                "label": _clip_label(clip.name),
                "mtime": stamp,
            })

    shots.sort(reverse=True)
    clips.sort(key=lambda c: c.get("mtime") or 0, reverse=True)
    result["screenshots"] = [path for _, path in shots]
    result["videos"] = clips
    return result


def local_screenshots(steam_path: str, appid) -> list:
    """Backward-compatible helper used by older callers."""
    return local_user_media(steam_path, appid)["screenshots"]


# ---------------------------------------------------------------------------
#  Local clip playback (DASH chunks -> tiny HLS playlist)
# ---------------------------------------------------------------------------
def _iso_duration(value: str) -> float:
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?", value or "")
    if not match:
        return 0.0
    return (int(match.group(1) or 0) * 3600
            + int(match.group(2) or 0) * 60
            + float(match.group(3) or 0))


def _clip_tracks(mpd_path: Path) -> list:
    """Reads stream ids and segment lists from a Steam ``session.mpd``."""
    try:
        root = ET.parse(mpd_path).getroot()
    except Exception as exc:
        log.info("Clip manifest read failed (%s): %s", mpd_path, exc)
        root = None

    base = mpd_path.parent
    total = (_iso_duration(root.get("mediaPresentationDuration", ""))
             if root is not None else 0.0)
    tracks = []
    if root is not None:
        for node in root.iter():
            if not node.tag.endswith("AdaptationSet"):
                continue
            content = (node.get("contentType") or "").lower()
            for rep in list(node):
                if not rep.tag.endswith("Representation"):
                    continue
                rid = rep.get("id", "0")
                duration = 0.0
                template = next(
                    (c for c in list(rep) if c.tag.endswith("SegmentTemplate")),
                    None)
                if template is not None:
                    try:
                        timescale = int(template.get("timescale") or 1000000)
                        if timescale > 0:
                            duration = (float(template.get("duration") or 0)
                                        / timescale)
                    except (TypeError, ValueError):
                        duration = 0.0
                init_path = base / f"init-stream{rid}.m4s"
                segments = sorted(base.glob(f"chunk-stream{rid}-*.m4s"))
                if not init_path.exists() or not segments:
                    continue
                tracks.append({
                    "kind": "audio" if content == "audio" else "video",
                    "init": init_path,
                    "segments": segments,
                    "duration": duration,
                })

    if not tracks:
        # Fallback for manifests without a usable SegmentTemplate.
        for kind, rid in (("video", "0"), ("audio", "1")):
            init_path = base / f"init-stream{rid}.m4s"
            segments = sorted(base.glob(f"chunk-stream{rid}-*.m4s"))
            if init_path.exists() and segments:
                tracks.append({
                    "kind": kind,
                    "init": init_path,
                    "segments": segments,
                    "duration": 0.0,
                })

    if total > 0:
        for track in tracks:
            if track["duration"] <= 0 and track["segments"]:
                track["duration"] = total / len(track["segments"])
    return tracks


def ensure_clip_playlist(clip) -> str:
    """Builds (once) a local HLS playlist for a Steam game recording.

    The FFmpeg backend behind QMediaPlayer plays HLS fine but rejects Steam's
    HEVC DASH manifest, so the existing fMP4 chunks are exposed through a
    playlist stored in the launcher cache.  Returns the master playlist path
    or an empty string when the clip cannot be read.
    """
    mpd = Path(clip.get("mpd") or "") if isinstance(clip, dict) \
        else Path(str(clip or ""))
    if not mpd.is_file():
        return ""

    try:
        stat = mpd.stat()
        stamp = f"{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        stamp = "0"
    token = hashlib.md5(
        f"{mpd}|{stamp}".encode("utf-8", "ignore")).hexdigest()[:12]
    out = CLIP_CACHE_DIR / token
    master = out / "master.m3u8"
    if master.exists():
        return str(master)

    tracks = _clip_tracks(mpd)
    video = next((t for t in tracks if t["kind"] == "video"), None)
    audio = next((t for t in tracks if t["kind"] == "audio"), None)
    if video is None:
        return ""

    def native(path):
        return str(path).replace("\\", "/")

    def write_playlist(name, track):
        duration = track["duration"] or 3.0
        target = max(1, int(math.ceil(duration)))
        lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:7",
            f"#EXT-X-TARGETDURATION:{target}",
            "#EXT-X-PLAYLIST-TYPE:VOD",
            f'#EXT-X-MAP:URI="{native(track["init"])}"',
        ]
        for segment in track["segments"]:
            lines.append(f"#EXTINF:{duration:.3f},")
            lines.append(native(segment))
        lines.append("#EXT-X-ENDLIST")
        path = out / name
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    try:
        out.mkdir(parents=True, exist_ok=True)
        video_path = write_playlist("video.m3u8", video)
        master_lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:7",
            "#EXT-X-INDEPENDENT-SEGMENTS",
        ]
        if audio is not None:
            audio_path = write_playlist("audio.m3u8", audio)
            master_lines.append(
                '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aud",NAME="audio",'
                f'DEFAULT=YES,AUTOSELECT=YES,URI="{native(audio_path)}"')
            master_lines.append(
                '#EXT-X-STREAM-INF:BANDWIDTH=12000000,AUDIO="aud"')
        else:
            master_lines.append("#EXT-X-STREAM-INF:BANDWIDTH=12000000")
        master_lines.append(native(video_path))
        master.write_text("\n".join(master_lines), encoding="utf-8")
    except Exception as exc:
        log.info("Clip playlist build failed (%s): %s", mpd, exc)
        return ""
    return str(master)


# ---------------------------------------------------------------------------
#  Public Steam endpoints
# ---------------------------------------------------------------------------
def _max_url(value) -> str:
    """Steam used to return ``{"max": url}`` objects for mp4/webm."""
    if isinstance(value, dict):
        return value.get("max", "") or ""
    return value or ""


def fetch_store(appid, lang="english") -> dict:
    url = ("https://store.steampowered.com/api/appdetails"
           f"?appids={appid}&cc=us&l={lang}")
    payload = _json(url)
    entry = payload.get(str(appid)) or {}
    if not entry.get("success"):
        return {}
    data = entry.get("data") or {}
    release = data.get("release_date") or {}
    return {
        "name": data.get("name", ""),
        "short_description": strip_html(data.get("short_description", "")),
        "about": strip_html(data.get("detailed_description", ""))[:2600],
        "header_image": data.get("header_image", ""),
        "capsule": data.get("capsule_image", "") or data.get("header_image", ""),
        "background": data.get("background_raw", "") or data.get("background", ""),
        "developers": list(data.get("developers") or []),
        "publishers": list(data.get("publishers") or []),
        "genres": [g.get("description", "") for g in data.get("genres") or []],
        "categories": [c.get("description", "") for c in data.get("categories") or []],
        "release_date": release.get("date", ""),
        "coming_soon": bool(release.get("coming_soon")),
        "metacritic": (data.get("metacritic") or {}).get("score"),
        "screenshots": [
            {"thumb": s.get("path_thumbnail", ""), "full": s.get("path_full", "")}
            for s in data.get("screenshots") or []
        ],
        "movies": [
            {
                "name": m.get("name", ""),
                "thumb": m.get("thumbnail", ""),
                # Steam now ships HLS/DASH manifests instead of direct files.
                # HLS is the only format the Qt FFmpeg backend plays here.
                "hls": m.get("hls_h264", "") or "",
                "dash": m.get("dash_h264", "") or m.get("dash_av1", "") or "",
                "webm": _max_url(m.get("webm")),
                "mp4": _max_url(m.get("mp4")),
            }
            for m in data.get("movies") or []
        ],
        "store_url": f"https://store.steampowered.com/app/{appid}/",
    }


def fetch_achievements(appid, lang="english") -> dict:
    """Reads the achievement schema + global percentages from Steam.

    Steam renders both blocks into the ``valve-ssr-data`` JSON island.  The
    schema is inside ``renderContext.queryData`` (itself a JSON string), the
    global unlock percentages sit in a second query of the same document.
    """
    url = f"https://steamcommunity.com/stats/{appid}/achievements?l={lang}"
    page = _text(url)
    match = _SSR_RE.search(page)
    if not match:
        return {"achievements": [], "total": 0, "average": 0}

    outer = json.loads(match.group(1))
    raw = (outer.get("renderContext") or {}).get("queryData") or "{}"
    query = json.loads(raw) if isinstance(raw, str) else raw
    groups = []
    percentages = {}
    for item in query.get("queries") or []:
        state = item.get("state") or {}
        data = state.get("data")
        if not isinstance(data, dict):
            continue
        if "groups" in data and isinstance(data["groups"], list):
            groups = data["groups"]
        if "percentages" in data and isinstance(data["percentages"], dict):
            percentages = data["percentages"]

    achievements = []
    for group in groups:
        for item in group.get("achievements") or []:
            key = str(item.get("internal_key", ""))
            percent = percentages.get(key)
            try:
                percent = round(float(percent), 1) if percent is not None else None
            except (TypeError, ValueError):
                percent = None
            achievements.append({
                "api_name": item.get("api_name", ""),
                "name": item.get("name", ""),
                "description": item.get("description", ""),
                "hidden": bool(item.get("hidden")),
                "icon": achievement_icon_url(
                    appid, item.get("icon_achieved") or item.get("icon_unachieved")),
                "percent": percent,
            })

    values = [a["percent"] for a in achievements if a["percent"] is not None]
    average = round(sum(values) / len(values), 1) if values else 0
    return {
        "achievements": achievements,
        "total": len(achievements),
        "average": average,
    }


def fetch_all(appid, lang="english", steam_path="") -> dict:
    store = {}
    achievements = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        store_future = pool.submit(fetch_store, appid, lang)
        achievements_future = pool.submit(fetch_achievements, appid, lang)
        try:
            store = store_future.result()
        except Exception as exc:
            log.info("Steam store details unavailable for %s: %s", appid, exc)
        try:
            achievements = achievements_future.result()
        except Exception as exc:
            log.info("Steam achievements unavailable for %s: %s", appid, exc)

    user_media = local_user_media(steam_path, appid)
    return {
        "appid": str(appid),
        "lang": lang,
        "schema": CACHE_SCHEMA,
        "fetched_at": int(time.time()),
        "store": store,
        "achievements": achievements,
        "local_screenshots": user_media["screenshots"],
        "user_media": user_media,
    }


# ---------------------------------------------------------------------------
#  Cache + background task
# ---------------------------------------------------------------------------
def cache_path(appid, lang="english") -> Path:
    return STEAM_CACHE_DIR / f"{appid}_{lang}.json"


def load_cache(appid, lang="english"):
    path = cache_path(appid, lang)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except Exception as exc:
        log.info("Steam cache read failed (%s): %s", path, exc)
    return None


def save_cache(appid, lang, payload) -> None:
    try:
        STEAM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        save_json(cache_path(appid, lang), payload)
    except Exception as exc:
        log.info("Steam cache write failed: %s", exc)


class SteamInfoSignals(QObject):
    loaded = pyqtSignal(str, dict)
    failed = pyqtSignal(str, str)


class SteamInfoTask(QRunnable):
    """Loads Steam info for one library key without blocking the window."""

    def __init__(self, key, appid, lang="english", steam_path="", force=False):
        super().__init__()
        self.key = str(key)
        self.appid = str(appid)
        self.lang = lang
        self.steam_path = steam_path or ""
        self.force = bool(force)
        self.signals = SteamInfoSignals()

    def run(self):
        cached = load_cache(self.appid, self.lang)
        if cached and not self.force:
            age = time.time() - float(cached.get("fetched_at", 0) or 0)
            fresh_schema = cached.get("schema") == CACHE_SCHEMA
            if fresh_schema and age < CACHE_TTL:
                self.signals.loaded.emit(self.key, cached)
                return
        try:
            payload = fetch_all(self.appid, self.lang, self.steam_path)
            # Keep old local media if a refresh came back empty (Steam may be
            # temporarily unreadable, or the library moved).
            if cached:
                old_media = cached.get("user_media") or {}
                new_media = payload.get("user_media") or {}
                if not new_media.get("screenshots") and old_media.get("screenshots"):
                    new_media["screenshots"] = old_media["screenshots"]
                if not new_media.get("videos") and old_media.get("videos"):
                    new_media["videos"] = old_media["videos"]
                payload["user_media"] = new_media
                payload["local_screenshots"] = new_media.get("screenshots") or []
            save_cache(self.appid, self.lang, payload)
            self.signals.loaded.emit(self.key, payload)
        except Exception as exc:
            log.info("Steam info failed for %s: %s", self.appid, exc)
            if cached:
                self.signals.loaded.emit(self.key, cached)
            else:
                self.signals.failed.emit(self.key, str(exc))
