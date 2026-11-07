"""Game file helpers, archive scanning and the library manifest scanner."""

import json
import logging
import os
import re
import zipfile
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from .covers import _cover_cache_file, store_cover_bytes
from .i18n import L
from .paths import SUPPORTED_EXTENSIONS
from .utils import prettify_name

log = logging.getLogger("Devers")

EXE_BLACKLIST = (
    "unins", "uninstall", "vcredist", "vc_redist", "dxsetup", "dxwebsetup",
    "setup", "installer", "crash", "report", "unitycrashhandler",
    "notification_helper", "touchup", "activate",
)


def _exe_score(name: str, size: int, depth: int) -> float:
    low = os.path.basename(name).lower()
    if not low.endswith(".exe"):
        return -1
    if any(bad in low for bad in EXE_BLACKLIST):
        return -1
    return size + max(0, 3 - depth) * 1_000_000


def detect_executable(root) -> str:
    """Finds the most likely game executable inside an extracted folder."""
    best = None
    root = str(root)
    if not os.path.isdir(root):
        return ""
    for cur, dirs, files in os.walk(root):
        rel = os.path.relpath(cur, root)
        depth = 0 if rel == "." else len(Path(rel).parts)
        if depth >= 3:
            dirs[:] = []
        for f in files:
            if not f.lower().endswith(".exe"):
                continue
            full = os.path.join(cur, f)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            score = _exe_score(f, size, depth)
            if score < 0:
                continue
            if best is None or score > best[0]:
                best = (score, full)
    return best[1] if best else ""


def detect_exe_in_archive(zf) -> str:
    """Finds the most likely game executable inside a zip/dvp archive."""
    best = None
    for info in zf.infolist():
        if info.is_dir() or not info.filename.lower().endswith(".exe"):
            continue
        depth = info.filename.count("/")
        score = _exe_score(info.filename, info.file_size, depth)
        if score < 0:
            continue
        if best is None or score > best[0]:
            best = (score, info.filename)
    return best[1] if best else ""


def find_cover_in_archive(zf):
    """Returns (bytes, extension) of the first cover-like image in an archive."""
    pattern = re.compile(r"(^|/)(cover|header|banner|poster|artwork)[^/]*\.(png|jpe?g|webp|bmp)$", re.I)
    for info in zf.infolist():
        if info.is_dir():
            continue
        if pattern.search(info.filename):
            try:
                if 0 < info.file_size <= 8 * 1024 * 1024:
                    return zf.read(info.filename), os.path.splitext(info.filename)[1].lower()
            except Exception:
                continue
    return None


