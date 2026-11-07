"""Cover image cache: disk cache, memory cache and the background loader."""

import hashlib
import logging
import os
import re
import threading
import urllib.request
from collections import OrderedDict
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, Qt, pyqtSignal
from PyQt6.QtGui import QImage

from .paths import COVERS_DIR, USER_AGENT

log = logging.getLogger("Devers")

COVER_MEMORY_LIMIT = 120
# Full-resolution media (screenshots) is much heavier than a 480px cover, so
# keep only a handful of those in memory regardless of the cover cache size.
FULL_MEMORY_LIMIT = 8
COVER_MEMORY_MAX_SIDE = 480

_cover_memory = OrderedDict()
_cover_memory_lock = threading.Lock()
_cover_failures = set()


def _cover_hash(source: str) -> str:
    return hashlib.sha1(source.encode("utf-8", "ignore")).hexdigest()


def _cover_cache_file(source: str) -> Path:
    return COVERS_DIR / f"{_cover_hash(source)}.img"


def store_cover_bytes(source: str, data: bytes) -> str:
    """Saves raw image bytes and returns the cached file path ("" on error)."""
    if not data:
        return ""
    path = _cover_cache_file(source)
    try:
        if path.exists() and path.stat().st_size == len(data):
            return str(path)
        COVERS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        return str(path)
    except Exception as e:
        log.warning(f"Не удалось сохранить обложку в кеш: {e}")
        return ""


def _cover_url_candidates(url: str):
    """Steam header images do not exist for every app, so try other assets."""
    yield url
    match = re.search(r"/steam/apps/(\d+)/header\.jpg$", url)
    if match:
        appid = match.group(1)
        for name in ("library_600x900.jpg", "capsule_616x353.jpg",
                     "capsule_231x87.jpg", "logo.png"):
            yield f"https://shared.steamstatic.com/store_item_assets/steam/apps/{appid}/{name}"


def download_cover(url: str) -> str:
    """Downloads a remote cover once and stores it on disk."""
    path = _cover_cache_file(url)
    try:
        if path.exists() and path.stat().st_size > 0:
            return str(path)
    except OSError:
        pass
    if url in _cover_failures:
        return ""

    for candidate in _cover_url_candidates(url):
        try:
            req = urllib.request.Request(candidate, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            if not data:
                continue
            saved = store_cover_bytes(url, data)
            if saved:
                log.info(f"Обложка загружена и закеширована: {candidate}")
                return saved
        except Exception as e:
            log.warning(f"Не удалось скачать обложку {candidate}: {e}")

    _cover_failures.add(url)
    return ""


def _remember_cover(key: str, image: QImage):
    with _cover_memory_lock:
        _cover_memory[key] = image
        _cover_memory.move_to_end(key)
        if key.endswith("|full"):
            full_keys = [k for k in _cover_memory if k.endswith("|full")]
            while len(full_keys) > FULL_MEMORY_LIMIT:
                _cover_memory.pop(full_keys.pop(0), None)
        while len(_cover_memory) > COVER_MEMORY_LIMIT:
            _cover_memory.popitem(last=False)


def load_cover_image(path: str = "", url: str = "", data: bytes = b"",
                     max_side: int = COVER_MEMORY_MAX_SIDE,
                     memory_key: str = "") -> QImage:
    """Loads a cover from memory cache, disk, URL or raw bytes (thread-safe).

    ``max_side=0`` keeps the original resolution — used by the media viewer so
    full-size screenshots stay sharp.  A custom ``memory_key`` keeps full-size
    entries separate from the small cover cache.
    """
    key = memory_key or path or url or (_cover_hash(data) if data else "")
    if not key:
        return QImage()
    cache_key = f"{key}|full" if max_side <= 0 else key

    with _cover_memory_lock:
        if cache_key in _cover_memory:
            _cover_memory.move_to_end(cache_key)
            return _cover_memory[cache_key]
    if url and url in _cover_failures:
        return QImage()

    image = QImage()
    try:
        if data:
            image.loadFromData(data)
        else:
            local = path
            if url:
                local = download_cover(url)
                cache_key = f"{url}|full" if max_side <= 0 else url
            if local and os.path.exists(local):
                image = QImage(local)
    except Exception as e:
        log.warning(f"Обложка не загрузилась ({key}): {e}")

    if not image.isNull():
        if max_side > 0 and max(image.width(), image.height()) > max_side:
            image = image.scaled(
                max_side, max_side,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        _remember_cover(cache_key, image)
    return image


def clear_cover_cache() -> None:
    with _cover_memory_lock:
        _cover_memory.clear()
    _cover_failures.clear()
    if COVERS_DIR.exists():
        for item in COVERS_DIR.iterdir():
            try:
                if item.is_file():
                    item.unlink()
            except OSError:
                pass


def cover_cache_stats():
    count = 0
    size = 0
    if COVERS_DIR.exists():
        for item in COVERS_DIR.iterdir():
            try:
                if item.is_file():
                    count += 1
                    size += item.stat().st_size
            except OSError:
                pass
    return count, size


class CoverLoader(QRunnable):
    class Signals(QObject):
        loaded = pyqtSignal(str, QImage)

    def __init__(self, key, path="", url="", data=None,
                 max_side=COVER_MEMORY_MAX_SIDE, memory_key=""):
        super().__init__()
        self.key = key
        self.path = path
        self.url = url
        self.data = data or b""
        self.max_side = max_side
        self.memory_key = memory_key
        self.signals = CoverLoader.Signals()

    def run(self):
        try:
            image = load_cover_image(
                self.path, self.url, self.data,
                max_side=self.max_side, memory_key=self.memory_key)
        except Exception as e:
            log.warning(f"Обложка не загрузилась: {e}")
            image = QImage()
        self.signals.loaded.emit(self.key, image)