class ExtractWorker(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished_extract = pyqtSignal(str, bool, str)

    def __init__(self, dvp_path, extract_to):
        super().__init__()
        self.dvp_path = dvp_path
        self.extract_to = extract_to

    def run(self):
        try:
            self.status.emit(L.t("launch.extracting", name=""))
            os.makedirs(self.extract_to, exist_ok=True)
            with zipfile.ZipFile(self.dvp_path, "r") as zf:
                names = zf.namelist()
                total = len(names)
                for i, name in enumerate(names):
                    zf.extract(name, self.extract_to)
                    if i % max(1, total // 100) == 0:
                        self.progress.emit(int((i / total) * 100))
                        self.status.emit(f"{i}/{total}")
            self.progress.emit(100)
            self.finished_extract.emit(self.extract_to, True, "")
        except zipfile.BadZipFile as e:
            self.finished_extract.emit("", False, f"Bad archive: {e}")
        except Exception as e:
            self.finished_extract.emit("", False, str(e))


class ManifestScanner(QThread):
    """Scans the games folder (.dvp/.zip/.exe/shortcuts) and linked library."""

    finished = pyqtSignal(dict)

    def __init__(self, games_dir, cache, external=None):
        super().__init__()
        self.games_dir = games_dir
        self.cache = cache or {}
        self.external = external or {}

    def _type_for(self, ext: str) -> str:
        if ext == ".dvp":
            return "dvp"
        if ext == ".zip":
            return "zip"
        if ext in (".bat", ".cmd"):
            return "script"
        if ext in (".lnk", ".url"):
            return "shortcut"
        return "exe"

    def _scan_archive(self, p: str, f: str, entry: dict) -> None:
        cover_source = f"{entry['type']}:{f}:{int(entry['mtime'])}"
        cached_cover = _cover_cache_file(cover_source)
        try:
            with zipfile.ZipFile(p, "r") as zf:
                names = zf.namelist()
                manifest = None
                if "manifest.json" in names:
                    try:
                        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                    except Exception as e:
                        entry["error"] = f"Bad manifest: {e}"

                if manifest:
                    entry["name"] = manifest.get("name", entry["name"])
                    entry["created"] = manifest.get("created", "")
                    exe_name = manifest.get("exe", "") or ""
                    if exe_name and exe_name != "unknown":
                        entry["exe"] = os.path.basename(exe_name)
                    cover_hex = manifest.get("cover_data")
                    if cover_hex and not (cached_cover.exists() and cached_cover.stat().st_size > 0):
                        try:
                            store_cover_bytes(cover_source, bytes.fromhex(cover_hex))
                        except Exception as e:
                            log.warning(f"Битая обложка в {f}: {e}")

                if not entry.get("exe"):
                    found = detect_exe_in_archive(zf)
                    if found:
                        entry["exe"] = os.path.basename(found)
                        entry["exe_in_archive"] = found

                if not (cached_cover.exists() and cached_cover.stat().st_size > 0):
                    found_cover = find_cover_in_archive(zf)
                    if found_cover:
                        data, ext = found_cover
                        store_cover_bytes(cover_source, data)
                        entry["cover_ext"] = ext

            if cached_cover.exists() and cached_cover.stat().st_size > 0:
                entry["cover_path"] = str(cached_cover)
        except zipfile.BadZipFile:
            entry["error"] = f"Corrupted {entry['type']}"
        except Exception as e:
            entry["error"] = f"Read error: {e}"

    def _external_entry(self, key: str, entry: dict) -> dict:
        """Refreshes size/exe data for games that live outside the games folder."""
        meta = dict(entry)
        meta["key"] = key
        meta["external"] = True
        path = meta.get("path", "")
        if meta.get("type") == "folder":
            if not os.path.isdir(path):
                meta["error"] = "Folder missing"
            else:
                if not meta.get("exe") or not os.path.exists(meta.get("exe", "")):
                    meta["exe"] = detect_executable(path)
                try:
                    meta["size"] = dir_size_cached(path)
                except Exception:
                    pass
        elif path and os.path.isfile(path):
            try:
                meta["size"] = os.path.getsize(path)
            except OSError:
                pass
        elif meta.get("type") != "steam" and path and not os.path.exists(path):
            meta["error"] = "File missing"
        meta.setdefault("name", prettify_name(Path(path).stem) if path else key)
        return meta

    def run(self):
        manifests = {}
        try:
            files = sorted(os.listdir(self.games_dir))
        except Exception as e:
            log.error(f"Не могу прочитать папку игр: {e}")
            files = []

        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            p = os.path.join(self.games_dir, f)
            try:
                mtime = os.path.getmtime(p)
                size = os.path.getsize(p)
            except OSError:
                continue

            game_type = self._type_for(ext)
            cached = self.cache.get(f, {})
            cached_cover_ok = (not cached.get("cover_path")
                               or os.path.exists(cached.get("cover_path", "")))
            if (cached.get("mtime") == mtime and cached.get("size") == size
                    and cached.get("type") == game_type and cached_cover_ok):
                manifests[f] = cached
                continue

            entry = {
                "mtime": mtime, "size": size, "path": p, "type": game_type,
                "name": prettify_name(Path(f).stem), "exe": "", "exe_in_archive": "",
                "created": "", "cover_path": "", "cover_url": "", "error": None,
            }

            if game_type in ("dvp", "zip"):
                self._scan_archive(p, f, entry)
            elif game_type in ("exe", "script"):
                entry["exe"] = p

            manifests[f] = entry

        for key, ext_entry in self.external.items():
            try:
                manifests[key] = self._external_entry(key, ext_entry)
            except Exception as e:
                log.warning(f"Пропущена внешняя игра {key}: {e}")

        self.finished.emit(manifests)


_dir_size_cache = {}


def dir_size_cached(path: str) -> int:
    """Cached folder size — external game folders can be huge."""
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return 0
    cached = _dir_size_cache.get(path)
    if cached and cached[0] == stamp:
        return cached[1]
    from .utils import dir_size
    size = dir_size(path)
    _dir_size_cache[path] = (stamp, size)
    return size
