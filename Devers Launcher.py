VERSION = "1.4"

import sys
import os
import json
import zipfile
import shutil
import subprocess
import tempfile
import time
import logging
import hashlib
import re
import threading
import webbrowser
import urllib.request
import urllib.error
from collections import OrderedDict
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QFrame,
                             QMessageBox, QProgressBar, QScrollArea, QDialog, 
                             QLineEdit, QDialogButtonBox, QCheckBox,
                             QFileDialog, QMenu, QSystemTrayIcon, QComboBox,
                             QGraphicsOpacityEffect, QSizePolicy, QGridLayout,
                             QInputDialog, QStackedWidget)
from PyQt6.QtCore import (Qt, QThread, pyqtSignal, QTimer, QSize, QPropertyAnimation, 
                          QEasingCurve, QParallelAnimationGroup, QRunnable, QThreadPool,
                          QObject, QPoint)
from PyQt6.QtGui import (QMovie, QPixmap, QIcon, QAction, QKeySequence, QShortcut,
                         QPainter, QColor, QBrush, QFont, QImage, QPainterPath,
                         QFontMetrics)


def get_base_dir() -> Path:
    """Корневая папка приложения (рядом с .exe или main.py)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR          = get_base_dir()
DATA_DIR          = BASE_DIR / "data"
LOCALIZATION_DIR  = DATA_DIR / "localization"
ICON_DIR          = DATA_DIR / "icon"
GAMES_DIR         = DATA_DIR / "games"
SAVE_DIR          = DATA_DIR / "save"
CACHE_DIR         = SAVE_DIR / "cache"
COVERS_DIR        = CACHE_DIR / "covers"
UPDATES_DIR       = SAVE_DIR / "updates"

CONFIG_FILE       = SAVE_DIR / "devers_config.json"
CACHE_FILE        = SAVE_DIR / "cache.json"
LIBRARY_FILE      = SAVE_DIR / "library.json"
STATS_FILE        = SAVE_DIR / "stats.json"
LOG_FILE          = SAVE_DIR / "launcher.log"

GIF_PATH          = ICON_DIR / "devers_gif.gif"
APP_ICON          = ICON_DIR / "app.ico"
ICONS_DIR         = ICON_DIR 

CONFIG_PATH      = str(CONFIG_FILE)
CACHE_PATH       = str(CACHE_FILE)
LIBRARY_PATH     = str(LIBRARY_FILE)
STATS_PATH       = str(STATS_FILE)
LOG_PATH         = str(LOG_FILE)
GIF_PATH_S       = str(GIF_PATH)
APP_ICON_S       = str(APP_ICON)
ICONS_DIR_S      = str(ICONS_DIR)
LOCALIZATION_DIR_S = str(LOCALIZATION_DIR)


def ensure_dirs() -> None:
    """Создаёт всю структуру data/ при старте."""
    for d in (DATA_DIR, LOCALIZATION_DIR, ICON_DIR,
              GAMES_DIR, SAVE_DIR, CACHE_DIR, COVERS_DIR, UPDATES_DIR):
        d.mkdir(parents=True, exist_ok=True)


def migrate_legacy() -> None:
    """Переносит файлы из старой структуры (всё в корне) в data/."""
    legacy_files = {
        BASE_DIR / "devers_config.json": CONFIG_FILE,
        BASE_DIR / "cache.json":         CACHE_FILE,
        BASE_DIR / "library.json":       LIBRARY_FILE,
        BASE_DIR / "stats.json":         STATS_FILE,
        BASE_DIR / "launcher.log":       LOG_FILE,
    }
    for old, new in legacy_files.items():
        if old.exists() and not new.exists():
            try:
                shutil.move(str(old), str(new))
            except Exception:
                pass

    old_loc = BASE_DIR / "localization"
    if old_loc.is_dir():
        for item in old_loc.iterdir():
            target = LOCALIZATION_DIR / item.name
            if not target.exists():
                try:
                    shutil.move(str(item), str(target))
                except Exception:
                    pass
        try:
            old_loc.rmdir()
        except OSError:
            pass

    old_icons = BASE_DIR / "icons"
    if old_icons.is_dir():
        for item in old_icons.iterdir():
            target = ICON_DIR / item.name
            if not target.exists():
                try:
                    shutil.move(str(item), str(target))
                except Exception:
                    pass
        try:
            old_icons.rmdir()
        except OSError:
            pass

    for fname in ("devers_gif.gif", "app.ico"):
        old_f = BASE_DIR / fname
        if old_f.exists():
            target = ICON_DIR / fname
            if not target.exists():
                try:
                    shutil.move(str(old_f), str(target))
                except Exception:
                    pass

    old_games = BASE_DIR / "games"
    if old_games.is_dir():
        for item in old_games.iterdir():
            target = GAMES_DIR / item.name
            if not target.exists():
                try:
                    shutil.move(str(item), str(target))
                except Exception:
                    pass
        try:
            old_games.rmdir()
        except OSError:
            pass


ensure_dirs()
migrate_legacy()
ensure_dirs()


DEFAULT_CONFIG = {
    "games_dir": str(GAMES_DIR),
    "temp_dir": str(CACHE_DIR),
    "auto_cleanup": True,
    "show_extensions": False,
    "sidebar_collapsed": False,
    "favorites": [],
    "sort_mode": "name",
    "language": "en",
    "check_updates": True,
    "last_update_check": 0,
    "animations": True,
    "animation_style": "slide",
    "animation_speed": "normal",
    "auto_steam_import": True,
    "steam_path": "",
    "steam_hidden": [],
    "steam_import_done": False,
}

ARCHIVE_EXTENSIONS = (".dvp", ".zip")
DIRECT_EXTENSIONS  = (".exe", ".bat", ".cmd", ".lnk", ".url")
SUPPORTED_EXTENSIONS = ARCHIVE_EXTENSIONS + DIRECT_EXTENSIONS

GITHUB_REPO        = "Made-by-One/Devers-Launcher"
GITHUB_RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"
UPDATE_CHECK_INTERVAL = 6 * 60 * 60
USER_AGENT = f"DeversLauncher/{VERSION}"

STEAM_CDN_HEADER = "https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("Devers")
log.info(f"=== Devers Launcher v{VERSION} ===")
log.info(f"BASE_DIR: {BASE_DIR}")
log.info(f"DATA_DIR: {DATA_DIR}")


EN_DEFAULT = {
    "_name": "English",
    "_code": "en",

    "app.title": "Devers Launcher",
    "app.subtitle": f"VERSION {VERSION}",
    "app.description": "Light game launcher for .dvp, .zip and .exe games.\nExtracts and runs games right from the launcher,\nautomatically picks up your Steam library.\nNo junk left on your disk.",
    "app.footer": "© 2026 Made by One Studio  •  All games are stored locally",

    "sidebar.home": "Home",
    "sidebar.library": "Library",
    "sidebar.favorites": "Favorites",
    "sidebar.about": "About",
    "sidebar.settings": "Settings",
    "sidebar.collapse": "Collapse / Expand",

    "library.title": "Game Library",
    "library.search_placeholder": "Search games...",
    "library.refresh": "Refresh",
    "library.sort.name": "By name",
    "library.sort.size": "By size",
    "library.sort.date": "By date",
    "library.sort.time": "By playtime",
    "library.sort.favorites": "Favorites first",
    "library.empty": "Library is empty.\nDrag .dvp, .zip, .exe files, shortcuts or folders into the window,\nor add them with the 'Add game' button.",
    "favorites.empty": "Favorites are empty.\nClick the star on any game card to add it here.",
    "library.found": "Found games: {count}",
    "library.not_played": "not played yet",
    "library.add_game": "Add game",
    "library.add_folder": "Add folder",
    "library.steam": "Steam",
    "library.added": "Added games: {count}",

    "card.error": "ERROR",
    "card.no_cover": "NO COVER",
    "card.play": "Play",
    "card.favorite": "Add to favorites",
    "card.unfavorite": "Remove from favorites",

    "menu.play": "Play",
    "menu.favorite_add": "Add to favorites",
    "menu.favorite_remove": "Remove from favorites",
    "menu.open_folder": "Open game folder",
    "menu.remove": "Remove from library",
    "menu.rename": "Rename",
    "menu.delete": "Delete",
    "menu.separator": "",

    "dialog.rename.title": "Rename",
    "dialog.rename.prompt": "New name:",
    "dialog.delete.title": "Delete",
    "dialog.delete.confirm": "Delete '{name}'?",
    "dialog.delete.error": "Failed to delete: {error}",
    "dialog.remove.title": "Remove from library",
    "dialog.remove.confirm": "Remove '{name}' from the library?\nThe game files will not be deleted.",
    "dialog.add.title": "Add games",
    "dialog.add.filter": "Games (*.dvp *.zip *.exe *.bat *.cmd *.lnk *.url);;All files (*)",
    "dialog.add.none": "No supported files selected.",
    "dialog.add.error": "Could not add the game: {error}",
    "dialog.add.exists": "'{name}' is already in the library.",
    "dialog.folder.title": "Select game folder",

    "launch.extracting": "Extracting «{name}»...",
    "launch.extract_error": "Extraction error",
    "launch.exe_missing": "File '{exe}' not found in archive",
    "launch.start_error": "Launch error",
    "launch.already_running": "Another game is already running!",
    "launch.playing": "▶  {name} launched (PID {pid})",
    "launch.closed": "Game closed. Cleaning up...",
    "launch.cleaned": "Cleaned",
    "launch.corrupted": "Game is corrupted:\n{error}",
    "launch.no_exe": "No executable file found inside «{name}»",
    "launch.steam_launch": "Launching «{name}» via Steam...",
    "launch.steam_error": "Could not launch via Steam: {error}",
    "launch.direct": "▶  {name} launched",
    "launch.missing_path": "Game files not found:\n{path}",

    "settings.title": "Settings",
    "settings.subtitle": "Manage storage and launcher behavior",
    "settings.section.storage": "STORAGE",
    "settings.section.temp": "TEMPORARY FILES",
    "settings.section.interface": "INTERFACE",
    "settings.section.language": "LANGUAGE",
    "settings.section.steam": "STEAM",
    "settings.section.updates": "UPDATES",
    "settings.section.cache": "IMAGE CACHE",
    "settings.section.animations": "ANIMATIONS",
    "settings.animations": "Enable smooth interface animations",
    "settings.animation_style": "Transition style:",
    "settings.animation_style.slide": "Slide",
    "settings.animation_style.fade": "Fade",
    "settings.animation_speed": "Animation speed:",
    "settings.animation_speed.fast": "Fast",
    "settings.animation_speed.normal": "Normal",
    "settings.animation_speed.smooth": "Smooth",
    "settings.animations_hint": "Page transitions, card appearance and dialogs.",
    "settings.games_dir": "Games folder:",
    "settings.temp_info": "Folder: {path}\nUsed: {size}",
    "settings.open_folder": "Open folder",
    "settings.browse": "Choose folder…",
    "settings.clear_now": "Clear now",
    "settings.auto_cleanup": "Automatically clean temp files",
    "settings.show_ext": "Show file extensions",
    "settings.start_collapsed": "Start with collapsed sidebar",
    "settings.auto_steam": "Automatically add installed Steam games",
    "settings.steam_path": "Steam folder:",
    "settings.steam_missing": "Steam was not detected automatically",
    "settings.check_updates": "Check for updates automatically",
    "settings.check_now": "Check now",
    "settings.covers_info": "Cached covers: {count}  •  {size}",
    "settings.clear_covers": "Clear cache",
    "settings.covers_cleared": "Image cache cleared.",
    "settings.language": "Language:",
    "settings.save": "Save",
    "settings.cancel": "Cancel",
    "settings.reset": "Reset",
    "settings.reset.confirm": "Reset all settings?",
    "settings.temp_missing": "Folder does not exist.",
    "settings.temp_clear.confirm": "Delete all files?\nUsed: {size}",
    "settings.temp_clear.done": "Temporary files removed.",
    "settings.temp_clear.error": "Error: {error}",

    "about.title": "About",
    "about.version": f"VERSION {VERSION}",
    "about.description": "Light game launcher for .dvp, .zip and .exe games.\n\nDeveloped by Made by One Studio.\nPacks, extracts and runs games, imports your Steam library\nand keeps everything local on your disk.",
    "about.close": "Close",
    "about.check_updates": "Check for updates",

    "steam.title": "Import from Steam",
    "steam.subtitle": "Installed Steam games",
    "steam.selection_hint": "Check the games that should be in the launcher",
    "steam.apply_selection": "Apply selection ({count})",
    "steam.selection_applied": "Steam library updated: +{added}, −{removed}",
    "steam.search_placeholder": "Search Steam games...",
    "steam.select_all": "Select all",
    "steam.select_none": "Clear",
    "steam.add_selected": "Add selected ({count})",
    "steam.not_found": "Steam installation was not found.\nSet the Steam folder in Settings.",
    "steam.empty": "No installed Steam games found.",
    "steam.already_added": "in library",
    "steam.scanning": "Scanning Steam library...",
    "steam.added": "Games added from Steam: {count}",
    "steam.found": "Found installed games: {count}",
    "steam.path": "Steam folder: {path}",

    "update.title": "Update available",
    "update.found": "Devers Launcher {version} is available.\nYou have version {current}.",
    "update.notes": "What's new:",
    "update.download": "Download & install",
    "update.downloading": "Downloading update... {percent}%",
    "update.download_error": "Update download failed:\n{error}",
    "update.page": "Release page",
    "update.later": "Later",
    "update.ready": "The update is downloaded. The launcher will close and restart to finish installing.",
    "update.apply_error": "Could not start the installer:\n{error}",
    "update.up_to_date": "You have the latest version ({version}).",
    "update.check_failed": "Could not check for updates:\n{error}",
    "update.checking": "Checking for updates...",
    "update.check_title": "Checking for updates",
    "update.checking_hint": "Looking for a new version on GitHub...",
    "update.check_hint": "Check your internet connection or open the release page.",
    "update.up_to_date_title": "You're up to date",
    "update.current_version": "Installed version: {version}",
    "update.retry": "Check again",
    "update.close": "Close",
    "update.error_title": "Update check failed",
    "update.asset": "{name}  •  {size}",
    "update.source_hint": "Running from source: the update will be saved to the updates folder.",
    "update.chip": "Update {version} — download",
    "update.source_mode": "This build runs from source, so it cannot replace itself.\nThe update was saved to:\n{path}",
    "update.no_asset": "This release has no downloadable build for your system.",
    "update.tray_title": "Update available",
    "update.tray_msg": "Devers Launcher {version} is available",

    "tray.show": "Show",
    "tray.quit": "Quit",
    "tray.check_updates": "Check for updates",
    "tray.settings": "Settings",
    "tray.minimized_title": "Devers Launcher",
    "tray.minimized_msg": "Minimized to tray",

    "bottom.temp": "Temp files: {size}",
    "bottom.stats": "{games} games  •  {steam} from Steam",
    "bottom.version": f"Devers Launcher v{VERSION}",
}


def ensure_default_localization():
    """Создаёт data/localization/en.json, если его нет."""
    en_path = LOCALIZATION_DIR / "en.json"
    if not en_path.exists():
        try:
            with open(en_path, "w", encoding="utf-8") as f:
                json.dump(EN_DEFAULT, f, indent=4, ensure_ascii=False)
            log.info(f"Создан {en_path}")
        except Exception as e:
            log.error(f"Не удалось создать en.json: {e}")


class LocalizationManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.current_lang = "en"
        self.strings = {}
        self.fallback = {}
        self.available = {}
        self.load_available()

    def load_available(self):
        self.available = {}
        if not LOCALIZATION_DIR.exists():
            return
        for f in LOCALIZATION_DIR.iterdir():
            if f.suffix != ".json":
                continue
            code = f.stem
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                name = data.get("_name", code.upper())
                self.available[code] = name
            except Exception as e:
                log.warning(f"Не удалось прочитать {f}: {e}")

        if "en" not in self.available:
            self.available["en"] = "English"

    def set_language(self, code):
        if code not in self.available:
            code = "en"
        self.current_lang = code

        en_path = LOCALIZATION_DIR / "en.json"
        try:
            with open(en_path, "r", encoding="utf-8") as f:
                self.fallback = json.load(f)
        except Exception:
            self.fallback = EN_DEFAULT.copy()

        if code == "en":
            self.strings = self.fallback
        else:
            path = LOCALIZATION_DIR / f"{code}.json"
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.strings = json.load(f)
            except Exception as e:
                log.warning(f"Не удалось загрузить {path}: {e}")
                self.strings = {}

        log.info(f"Язык установлен: {code} ({self.available.get(code, code)})")

    def t(self, key, **kwargs):
        if key == "app.subtitle":
            return f"VERSION {VERSION}"
        if key == "about.version":
            return f"VERSION {VERSION}"
        if key == "bottom.version":
            return f"Devers Launcher v{VERSION}"

        value = self.strings.get(key)
        if value is None:
            value = self.fallback.get(key)
        if value is None:
            value = key
        if kwargs:
            try:
                value = value.format(**kwargs)
            except Exception:
                pass
        return value



L = LocalizationManager()

def build_app_icon():
    if APP_ICON.exists():
        icon = QIcon(str(APP_ICON))
        if not icon.isNull():
            log.info(f"Иконка приложения: {APP_ICON}")
            return icon

    logo_png = ICON_DIR / "logo.png"
    if logo_png.exists():
        icon = QIcon(str(logo_png))
        if not icon.isNull():
            log.info(f"Иконка приложения: {logo_png}")
            return icon

    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI Symbol", int(size * 0.72), QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "✦")
        painter.end()
        icon.addPixmap(pm)
    log.info("Иконка приложения: программная ✦")
    return icon


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return {**default, **json.load(f)} if isinstance(default, dict) else json.load(f)
        except Exception as e:
            log.warning(f"Не удалось прочитать {path}: {e}")
            return default.copy() if isinstance(default, dict) else default
    return default.copy() if isinstance(default, dict) else default


def save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        log.error(f"Не удалось сохранить {path}: {e}")


ANIMATION_SPEEDS = {"fast": 0.65, "normal": 1.0, "smooth": 1.5}
ANIMATION_STYLES = ("slide", "fade")


class AnimationManager:
    """Central switch for interface animations (enable / speed / style)."""

    def __init__(self):
        self.enabled_animations = True
        self.speed = "normal"
        self.style = "slide"

    def configure(self, config):
        self.enabled_animations = bool(config.get("animations", True))
        speed = str(config.get("animation_speed", "normal"))
        self.speed = speed if speed in ANIMATION_SPEEDS else "normal"
        style = str(config.get("animation_style", "slide"))
        self.style = style if style in ANIMATION_STYLES else "slide"

    def enabled(self) -> bool:
        return self.enabled_animations

    def duration(self, base_ms: int) -> int:
        if not self.enabled_animations:
            return 0
        return max(60, int(base_ms * ANIMATION_SPEEDS.get(self.speed, 1.0)))


ANIM = AnimationManager()


def fade_in_widget(widget, base_duration=200, delay=0, start=0.0):
    """Smoothly fades a widget in by animating its opacity effect."""
    if widget is None or not ANIM.enabled():
        return None
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(start)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(ANIM.duration(base_duration))
    anim.setStartValue(start)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def cleanup():
        try:
            if widget.graphicsEffect() is effect:
                widget.setGraphicsEffect(None)
        except Exception:
            pass

    anim.finished.connect(cleanup)
    widget._fade_animation = anim
    if delay > 0:
        QTimer.singleShot(delay, anim.start)
    else:
        anim.start()
    return anim


def human_size(bytes_val):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


def human_time(seconds):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h}h {m}m"
    elif m > 0:
        return f"{m}m"
    else:
        return f"{seconds}s"


def dir_size(path):
    total = 0
    if not os.path.exists(path):
        return 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except:
                pass
    return total


def invert_pixmap(pixmap):
    if pixmap.isNull():
        return pixmap
    img = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() > 0:
                c.setRed(255 - c.red())
                c.setGreen(255 - c.green())
                c.setBlue(255 - c.blue())
                img.setPixelColor(x, y, c)
    return QPixmap.fromImage(img)


def tint_pixmap(pixmap, color):
    if pixmap.isNull():
        return pixmap
    img = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() > 0:
                c.setRed(color.red())
                c.setGreen(color.green())
                c.setBlue(color.blue())
                img.setPixelColor(x, y, c)
    return QPixmap.fromImage(img)


def get_icon(name, size=22):
    path = ICON_DIR / f"{name}.png"
    if not path.exists():
        return None
    base = QPixmap(str(path))
    if base.isNull():
        return None
    base = base.scaled(size, size,
                       Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
    inverted = invert_pixmap(base)
    icon = QIcon()
    icon.addPixmap(base, QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(inverted, QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(inverted, QIcon.Mode.Selected, QIcon.State.Off)
    icon.addPixmap(base, QIcon.Mode.Selected, QIcon.State.On)
    return icon


def get_icon_tinted(name, size, color):
    path = ICON_DIR / f"{name}.png"
    if not path.exists():
        return None
    base = QPixmap(str(path))
    if base.isNull():
        return None
    base = base.scaled(size, size,
                       Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
    tinted = tint_pixmap(base, color)
    icon = QIcon()
    icon.addPixmap(tinted, QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(tinted, QIcon.Mode.Normal, QIcon.State.On)
    return icon


# ---------------------------------------------------------------------------
#  IMAGE CACHE
#  Covers are cached on disk (data/save/cache/covers) and in memory, so they
#  are decoded/downloaded only once and survive launcher restarts.
# ---------------------------------------------------------------------------

COVER_MEMORY_LIMIT = 120
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
        while len(_cover_memory) > COVER_MEMORY_LIMIT:
            _cover_memory.popitem(last=False)


def load_cover_image(path: str = "", url: str = "", data: bytes = b"") -> QImage:
    """Loads a cover from memory cache, disk, URL or raw bytes (thread-safe)."""
    key = path or url or (_cover_hash(data) if data else "")
    if not key:
        return QImage()

    with _cover_memory_lock:
        if key in _cover_memory:
            _cover_memory.move_to_end(key)
            return _cover_memory[key]
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
                key = url
            if local and os.path.exists(local):
                image = QImage(local)
    except Exception as e:
        log.warning(f"Обложка не загрузилась ({key}): {e}")

    if not image.isNull():
        if max(image.width(), image.height()) > COVER_MEMORY_MAX_SIDE:
            image = image.scaled(
                COVER_MEMORY_MAX_SIDE, COVER_MEMORY_MAX_SIDE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        _remember_cover(key, image)
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


# ---------------------------------------------------------------------------
#  GAME FILE HELPERS
# ---------------------------------------------------------------------------

EXE_BLACKLIST = (
    "unins", "uninstall", "vcredist", "vc_redist", "dxsetup", "dxwebsetup",
    "setup", "installer", "crash", "report", "unitycrashhandler",
    "notification_helper", "touchup", "activate",
)


def prettify_name(stem: str) -> str:
    name = re.sub(r"[._]+", " ", stem)
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name or stem


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


# ---------------------------------------------------------------------------
#  STEAM LIBRARY
# ---------------------------------------------------------------------------

STEAM_TOOL_NAMES = (
    "steamworks common redistributables",
    "steam linux runtime",
    "steamvr",
    "proton",
    "steam audio",
)


def find_steam_path(configured: str = ""):
    candidates = []
    if configured:
        candidates.append(os.path.expandvars(configured))

    if os.name == "nt":
        try:
            import winreg
            for root, sub in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            ):
                try:
                    with winreg.OpenKey(root, sub) as key:
                        for value in ("SteamPath", "InstallPath"):
                            try:
                                val, _ = winreg.QueryValueEx(key, value)
                                if val:
                                    candidates.append(val)
                            except OSError:
                                pass
                except OSError:
                    pass
        except ImportError:
            pass
        for env in ("ProgramFiles(x86)", "ProgramFiles"):
            base = os.environ.get(env)
            if base:
                candidates.append(os.path.join(base, "Steam"))
    elif sys.platform == "darwin":
        candidates.append(os.path.expanduser("~/Library/Application Support/Steam"))
    else:
        candidates.extend(os.path.expanduser(p) for p in (
            "~/.steam/steam", "~/.local/share/Steam",
            "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
        ))

    for candidate in candidates:
        try:
            p = Path(candidate)
            if p.is_dir():
                return p
        except OSError:
            continue
    return None


def steam_library_folders(steam_path: Path) -> list:
    folders = [steam_path]
    vdf = steam_path / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        try:
            text = vdf.read_text(encoding="utf-8", errors="ignore")
            for raw in re.findall(r'"path"\s+"([^"]+)"', text, flags=re.I):
                path = Path(raw.replace("\\\\", "\\"))
                if path.is_dir() and path not in folders:
                    folders.append(path)
        except Exception as e:
            log.warning(f"Не удалось прочитать libraryfolders.vdf: {e}")
    return folders


def _parse_steam_acf(path: Path) -> dict:
    data = {}
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return data
    for m in re.finditer(r'"([^"]+)"\s+"([^"]*)"', text):
        data[m.group(1)] = m.group(2)
    return data


def scan_steam_games(steam_path):
    """Returns a list of installed Steam games found in all library folders."""
    if not steam_path:
        return []
    games = []
    seen = set()
    appcache = steam_path / "appcache" / "librarycache"

    for library in steam_library_folders(steam_path):
        steamapps = library / "steamapps"
        if not steamapps.is_dir():
            continue
        try:
            manifests = sorted(steamapps.glob("appmanifest_*.acf"))
        except OSError:
            continue

        for acf in manifests:
            info = _parse_steam_acf(acf)
            appid = info.get("appid") or re.sub(r"\D", "", acf.stem)
            if not appid or appid in seen:
                continue
            name = info.get("name", "").strip()
            if not name or any(tool in name.lower() for tool in STEAM_TOOL_NAMES):
                continue
            installdir = info.get("installdir", "").strip()
            game_path = steamapps / "common" / installdir if installdir else Path("")
            if installdir and not game_path.is_dir():
                continue
            try:
                size = int(info.get("SizeOnDisk", "0") or 0)
            except ValueError:
                size = 0

            cover_local = ""
            cache_dirs = (appcache, library / "appcache" / "librarycache")
            for cache_root in cache_dirs:
                for candidate in (
                    cache_root / f"{appid}_header.jpg",
                    cache_root / f"{appid}_library_600x900.jpg",
                    cache_root / appid / "library_600x900.jpg",
                    cache_root / appid / "library_hero.jpg",
                    cache_root / appid / "header.jpg",
                ):
                    if candidate.exists():
                        cover_local = str(candidate)
                        break
                if cover_local:
                    break

            if not cover_local:
                for cache_root in cache_dirs:
                    cache_dir = cache_root / appid
                    if not cache_dir.is_dir():
                        continue
                    images = []
                    try:
                        for item in cache_dir.iterdir():
                            if item.is_file() and item.suffix.lower() in (".jpg", ".jpeg", ".png"):
                                try:
                                    images.append((item.stat().st_size, item))
                                except OSError:
                                    pass
                    except OSError:
                        pass
                    if images:
                        images.sort(reverse=True)
                        cover_local = str(images[0][1])
                        break

            seen.add(appid)
            games.append({
                "key": f"steam:{appid}",
                "appid": appid,
                "name": name,
                "path": str(game_path) if installdir else "",
                "size": size,
                "cover_path": cover_local,
                "cover_url": STEAM_CDN_HEADER.format(appid=appid),
                "library": str(library),
            })

    games.sort(key=lambda g: g["name"].lower())
    return games


def launch_steam_game(appid: str) -> None:
    url = f"steam://rungameid/{appid}"
    if os.name == "nt":
        os.startfile(url)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", url])
    else:
        subprocess.Popen(["xdg-open", url])


def snapshot_pids():
    """Return {pid: lowercased_name} of currently running processes (best-effort).

    Used to track play-time for games launched without a Popen handle
    (Steam / shortcuts), where we cannot poll a single process directly.
    Returns an empty dict on any failure.
    """
    procs = {}
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            for line in out.stdout.splitlines():
                parts = line.split(",")
                if len(parts) >= 2:
                    name = parts[0].strip('"').lower()
                    pid = parts[1].strip('"')
                    if pid.isdigit():
                        procs[int(pid)] = name
        else:
            out = subprocess.run(["ps", "-A", "-o", "pid=,comm="],
                                 capture_output=True, text=True)
            for line in out.stdout.splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2 and parts[0].strip().isdigit():
                    procs[int(parts[0])] = parts[1].strip().lower()
    except Exception:
        return {}
    return procs


# Processes that are not the game itself; they appear whenever Steam (or the
# OS) reacts to a launch and must not keep a play session "alive".
_LAUNCH_NOISE = (
    "steam", "webhelper", "conhost", "cmd.exe", "explorer.exe",
    "searchindexer", "runtimebroker", "svchost", "dwm.exe", "taskhost",
)


# ---------------------------------------------------------------------------
#  UPDATES (GitHub releases)
# ---------------------------------------------------------------------------

def parse_version(value: str) -> tuple:
    numbers = re.findall(r"\d+", str(value or ""))
    return tuple(int(n) for n in numbers[:4]) if numbers else (0,)


def is_newer_version(remote: str, current: str) -> bool:
    def normalized(v):
        parts = list(parse_version(v))
        while len(parts) < 4:
            parts.append(0)
        return tuple(parts)
    return normalized(remote) > normalized(current)


def fetch_latest_release() -> dict:
    req = urllib.request.Request(
        GITHUB_RELEASES_API,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Unexpected GitHub response")
    return data


def pick_update_asset(assets):
    """Picks the best release asset for the current platform."""
    if not assets:
        return None
    if os.name == "nt":
        preferred = (".zip", ".exe", ".msi")
    elif sys.platform == "darwin":
        preferred = (".dmg", ".zip")
    else:
        preferred = (".appimage", ".tar.gz", ".zip")

    best = None
    for asset in assets:
        name = str(asset.get("name", "")).lower()
        for rank, ext in enumerate(preferred):
            if name.endswith(ext):
                score = (len(preferred) - rank) * 10
                if os.name == "nt" and "windows" in name:
                    score += 5
                if best is None or score > best[0]:
                    best = (score, asset)
                break
    return best[1] if best else None


class RoundedCoverLabel(QLabel):
    def __init__(self, radius_top=12, parent=None):
        super().__init__(parent)
        self._radius = radius_top
        self._source_pixmap = None

    def set_rounded_pixmap(self, pixmap):
        self._source_pixmap = pixmap
        self._repaint()

    def clear_rounded(self):
        self._source_pixmap = None
        self.clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._repaint()

    def _repaint(self):
        if self._source_pixmap is None or self._source_pixmap.isNull():
            return
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return
        scaled = self._source_pixmap.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        if scaled.width() > w or scaled.height() > h:
            x = (scaled.width() - w) // 2
            y = (scaled.height() - h) // 2
            scaled = scaled.copy(x, y, w, h)

        result = QPixmap(w, h)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        r = self._radius
        path = QPainterPath()
        path.moveTo(0, r)
        path.arcTo(0, 0, 2 * r, 2 * r, 180, -90)
        path.lineTo(w - r, 0)
        path.arcTo(w - 2 * r, 0, 2 * r, 2 * r, 90, -90)
        path.lineTo(w, h)
        path.lineTo(0, h)
        path.closeSubpath()

        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        super().setPixmap(result)


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
            with zipfile.ZipFile(self.dvp_path, 'r') as zf:
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
            elif game_type == "exe":
                entry["exe"] = p
            elif game_type == "script":
                entry["exe"] = p

            manifests[f] = entry

        for key, ext_entry in self.external.items():
            try:
                manifests[key] = self._external_entry(key, ext_entry)
            except Exception as e:
                log.warning(f"Пропущена внешняя игра {key}: {e}")

        self.finished.emit(manifests)

    def _external_entry(self, key: str, ext_entry: dict) -> dict:
        game_type = ext_entry.get("type", "exe")
        path = str(ext_entry.get("path", ""))
        entry = {
            "mtime": ext_entry.get("added", 0),
            "size": ext_entry.get("size", 0),
            "path": path,
            "type": game_type,
            "name": ext_entry.get("name", key),
            "exe": str(ext_entry.get("exe", "")),
            "created": "",
            "cover_path": str(ext_entry.get("cover_path", "")),
            "cover_url": str(ext_entry.get("cover_url", "")),
            "external": True,
            "error": None,
        }
        if game_type == "steam":
            entry["appid"] = ext_entry.get("appid", key.split(":")[-1])
            if entry["cover_path"] and not os.path.exists(entry["cover_path"]):
                entry["cover_path"] = ""
            if path and not os.path.isdir(path):
                entry["error"] = "Not installed"
        elif game_type == "folder":
            if not os.path.isdir(path):
                entry["error"] = "Folder not found"
            else:
                try:
                    entry["mtime"] = os.path.getmtime(path)
                except OSError:
                    pass
                if not entry["exe"] or not os.path.exists(entry["exe"]):
                    entry["exe"] = detect_executable(path)
        else:
            if not os.path.exists(path):
                entry["error"] = "File not found"
            else:
                try:
                    entry["mtime"] = os.path.getmtime(path)
                    entry["size"] = os.path.getsize(path)
                except OSError:
                    pass
                if not entry["exe"]:
                    entry["exe"] = path
        return entry


class CoverLoader(QRunnable):
    class Signals(QObject):
        loaded = pyqtSignal(str, QImage)

    def __init__(self, key, path="", url="", data=None):
        super().__init__()
        self.key = key
        self.path = path
        self.url = url
        self.data = data or b""
        self.signals = CoverLoader.Signals()

    def run(self):
        try:
            image = load_cover_image(self.path, self.url, self.data)
        except Exception as e:
            log.warning(f"Обложка не загрузилась: {e}")
            image = QImage()
        self.signals.loaded.emit(self.key, image)


CARD_WIDTH = 240
CARD_HEIGHT = 256
COVER_HEIGHT = 172

BADGE_LABELS = {
    "steam": "STEAM",
    "exe": "EXE",
    "zip": "ZIP",
    "dvp": "DVP",
    "folder": "FOLDER",
    "shortcut": "LINK",
    "script": "BAT",
}


def badge_style(kind: str) -> str:
    if kind == "steam":
        return ("background-color: rgba(18, 34, 58, 215); color: #8EC2FF; "
                "border: 1px solid rgba(120, 175, 255, 110);")
    return ("background-color: rgba(10, 10, 10, 205); color: #E6E6E6; "
            "border: 1px solid rgba(255, 255, 255, 45);")


class GameCard(QFrame):
    play_requested = pyqtSignal(str)
    context_menu_requested = pyqtSignal(str, QPoint)
    favorite_toggled = pyqtSignal(str)

    def __init__(self, key, meta, is_favorite=False, show_ext=False, play_time=0,
                 launch_count=0, width=CARD_WIDTH):
        super().__init__()
        self.key = key
        self.meta = meta
        self._play_time = play_time
        self._launch_count = launch_count
        self._card_width = max(180, int(width))
        self.setObjectName("GameCard")
        self.setFixedSize(self._card_width, CARD_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.cover = RoundedCoverLabel(radius_top=12)
        self.cover.setFixedHeight(COVER_HEIGHT)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setStyleSheet(
            "background-color: #141414; "
            "color: #444444; font-size: 10px;"
        )
        self.cover.setText(L.t("card.no_cover"))

        if meta.get("error"):
            self.cover.setText(L.t("card.error"))
            self.cover.setStyleSheet(
                "background-color: #1A1010; "
                "color: #FF6B6B; font-size: 11px;"
            )
        elif meta.get("cover_path") or meta.get("cover_url") or meta.get("cover_data"):
            QThreadPool.globalInstance().start(self._make_cover_loader(meta))

        self.badge = QLabel(self.cover)
        self.badge.setText(BADGE_LABELS.get(str(meta.get("type", "")), ""))
        self.badge.setStyleSheet(
            f"{badge_style(str(meta.get('type', '')))}"
            "border-radius: 7px; padding: 3px 8px; font-size: 9px; font-weight: bold;"
            "letter-spacing: 1px;"
        )
        self.badge.setVisible(bool(self.badge.text()))
        self.badge.adjustSize()
        self.badge.move(10, 10)
        if self.badge.isVisible():
            self.badge.raise_()

        self.play_overlay = QPushButton(self.cover)
        self.play_overlay.setFixedSize(56, 56)
        self.play_overlay.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_overlay.setToolTip(L.t("menu.play"))
        self.play_overlay.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 175);
                border: 1px solid rgba(255, 255, 255, 70);
                border-radius: 28px;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 235); }
        """)
        overlay_icon = get_icon("play", 22)
        if overlay_icon:
            self.play_overlay.setIcon(overlay_icon)
            self.play_overlay.setIconSize(QSize(22, 22))
        else:
            self.play_overlay.setText("▶")
        self.play_overlay.clicked.connect(lambda: self.play_requested.emit(self.key))
        self._overlay_effect = QGraphicsOpacityEffect(self.play_overlay)
        self._overlay_effect.setOpacity(0.0)
        self.play_overlay.setGraphicsEffect(self._overlay_effect)
        self.play_overlay.setVisible(False)
        self._overlay_anim = QPropertyAnimation(self._overlay_effect, b"opacity", self)
        self._overlay_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        outer.addWidget(self.cover)

        info_wrap = QWidget()
        info_wrap.setStyleSheet(
            "background-color: #0D0D0D; "
            "border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;"
        )
        info = QVBoxLayout(info_wrap)
        info.setContentsMargins(14, 9, 14, 10)
        info.setSpacing(5)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        display_name = meta.get("name", "Unknown")
        if show_ext and meta.get("type") not in ("steam", "folder"):
            suffix = os.path.splitext(meta.get("path", ""))[1]
            if suffix:
                display_name = f"{display_name}{suffix}"
        self._full_name = display_name
        self.name_label = QLabel(self._elided_name(display_name))
        self.name_label.setToolTip(display_name)
        self.name_label.setStyleSheet(
            "color: #FFFFFF; font-size: 13px; font-weight: bold; "
            "letter-spacing: -0.3px; background: transparent;"
        )
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        top_row.addWidget(self.name_label)

        self.fav_btn = QPushButton()
        self.fav_btn.setFixedSize(26, 26)
        self.fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fav_btn.setToolTip(L.t("card.favorite") if not is_favorite else L.t("card.unfavorite"))
        self._setup_fav_button(is_favorite)
        self.fav_btn.clicked.connect(lambda: self.favorite_toggled.emit(self.key))
        top_row.addWidget(self.fav_btn)

        info.addStretch(1)
        info.addLayout(top_row)

        self.stats_label = QLabel(self._stats_text())
        self.stats_label.setStyleSheet("color: #666666; font-size: 10px; background: transparent;")
        info.addWidget(self.stats_label)
        info.addStretch(1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        self.progress.setFixedHeight(14)
        self._progress_anim = QPropertyAnimation(self.progress, b"value", self)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #1A1A1A; border: none;
                border-radius: 7px; text-align: center; color: transparent;
            }
            QProgressBar::chunk { background-color: #FFFFFF; border-radius: 7px; }
        """)
        info.addWidget(self.progress)

        outer.addWidget(info_wrap)

    def _setup_fav_button(self, is_favorite):
        icon_name = "star_filled" if is_favorite else "star"
        color = QColor(255, 209, 102) if is_favorite else QColor(120, 120, 120)
        icon = get_icon_tinted(icon_name, 18, color)
        if icon:
            self.fav_btn.setIcon(icon)
            self.fav_btn.setIconSize(QSize(18, 18))
            self.fav_btn.setText("")
            self.fav_btn.setStyleSheet("""
                QPushButton { background-color: transparent; border: none; }
                QPushButton:hover { background-color: #1A1A1A; border-radius: 6px; }
            """)
        else:
            self.fav_btn.setText("★" if is_favorite else "☆")
            self.fav_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {'#FFD166' if is_favorite else '#666666'};
                    border: none; font-size: 16px;
                }}
                QPushButton:hover {{ color: #FFD166; }}
            """)

    def _make_cover_loader(self, meta):
        data = None
        if meta.get("cover_data"):
            try:
                data = bytes.fromhex(meta["cover_data"])
            except Exception:
                data = None
        loader = CoverLoader(self.key, meta.get("cover_path", ""),
                             meta.get("cover_url", ""), data)
        loader.signals.loaded.connect(self._on_cover_loaded)
        return loader

    def _stats_text(self) -> str:
        parts = [human_size(self.meta.get("size", 0))]
        parts.append(human_time(self._play_time) if self._play_time else L.t("library.not_played"))
        if self._launch_count:
            parts.append(f"×{self._launch_count}")
        return "  •  ".join(parts)

    def update_stats(self, play_time=None, launch_count=None):
        """Refresh the stats line in place (cheap; avoids a full re-render)."""
        if play_time is not None:
            self._play_time = play_time
        if launch_count is not None:
            self._launch_count = launch_count
        self.stats_label.setText(self._stats_text())

    def set_card_width(self, width):
        """Resize a card in place when the grid columns change."""
        width = max(180, int(width))
        if width == self._card_width:
            return
        self._card_width = width
        self.setFixedWidth(width)
        self.name_label.setText(self._elided_name(self._full_name))
        self._center_overlay()

    def _elided_name(self, text: str) -> str:
        try:
            fm = QFontMetrics(self.font())
        except Exception:
            return text
        return fm.elidedText(text, Qt.TextElideMode.ElideRight, self._card_width - 100)

    def _on_cover_loaded(self, key, image):
        if key != self.key or image.isNull():
            return
        self.cover.set_rounded_pixmap(QPixmap.fromImage(image))
        self.cover.setText("")

    def set_progress_value(self, value):
        """Smoothly animates the extraction progress bar."""
        if not ANIM.enabled():
            self.progress.setValue(value)
            return
        self._progress_anim.stop()
        self._progress_anim.setDuration(ANIM.duration(260))
        self._progress_anim.setStartValue(self.progress.value())
        self._progress_anim.setEndValue(value)
        self._progress_anim.start()

    def _set_overlay_visible(self, visible):
        if not ANIM.enabled():
            self._overlay_effect.setOpacity(1.0 if visible else 0.0)
            self.play_overlay.setVisible(visible)
            return
        self._overlay_anim.stop()
        if visible:
            self.play_overlay.setVisible(True)
            self.play_overlay.raise_()
            self._overlay_anim.setDuration(ANIM.duration(160))
            self._overlay_anim.setStartValue(self._overlay_effect.opacity())
            self._overlay_anim.setEndValue(1.0)
        else:
            self._overlay_anim.setDuration(ANIM.duration(140))
            self._overlay_anim.setStartValue(self._overlay_effect.opacity())
            self._overlay_anim.setEndValue(0.0)
            self._overlay_anim.finished.connect(self._hide_overlay_if_faded)
        self._overlay_anim.start()

    def _hide_overlay_if_faded(self):
        try:
            self._overlay_anim.finished.disconnect(self._hide_overlay_if_faded)
        except Exception:
            pass
        if self._overlay_effect.opacity() < 0.05:
            self.play_overlay.setVisible(False)

    def _center_overlay(self):
        self.play_overlay.move(
            (self.cover.width() - self.play_overlay.width()) // 2,
            (self.cover.height() - self.play_overlay.height()) // 2,
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "play_overlay"):
            self._center_overlay()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._center_overlay()
        self._set_overlay_visible(True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._set_overlay_visible(False)

    def _on_context(self, pos):
        self.context_menu_requested.emit(self.key, self.mapToGlobal(pos))

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.play_requested.emit(self.key)


class CollapsibleSidebar(QFrame):
    page_changed = pyqtSignal(str)

    EXPANDED = 230
    COLLAPSED = 68

    def __init__(self):
        super().__init__()
        self.setObjectName("Sidebar")
        self.is_collapsed = False
        self.setMinimumWidth(self.EXPANDED)
        self.setMaximumWidth(self.EXPANDED)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(15, 20, 15, 20)
        self.root.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(0)

        self.symbol_btn = QPushButton("✦")
        self.symbol_btn.setObjectName("SymbolBtn")
        self.symbol_btn.setFixedSize(36, 36)
        self.symbol_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.symbol_btn.setToolTip(L.t("sidebar.collapse"))

        logo_icon = get_icon("logo", 22)
        if logo_icon:
            self.symbol_btn.setIcon(logo_icon)
            self.symbol_btn.setIconSize(QSize(22, 22))
            self.symbol_btn.setText("")
            self.symbol_btn.setStyleSheet("""
                QPushButton { background-color: transparent; border: none; }
                QPushButton:hover { background-color: #151515; border-radius: 8px; }
            """)
        else:
            self.symbol_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent; color: #FFFFFF;
                    border: none; font-size: 20px; font-weight: 900;
                }
                QPushButton:hover { background-color: #151515; border-radius: 8px; }
            """)

        self.symbol_btn.clicked.connect(self.toggle)
        header.addWidget(self.symbol_btn)

        self.logo = QLabel("Devers")
        self.logo.setObjectName("Logo")
        self.logo.setFixedHeight(36)
        header.addWidget(self.logo)
        header.addStretch()

        self.root.addLayout(header)
        self.root.addSpacing(30)

        self.nav_buttons = {}
        self.btn_home = self._make_nav("home", "🏠", L.t("sidebar.home"), "home")
        self.btn_library = self._make_nav("library", "📚", L.t("sidebar.library"), "library")
        self.btn_fav = self._make_nav("star", "★", L.t("sidebar.favorites"), "favorites")
        self.btn_home.setChecked(True)
        self._render(self.btn_home, self.is_collapsed)

        self.root.addWidget(self.btn_home)
        self.root.addWidget(self.btn_library)
        self.root.addWidget(self.btn_fav)
        self.root.addStretch()

        self.btn_about = self._make_nav("info", "ℹ", L.t("sidebar.about"), "about", is_toggle=False)
        self.btn_settings = self._make_nav("settings", "⚙", L.t("sidebar.settings"), "settings", is_toggle=False)
        self.root.addWidget(self.btn_about)
        self.root.addWidget(self.btn_settings)

    def _make_nav(self, icon_name, emoji, text, key, is_toggle=True):
        btn = QPushButton()
        btn.setObjectName("NavButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(text)
        btn.setFixedHeight(46)
        btn.setProperty("nav_icon_name", icon_name)
        btn.setProperty("nav_emoji", emoji)
        btn.setProperty("nav_text", text)
        self._render(btn, self.is_collapsed)
        if is_toggle:
            btn.setCheckable(True)
            btn.clicked.connect(lambda: self.switch(key))
        self.nav_buttons[key] = btn
        return btn

    def _render(self, btn, collapsed):
        icon_name = btn.property("nav_icon_name")
        emoji = btn.property("nav_emoji")
        text = btn.property("nav_text")
        active = btn.isChecked()

        if collapsed:
            icon = get_icon(icon_name, 24)
            if icon:
                btn.setIcon(icon)
                btn.setIconSize(QSize(24, 24))
                btn.setText("")
            else:
                btn.setIcon(QIcon())
                btn.setText(emoji)
            btn.setStyleSheet(self._style(True, active))
        else:
            icon = get_icon(icon_name, 18)
            if icon:
                btn.setIcon(icon)
                btn.setIconSize(QSize(18, 18))
                btn.setText(f"   {text}")
            else:
                btn.setIcon(QIcon())
                btn.setText(f"  {emoji}   {text}")
            btn.setStyleSheet(self._style(False, active))

    def _style(self, collapsed, active):
        padding = "0" if collapsed else "0 16px"
        align = "center" if collapsed else "left"
        bg = "#FFFFFF" if active else "transparent"
        fg = "#000000" if active else "#999999"
        weight = "bold" if active else "500"
        fs = "16px" if collapsed else "13px"
        return f"""
            QPushButton {{
                background-color: {bg}; color: {fg};
                border: none; border-radius: 10px;
                padding: {padding}; font-size: {fs};
                font-weight: {weight}; text-align: {align};
            }}
            QPushButton:hover {{
                background-color: {'#FFFFFF' if active else '#151515'};
                color: {'#000000' if active else '#FFFFFF'};
            }}
        """

    def switch(self, key):
        for k, btn in self.nav_buttons.items():
            if k in ("settings", "about"):
                continue
            btn.setChecked(k == key)
            self._render(btn, self.is_collapsed)
        self.page_changed.emit(key)

    def toggle(self):
        self.is_collapsed = not self.is_collapsed
        target = self.COLLAPSED if self.is_collapsed else self.EXPANDED
        duration = ANIM.duration(260)

        if duration <= 0:
            self.setMinimumWidth(target)
            self.setMaximumWidth(target)
        else:
            a1 = QPropertyAnimation(self, b"minimumWidth")
            a1.setDuration(duration); a1.setStartValue(self.width()); a1.setEndValue(target)
            a1.setEasingCurve(QEasingCurve.Type.InOutCubic)
            a2 = QPropertyAnimation(self, b"maximumWidth")
            a2.setDuration(duration); a2.setStartValue(self.width()); a2.setEndValue(target)
            a2.setEasingCurve(QEasingCurve.Type.InOutCubic)

            g = QParallelAnimationGroup()
            g.addAnimation(a1); g.addAnimation(a2)
            g.start()
            self._anim_group = g

        self.logo.setVisible(not self.is_collapsed)
        for k, btn in self.nav_buttons.items():
            self._render(btn, self.is_collapsed)


class SkeletonCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("SkeletonCard")
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setStyleSheet("""
            QFrame#SkeletonCard {
                background-color: #0D0D0D;
                border: 1px solid #1A1A1A;
                border-radius: 12px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top = QFrame()
        top.setFixedHeight(COVER_HEIGHT)
        top.setStyleSheet("background-color: #141414;")
        layout.addWidget(top)

        bottom = QWidget()
        bottom.setStyleSheet(
            "background-color: #0D0D0D; "
            "border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;"
        )
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(14, 12, 14, 12)
        bl.setSpacing(8)

        line1 = QFrame(); line1.setFixedHeight(12)
        line1.setStyleSheet("background-color: #1A1A1A; border-radius: 6px; max-width: 150px;")
        line2 = QFrame(); line2.setFixedHeight(8)
        line2.setStyleSheet("background-color: #141414; border-radius: 4px; max-width: 90px;")
        bl.addWidget(line1); bl.addWidget(line2); bl.addStretch()
        layout.addWidget(bottom)


class FadeInDialog(QDialog):
    """Dialog that fades in smoothly when opened (respects animation settings)."""

    def showEvent(self, event):
        super().showEvent(event)
        fade_in_widget(self, 190)


class SettingsDialog(FadeInDialog):
    settings_applied = pyqtSignal(dict)
    check_updates_requested = pyqtSignal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config.copy()
        self.setWindowTitle(L.t("settings.title"))
        self.setWindowIcon(QApplication.windowIcon())
        self.resize(620, 820)
        self.setStyleSheet("""
            QDialog { background-color: #0A0A0A; }
            QLabel { color: #CCCCCC; font-size: 13px; }
            QLabel#SectionTitle { color: #FFFFFF; font-size: 14px; font-weight: bold; margin-top: 10px; letter-spacing: 1px; }
            QLineEdit { background-color: #1A1A1A; color: #FFFFFF; border: 1px solid #2A2A2A; border-radius: 8px; padding: 10px; font-size: 12px; }
            QLineEdit:focus { border: 1px solid #FFFFFF; }
            QComboBox { background-color: #1A1A1A; color: #FFFFFF; border: 1px solid #2A2A2A; border-radius: 8px; padding: 10px; font-size: 12px; }
            QComboBox::drop-down { border: none; }
            QCheckBox { color: #CCCCCC; font-size: 13px; spacing: 10px; }
            QCheckBox::indicator { width: 18px; height: 18px; background-color: #1A1A1A; border: 1px solid #333333; border-radius: 4px; }
            QCheckBox::indicator:checked { background-color: #FFFFFF; border: 1px solid #FFFFFF; }
            QPushButton { background-color: #FFFFFF; color: #000000; padding: 10px 22px; border-radius: 8px; font-weight: bold; font-size: 13px; }
            QPushButton:hover { background-color: #E0E0E0; }
            QPushButton#Secondary { background-color: #1A1A1A; color: #FFFFFF; border: 1px solid #333333; }
            QPushButton#Secondary:hover { background-color: #2A2A2A; }
            QPushButton#Compact { padding: 0; font-size: 15px; }
            QPushButton#Danger { background-color: #1A1A1A; color: #FF6B6B; border: 1px solid #3A1A1A; }
            QPushButton#Danger:hover { background-color: #3A1A1A; }
            QScrollArea { background: transparent; border: none; }
            QScrollArea > QWidget > QWidget { background: transparent; }
            QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
            QScrollBar::handle:vertical { background: #222222; border-radius: 4px; min-height: 40px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(35, 30, 35, 20)
        layout.setSpacing(12)
        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        title = QLabel(L.t("settings.title"))
        title.setStyleSheet("color: #FFFFFF; font-size: 26px; font-weight: 900; letter-spacing: -1px;")
        layout.addWidget(title)
        sub = QLabel(L.t("settings.subtitle"))
        sub.setStyleSheet("color: #666666; font-size: 12px;")
        layout.addWidget(sub)
        layout.addSpacing(10)

        sec1 = QLabel(L.t("settings.section.storage")); sec1.setObjectName("SectionTitle"); layout.addWidget(sec1)

        games_row = QHBoxLayout()
        self.games_input = QLineEdit(self.config.get("games_dir", str(GAMES_DIR)))
        self.games_input.setCursorPosition(0)
        b = self._browse_button(self._browse)
        games_row.addWidget(self.games_input); games_row.addWidget(b)
        row = QHBoxLayout(); lbl = QLabel(L.t("settings.games_dir")); lbl.setFixedWidth(150)
        row.addWidget(lbl); row.addLayout(games_row); layout.addLayout(row)

        layout.addSpacing(10)
        sec2 = QLabel(L.t("settings.section.temp")); sec2.setObjectName("SectionTitle"); layout.addWidget(sec2)

        self.temp_label = QLabel(""); self.temp_label.setStyleSheet("color: #888888; font-size: 12px;")
        self.temp_label.setWordWrap(True)
        layout.addWidget(self.temp_label)
        self._update_temp()

        tr = QHBoxLayout()
        o = QPushButton(L.t("settings.open_folder")); o.setObjectName("Secondary"); o.clicked.connect(self._open_temp)
        c = QPushButton(L.t("settings.clear_now")); c.setObjectName("Danger"); c.clicked.connect(self._clear_temp)
        tr.addWidget(o); tr.addWidget(c); layout.addLayout(tr)

        self.auto_cleanup = QCheckBox(L.t("settings.auto_cleanup"))
        self.auto_cleanup.setChecked(self.config.get("auto_cleanup", True))
        layout.addWidget(self.auto_cleanup)

        layout.addSpacing(10)
        sec3 = QLabel(L.t("settings.section.interface")); sec3.setObjectName("SectionTitle"); layout.addWidget(sec3)

        self.show_ext = QCheckBox(L.t("settings.show_ext"))
        self.show_ext.setChecked(self.config.get("show_extensions", False))
        layout.addWidget(self.show_ext)

        self.start_collapsed = QCheckBox(L.t("settings.start_collapsed"))
        self.start_collapsed.setChecked(self.config.get("sidebar_collapsed", False))
        layout.addWidget(self.start_collapsed)

        layout.addSpacing(10)
        sec_steam = QLabel(L.t("settings.section.steam")); sec_steam.setObjectName("SectionTitle"); layout.addWidget(sec_steam)

        self.auto_steam = QCheckBox(L.t("settings.auto_steam"))
        self.auto_steam.setChecked(self.config.get("auto_steam_import", True))
        layout.addWidget(self.auto_steam)

        steam_row = QHBoxLayout()
        detected = find_steam_path(self.config.get("steam_path", ""))
        self.steam_input = QLineEdit(str(detected) if detected else self.config.get("steam_path", ""))
        self.steam_input.setPlaceholderText(L.t("settings.steam_missing"))
        self.steam_input.setCursorPosition(0)
        sb = self._browse_button(self._browse_steam)
        steam_row.addWidget(self.steam_input); steam_row.addWidget(sb)
        row_steam = QHBoxLayout(); lbl_steam = QLabel(L.t("settings.steam_path")); lbl_steam.setFixedWidth(150)
        row_steam.addWidget(lbl_steam); row_steam.addLayout(steam_row); layout.addLayout(row_steam)

        layout.addSpacing(10)
        sec_updates = QLabel(L.t("settings.section.updates")); sec_updates.setObjectName("SectionTitle"); layout.addWidget(sec_updates)

        self.check_updates = QCheckBox(L.t("settings.check_updates"))
        self.check_updates.setChecked(self.config.get("check_updates", True))
        layout.addWidget(self.check_updates)

        upd_row = QHBoxLayout()
        check_now = QPushButton(L.t("settings.check_now")); check_now.setObjectName("Secondary")
        check_now.clicked.connect(self._request_update_check)
        upd_row.addWidget(check_now); upd_row.addStretch(); layout.addLayout(upd_row)

        layout.addSpacing(10)
        sec_cache = QLabel(L.t("settings.section.cache")); sec_cache.setObjectName("SectionTitle"); layout.addWidget(sec_cache)

        self.covers_label = QLabel(""); self.covers_label.setStyleSheet("color: #888888; font-size: 12px;")
        self.covers_label.setWordWrap(True)
        layout.addWidget(self.covers_label)
        self._update_covers()

        covers_row = QHBoxLayout()
        cc = QPushButton(L.t("settings.clear_covers")); cc.setObjectName("Danger"); cc.clicked.connect(self._clear_covers)
        covers_row.addWidget(cc); covers_row.addStretch(); layout.addLayout(covers_row)

        layout.addSpacing(10)
        sec_anim = QLabel(L.t("settings.section.animations")); sec_anim.setObjectName("SectionTitle"); layout.addWidget(sec_anim)

        self.animations_cb = QCheckBox(L.t("settings.animations"))
        self.animations_cb.setChecked(self.config.get("animations", True))
        layout.addWidget(self.animations_cb)

        anim_style_row = QHBoxLayout()
        lbl_astyle = QLabel(L.t("settings.animation_style")); lbl_astyle.setFixedWidth(150)
        self.anim_style_combo = QComboBox()
        self.anim_style_combo.addItem(L.t("settings.animation_style.slide"), "slide")
        self.anim_style_combo.addItem(L.t("settings.animation_style.fade"), "fade")
        self._select_combo_value(self.anim_style_combo, self.config.get("animation_style", "slide"))
        anim_style_row.addWidget(lbl_astyle); anim_style_row.addWidget(self.anim_style_combo)
        layout.addLayout(anim_style_row)

        anim_speed_row = QHBoxLayout()
        lbl_aspeed = QLabel(L.t("settings.animation_speed")); lbl_aspeed.setFixedWidth(150)
        self.anim_speed_combo = QComboBox()
        self.anim_speed_combo.addItem(L.t("settings.animation_speed.fast"), "fast")
        self.anim_speed_combo.addItem(L.t("settings.animation_speed.normal"), "normal")
        self.anim_speed_combo.addItem(L.t("settings.animation_speed.smooth"), "smooth")
        self._select_combo_value(self.anim_speed_combo, self.config.get("animation_speed", "normal"))
        anim_speed_row.addWidget(lbl_aspeed); anim_speed_row.addWidget(self.anim_speed_combo)
        layout.addLayout(anim_speed_row)

        anim_hint = QLabel(L.t("settings.animations_hint"))
        anim_hint.setWordWrap(True)
        anim_hint.setStyleSheet("color: #666666; font-size: 11px;")
        layout.addWidget(anim_hint)

        self.animations_cb.toggled.connect(self._update_animation_controls)
        self._update_animation_controls(self.animations_cb.isChecked())

        layout.addSpacing(10)
        sec4 = QLabel(L.t("settings.section.language")); sec4.setObjectName("SectionTitle"); layout.addWidget(sec4)

        lang_row = QHBoxLayout()
        self.lang_combo = QComboBox()
        items = sorted(L.available.items(), key=lambda x: (x[0] != "en", x[1].lower()))
        for code, name in items:
            self.lang_combo.addItem(name, code)
        cur = self.config.get("language", "en")
        for i in range(self.lang_combo.count()):
            if self.lang_combo.itemData(i) == cur:
                self.lang_combo.setCurrentIndex(i)
                break
        lang_row.addWidget(self.lang_combo)
        row_lang = QHBoxLayout(); lbl_lang = QLabel(L.t("settings.language")); lbl_lang.setFixedWidth(150)
        row_lang.addWidget(lbl_lang); row_lang.addLayout(lang_row); layout.addLayout(row_lang)

        layout.addStretch()

        btns = QHBoxLayout()
        btns.setContentsMargins(35, 10, 35, 20)
        r = QPushButton(L.t("settings.reset")); r.setObjectName("Secondary"); r.clicked.connect(self._reset)
        c2 = QPushButton(L.t("settings.cancel")); c2.setObjectName("Secondary"); c2.clicked.connect(self.reject)
        s = QPushButton(L.t("settings.save")); s.clicked.connect(self._save)
        btns.addWidget(r); btns.addStretch(); btns.addWidget(c2); btns.addWidget(s)
        outer.addLayout(btns)

    @staticmethod
    def _select_combo_value(combo, value):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _update_animation_controls(self, enabled):
        self.anim_style_combo.setEnabled(bool(enabled))
        self.anim_speed_combo.setEnabled(bool(enabled))

    def _browse_button(self, slot):
        """Compact icon button used to pick a folder next to a path field."""
        btn = QPushButton("…")
        btn.setObjectName("Compact")
        btn.setFixedSize(45, 39)
        btn.setToolTip(L.t("settings.browse"))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        icon = get_icon("folder", 16)
        if icon:
            btn.setIcon(icon)
            btn.setIconSize(QSize(16, 16))
            btn.setText("")
        btn.clicked.connect(slot)
        return btn

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, L.t("settings.games_dir"))
        if d: self.games_input.setText(d)

    def _browse_steam(self):
        d = QFileDialog.getExistingDirectory(self, L.t("settings.steam_path"))
        if d: self.steam_input.setText(d)

    def _update_covers(self):
        count, size = cover_cache_stats()
        self.covers_label.setText(L.t("settings.covers_info", count=count, size=human_size(size)))

    def _clear_covers(self):
        try:
            clear_cover_cache()
            self._update_covers()
            QMessageBox.information(self, L.t("settings.section.cache"), L.t("settings.covers_cleared"))
        except Exception as e:
            QMessageBox.critical(self, L.t("settings.section.cache"), L.t("settings.temp_clear.error", error=str(e)))

    def _request_update_check(self):
        self._save()
        self.check_updates_requested.emit()

    def _update_temp(self):
        t = self.config.get("temp_dir", str(CACHE_DIR))
        self.temp_label.setText(L.t("settings.temp_info", path=t, size=human_size(dir_size(t))))

    def _open_temp(self):
        t = self.config.get("temp_dir", str(CACHE_DIR))
        os.makedirs(t, exist_ok=True)
        if os.name == 'nt': os.startfile(t)
        elif sys.platform == 'darwin': subprocess.Popen(['open', t])
        else: subprocess.Popen(['xdg-open', t])

    def _clear_temp(self):
        t = self.config.get("temp_dir", str(CACHE_DIR))
        if not os.path.exists(t):
            QMessageBox.information(self, L.t("settings.clear_now"), L.t("settings.temp_missing"))
            return
        r = QMessageBox.question(self, L.t("settings.clear_now"),
                                 L.t("settings.temp_clear.confirm", size=human_size(dir_size(t))))
        if r == QMessageBox.StandardButton.Yes:
            try:
                shutil.rmtree(t, ignore_errors=True)
                os.makedirs(t, exist_ok=True)
                self._update_temp()
                QMessageBox.information(self, L.t("settings.clear_now"), L.t("settings.temp_clear.done"))
            except Exception as e:
                QMessageBox.critical(self, L.t("settings.clear_now"), L.t("settings.temp_clear.error", error=str(e)))

    def _reset(self):
        r = QMessageBox.question(self, L.t("settings.reset"), L.t("settings.reset.confirm"))
        if r == QMessageBox.StandardButton.Yes:
            self.games_input.setText(str(GAMES_DIR))
            self.auto_cleanup.setChecked(True)
            self.show_ext.setChecked(False)
            self.start_collapsed.setChecked(False)
            self.auto_steam.setChecked(True)
            self.check_updates.setChecked(True)
            self.animations_cb.setChecked(True)
            self._select_combo_value(self.anim_style_combo, "slide")
            self._select_combo_value(self.anim_speed_combo, "normal")
            self.steam_input.setText(str(find_steam_path() or ""))
            for i in range(self.lang_combo.count()):
                if self.lang_combo.itemData(i) == "en":
                    self.lang_combo.setCurrentIndex(i)
                    break

    def _save(self):
        self.config["games_dir"] = self.games_input.text()
        self.config["auto_cleanup"] = self.auto_cleanup.isChecked()
        self.config["show_extensions"] = self.show_ext.isChecked()
        self.config["sidebar_collapsed"] = self.start_collapsed.isChecked()
        self.config["auto_steam_import"] = self.auto_steam.isChecked()
        self.config["steam_path"] = self.steam_input.text().strip()
        self.config["check_updates"] = self.check_updates.isChecked()
        self.config["animations"] = self.animations_cb.isChecked()
        self.config["animation_style"] = self.anim_style_combo.currentData() or "slide"
        self.config["animation_speed"] = self.anim_speed_combo.currentData() or "normal"
        self.config["language"] = self.lang_combo.currentData()
        save_json(CONFIG_PATH, self.config)
        self.settings_applied.emit(self.config)
        self.accept()


class AboutDialog(FadeInDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(L.t("about.title"))
        self.setWindowIcon(QApplication.windowIcon())
        self.resize(480, 440)
        self.setStyleSheet("""
            QDialog { background-color: #0A0A0A; }
            QLabel { color: #CCCCCC; font-size: 13px; }
            QPushButton { background-color: #FFFFFF; color: #000000; padding: 10px 22px; border-radius: 8px; font-weight: bold; font-size: 13px; }
            QPushButton:hover { background-color: #E0E0E0; }
            QPushButton#Secondary { background-color: #141414; color: #DDDDDD; border: 1px solid #2A2A2A; }
            QPushButton#Secondary:hover { background-color: #222222; }
        """)
        self.check_requested = False
        l = QVBoxLayout(self)
        l.setContentsMargins(40, 35, 40, 35)
        l.setSpacing(15)
        l.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        logo_path = ICON_DIR / "logo.png"
        if logo_path.exists():
            sym = QLabel()
            sym.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pm = QPixmap(str(logo_path))
            if not pm.isNull():
                sym.setPixmap(pm.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))
            l.addWidget(sym)
        else:
            sym = QLabel("✦")
            sym.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sym.setStyleSheet("color: #FFFFFF; font-size: 48px; font-weight: 900;")
            l.addWidget(sym)

        title = QLabel(L.t("app.title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #FFFFFF; font-size: 26px; font-weight: 900; letter-spacing: -1px;")
        l.addWidget(title)

        ver = QLabel(L.t("about.version"))
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet("color: #555555; font-size: 10px; letter-spacing: 5px;")
        l.addWidget(ver)

        l.addSpacing(15)

        desc = QLabel(L.t("about.description"))
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #666666; font-size: 12px; line-height: 20px;")
        l.addWidget(desc)

        l.addStretch()

        check = QPushButton(L.t("about.check_updates"))
        check.setObjectName("Secondary")
        check.clicked.connect(self._request_check)
        l.addWidget(check, alignment=Qt.AlignmentFlag.AlignCenter)

        ok = QPushButton(L.t("about.close"))
        ok.clicked.connect(self.accept)
        l.addWidget(ok, alignment=Qt.AlignmentFlag.AlignCenter)

    def _request_check(self):
        self.check_requested = True
        self.accept()


class SteamScanThread(QThread):
    scanned = pyqtSignal(list, str)

    def __init__(self, steam_path):
        super().__init__()
        self.steam_path = steam_path

    def run(self):
        try:
            games = scan_steam_games(self.steam_path)
            self.scanned.emit(games, "")
        except Exception as e:
            log.exception("Ошибка сканирования Steam")
            self.scanned.emit([], str(e))


class SteamImportDialog(FadeInDialog):
    """Lists installed Steam games and lets the user add them to the library."""

    def __init__(self, steam_path, existing_keys, parent=None):
        super().__init__(parent)
        self.steam_path = steam_path
        self.existing_keys = set(existing_keys)
        self.games = []
        self.rows = []
        self.cover_loaders = []
        self.scanner = None

        self.selected_keys = set()
        self.setWindowTitle(L.t("steam.title"))
        self.setWindowIcon(QApplication.windowIcon())
        self.resize(700, 660)
        self.setStyleSheet("""
            QDialog { background-color: #0A0A0A; }
            QLabel { color: #CCCCCC; font-size: 13px; }
            QScrollArea { background: transparent; border: none; }
            QScrollArea > QWidget > QWidget { background: transparent; }
            QLineEdit { background-color: #141414; color: #FFFFFF; border: 1px solid #222222; border-radius: 8px; padding: 9px 12px; font-size: 12px; }
            QLineEdit:focus { border: 1px solid #333333; }
            QCheckBox { color: #DDDDDD; font-size: 13px; spacing: 10px; }
            QCheckBox::indicator { width: 18px; height: 18px; background-color: #141414; border: 1px solid #333333; border-radius: 4px; }
            QCheckBox::indicator:checked { background-color: #FFFFFF; border: 1px solid #FFFFFF; }
            QPushButton { background-color: #FFFFFF; color: #000000; padding: 9px 18px; border-radius: 8px; font-weight: bold; font-size: 13px; }
            QPushButton:hover { background-color: #E0E0E0; }
            QPushButton#Secondary { background-color: #141414; color: #DDDDDD; border: 1px solid #2A2A2A; }
            QPushButton#Secondary:hover { background-color: #222222; }
            QScrollBar:vertical { background: transparent; width: 8px; }
            QScrollBar::handle:vertical { background: #222222; border-radius: 4px; min-height: 40px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 25, 30, 25)
        root.setSpacing(12)

        title = QLabel(L.t("steam.title"))
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: 900; letter-spacing: -1px;")
        root.addWidget(title)

        sub = QLabel(L.t("steam.subtitle"))
        sub.setStyleSheet("color: #666666; font-size: 12px;")
        root.addWidget(sub)

        self.path_label = QLabel(L.t("steam.path", path=str(steam_path) if steam_path else L.t("settings.steam_missing")))
        self.path_label.setStyleSheet("color: #444444; font-size: 11px;")
        root.addWidget(self.path_label)

        hint = QLabel(L.t("steam.selection_hint"))
        hint.setStyleSheet("color: #555555; font-size: 11px;")
        root.addWidget(hint)

        self.search = QLineEdit()
        self.search.setPlaceholderText(L.t("steam.search_placeholder"))
        self.search.textChanged.connect(self._populate)
        root.addWidget(self.search)

        self.status = QLabel(L.t("steam.scanning"))
        self.status.setStyleSheet("color: #777777; font-size: 11px;")
        root.addWidget(self.status)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.host = QWidget()
        self.list_layout = QVBoxLayout(self.host)
        self.list_layout.setContentsMargins(2, 2, 2, 2)
        self.list_layout.setSpacing(4)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.host)
        root.addWidget(self.scroll, stretch=1)

        tools = QHBoxLayout()
        self.sel_all = QPushButton(L.t("steam.select_all")); self.sel_all.setObjectName("Secondary")
        self.sel_none = QPushButton(L.t("steam.select_none")); self.sel_none.setObjectName("Secondary")
        self.sel_all.clicked.connect(lambda: self._set_all(True))
        self.sel_none.clicked.connect(lambda: self._set_all(False))
        tools.addWidget(self.sel_all); tools.addWidget(self.sel_none); tools.addStretch()
        root.addLayout(tools)

        buttons = QHBoxLayout()
        cancel = QPushButton(L.t("settings.cancel")); cancel.setObjectName("Secondary"); cancel.clicked.connect(self.reject)
        self.add_btn = QPushButton(L.t("steam.apply_selection", count=0))
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self._accept_selection)
        buttons.addStretch(); buttons.addWidget(cancel); buttons.addWidget(self.add_btn)
        root.addLayout(buttons)

        self._start_scan()

    def _start_scan(self):
        if not self.steam_path:
            self.status.setText(L.t("steam.not_found"))
            return
        self.scanner = SteamScanThread(self.steam_path)
        self.scanner.scanned.connect(self._on_scanned)
        self.scanner.start()

    def _on_scanned(self, games, error):
        if error:
            self.status.setText(L.t("update.check_failed", error=error))
            return
        self.games = games
        if not games:
            self.status.setText(L.t("steam.empty"))
            return
        self.status.setText(L.t("steam.found", count=len(games)))
        self._populate()

    def _populate(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.rows.clear()

        query = self.search.text().strip().lower()
        for game in self.games:
            if query and query not in game["name"].lower():
                continue
            already = game["key"] in self.existing_keys
            row = QWidget()
            row.setStyleSheet("QWidget { background: transparent; }")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(6, 4, 6, 4)
            rl.setSpacing(10)

            cb = QCheckBox()
            cb.setChecked(already)
            cb.setToolTip(L.t("steam.selection_hint"))
            cb.stateChanged.connect(self._update_count)

            thumb = QLabel()
            thumb.setFixedSize(92, 43)
            thumb.setStyleSheet("background-color: #141414; border-radius: 6px; color: #444444;")
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setText("Steam" if not (game.get("cover_path") or game.get("cover_url")) else "")
            if game.get("cover_path") or game.get("cover_url"):
                loader = CoverLoader(game["key"], game.get("cover_path", ""), game.get("cover_url", ""))
                loader.signals.loaded.connect(lambda key, img, lbl=thumb: self._set_thumb(lbl, img))
                self.cover_loaders.append(loader)
                QThreadPool.globalInstance().start(loader)

            info = QVBoxLayout()
            info.setSpacing(2)
            name = QLabel(game["name"])
            name.setWordWrap(True)
            name.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: 600;")
            meta = QLabel(human_size(game.get("size", 0)))
            meta.setStyleSheet("color: #666666; font-size: 10px;")
            if already:
                meta.setText(f"{human_size(game.get('size', 0))}  •  {L.t('steam.already_added')}")
            info.addWidget(name); info.addWidget(meta)

            rl.addWidget(cb); rl.addWidget(thumb); rl.addLayout(info, stretch=1)
            self.list_layout.addWidget(row)
            self.rows.append((game, cb))

        self._update_count()

    def _set_thumb(self, label, image):
        if image.isNull():
            return
        pm = QPixmap.fromImage(image).scaled(
            92, 43, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation)
        label.setPixmap(pm)

    def _set_all(self, checked):
        for _, cb in self.rows:
            cb.setChecked(checked)

    def _selected(self):
        return [game for game, cb in self.rows if cb.isChecked()]

    def _update_count(self):
        count = len(self._selected())
        self.add_btn.setText(L.t("steam.apply_selection", count=count))
        self.add_btn.setEnabled(bool(self.rows))

    def _accept_selection(self):
        self.selected_games = self._selected()
        self.selected_keys = {game["key"] for game in self.selected_games}
        self.accept()

    def closeEvent(self, event):
        if self.scanner and self.scanner.isRunning():
            self.scanner.wait(1500)
        super().closeEvent(event)


class UpdateCheckThread(QThread):
    checked = pyqtSignal(dict, str)

    def run(self):
        try:
            release = fetch_latest_release()
            self.checked.emit(release, "")
        except urllib.error.HTTPError as e:
            message = f"GitHub API {e.code}"
            if e.code == 403:
                message = "GitHub API rate limit (403)"
            self.checked.emit({}, message)
        except Exception as e:
            log.warning(f"Не удалось проверить обновления: {e}")
            self.checked.emit({}, str(e))


class UpdateDownloadThread(QThread):
    progress = pyqtSignal(int)
    downloaded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, asset, expected_version):
        super().__init__()
        self.asset = asset
        self.expected_version = expected_version

    def run(self):
        try:
            UPDATES_DIR.mkdir(parents=True, exist_ok=True)
            name = self.asset.get("name") or f"Devers-Launcher-{self.expected_version}.zip"
            safe_name = re.sub(r"[^\w.\- ]+", "_", name)
            target = UPDATES_DIR / safe_name
            partial = target.with_name(target.name + ".part")
            req = urllib.request.Request(
                self.asset["browser_download_url"],
                headers={"User-Agent": USER_AGENT},
            )
            total = int(self.asset.get("size", 0) or 0)
            received = 0
            with urllib.request.urlopen(req, timeout=30) as resp, open(partial, "wb") as f:
                total = int(resp.headers.get("Content-Length") or total or 0)
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
                    if total > 0:
                        self.progress.emit(min(100, int(received * 100 / total)))
                    else:
                        self.progress.emit(-1)
            if total > 0 and received < total:
                raise IOError(f"Incomplete download ({received}/{total} bytes)")
            os.replace(partial, target)
            self.progress.emit(100)
            self.downloaded.emit(str(target))
        except Exception as e:
            log.exception("Ошибка загрузки обновления")
            self.failed.emit(str(e))


UPDATE_DIALOG_STYLE = """
    QDialog { background-color: #0A0A0A; }
    QLabel { color: #CCCCCC; font-size: 13px; }
    QLabel#DialogTitle { color: #FFFFFF; font-size: 22px; font-weight: 900; letter-spacing: -1px; }
    QLabel#DialogSub { color: #666666; font-size: 12px; }
    QProgressBar { background-color: #1A1A1A; border: none; border-radius: 6px; height: 12px; text-align: center; color: transparent; }
    QProgressBar::chunk { background-color: #FFFFFF; border-radius: 6px; }
    QPushButton { background-color: #FFFFFF; color: #000000; padding: 10px 20px; border-radius: 8px; font-weight: bold; font-size: 13px; }
    QPushButton:hover { background-color: #E0E0E0; }
    QPushButton:disabled { background-color: #333333; color: #777777; }
    QPushButton#Secondary { background-color: #141414; color: #DDDDDD; border: 1px solid #2A2A2A; }
    QPushButton#Secondary:hover { background-color: #222222; }
    QScrollArea { background: transparent; border: none; }
    QScrollArea > QWidget > QWidget { background: transparent; }
    QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
    QScrollBar::handle:vertical { background: #222222; border-radius: 4px; min-height: 40px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
"""


def dialog_logo_label(size=52):
    """Returns the app logo (or a fallback mark) as a QLabel."""
    label = QLabel()
    label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    logo_path = ICON_DIR / "logo.png"
    if logo_path.exists():
        pm = QPixmap(str(logo_path))
        if not pm.isNull():
            label.setPixmap(pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
            return label
    label.setText("✦")
    label.setStyleSheet(f"color: #FFFFFF; font-size: {int(size * 0.7)}px; font-weight: 900;")
    return label


class UpdateCheckDialog(FadeInDialog):
    """Small non-modal dialog shown while the launcher checks GitHub."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(L.t("update.check_title"))
        self.setWindowIcon(QApplication.windowIcon())
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setModal(False)
        self.setFixedSize(420, 190)
        self.setStyleSheet(UPDATE_DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(14)
        header.addWidget(dialog_logo_label(44))

        text_box = QVBoxLayout()
        text_box.setSpacing(4)
        title = QLabel(L.t("update.check_title"))
        title.setObjectName("DialogTitle")
        hint = QLabel(L.t("update.checking_hint"))
        hint.setObjectName("DialogSub")
        hint.setWordWrap(True)
        text_box.addWidget(title)
        text_box.addWidget(hint)
        header.addLayout(text_box, stretch=1)
        layout.addLayout(header)

        layout.addStretch()

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(10)
        layout.addWidget(self.progress)


def _notes_plain_text(raw: str) -> str:
    """Turns release markdown into readable plain text for the notes panel."""
    text = raw or ""
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"[*_`>]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or "—"


class UpdateInfoDialog(FadeInDialog):
    """Styled message dialog for update checks (up to date, errors)."""

    def __init__(self, title, message, detail="", primary_text=None, retry=False,
                 secondary_text=None, page_url="", parent=None):
        super().__init__(parent)
        self.retry_requested = False
        self.setWindowTitle(title)
        self.setWindowIcon(QApplication.windowIcon())
        self.setStyleSheet(UPDATE_DIALOG_STYLE)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(14)
        header.addWidget(dialog_logo_label(48), alignment=Qt.AlignmentFlag.AlignTop)

        text_box = QVBoxLayout()
        text_box.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("DialogTitle")
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet("color: #AAAAAA; font-size: 13px;")
        text_box.addWidget(title_label)
        text_box.addWidget(message_label)
        if detail:
            detail_label = QLabel(detail)
            detail_label.setWordWrap(True)
            detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            detail_label.setStyleSheet("color: #666666; font-size: 11px;")
            text_box.addWidget(detail_label)
        header.addLayout(text_box, stretch=1)
        layout.addLayout(header)

        buttons = QHBoxLayout()
        buttons.addStretch()
        if page_url:
            page = QPushButton(L.t("update.page"))
            page.setObjectName("Secondary")
            page.clicked.connect(lambda: webbrowser.open(page_url))
            buttons.addWidget(page)
        if secondary_text:
            close_btn = QPushButton(secondary_text)
            close_btn.setObjectName("Secondary")
            close_btn.clicked.connect(self.reject)
            buttons.addWidget(close_btn)
        primary = QPushButton(primary_text or L.t("update.close"))
        primary.clicked.connect(self._primary)
        buttons.addWidget(primary)
        layout.addLayout(buttons)

    def _primary(self):
        self.retry_requested = True
        self.accept()


class UpdateDialog(FadeInDialog):
    """Shows release notes and downloads the new build."""

    install_requested = pyqtSignal(str)

    def __init__(self, release, asset, parent=None):
        super().__init__(parent)
        self.release = release
        self.asset = asset
        self.downloader = None
        self.downloaded_path = ""

        version = str(release.get("tag_name") or release.get("name") or "?")
        self.setWindowTitle(L.t("update.title"))
        self.setWindowIcon(QApplication.windowIcon())
        self.setStyleSheet(UPDATE_DIALOG_STYLE)
        self.resize(600, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(14)
        header.addWidget(dialog_logo_label(52), alignment=Qt.AlignmentFlag.AlignTop)

        head_text = QVBoxLayout()
        head_text.setSpacing(4)
        title = QLabel(L.t("update.title"))
        title.setObjectName("DialogTitle")
        found = QLabel(L.t("update.found", version=version, current=VERSION))
        found.setStyleSheet("color: #888888; font-size: 12px;")
        found.setWordWrap(True)
        head_text.addWidget(title)
        head_text.addWidget(found)
        header.addLayout(head_text, stretch=1)
        layout.addLayout(header)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        current_chip = QLabel(f"v{VERSION}")
        current_chip.setStyleSheet("color: #777777; background-color: #141414; border: 1px solid #222222; "
                                   "border-radius: 10px; padding: 4px 12px; font-size: 11px;")
        arrow = QLabel("→")
        arrow.setStyleSheet("color: #555555; font-size: 14px;")
        new_chip = QLabel(version if version.lower().startswith("v") else f"v{version}")
        new_chip.setStyleSheet("color: #000000; background-color: #FFFFFF; border-radius: 10px; "
                               "padding: 4px 12px; font-size: 11px; font-weight: bold;")
        chips.addWidget(current_chip)
        chips.addWidget(arrow)
        chips.addWidget(new_chip)
        chips.addStretch()
        if asset:
            asset_label = QLabel(L.t("update.asset", name=asset.get("name", ""),
                                      size=human_size(asset.get("size", 0))))
            asset_label.setStyleSheet("color: #555555; font-size: 11px;")
            chips.addWidget(asset_label)
        layout.addLayout(chips)

        notes_title = QLabel(L.t("update.notes"))
        notes_title.setStyleSheet("color: #666666; font-size: 11px; letter-spacing: 1px;")
        layout.addWidget(notes_title)

        body = QLabel(_notes_plain_text(str(release.get("body") or "")))
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        body.setStyleSheet("color: #AAAAAA; font-size: 12px; background-color: #0F0F0F; "
                          "border: 1px solid #1E1E1E; border-radius: 8px; padding: 14px;")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_host = QWidget()
        sh = QVBoxLayout(scroll_host)
        sh.setContentsMargins(0, 0, 0, 0)
        sh.addWidget(body)
        sh.addStretch()
        scroll.setWidget(scroll_host)
        layout.addWidget(scroll, stretch=1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(12)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #777777; font-size: 11px;")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        page = QPushButton(L.t("update.page")); page.setObjectName("Secondary")
        page.clicked.connect(lambda: webbrowser.open(release.get("html_url") or GITHUB_RELEASES_PAGE))
        later = QPushButton(L.t("update.later")); later.setObjectName("Secondary"); later.clicked.connect(self.reject)
        self.download_btn = QPushButton(L.t("update.download"))
        self.download_btn.setEnabled(asset is not None)
        self.download_btn.clicked.connect(self._start_download)
        buttons.addWidget(page); buttons.addStretch(); buttons.addWidget(later); buttons.addWidget(self.download_btn)
        layout.addLayout(buttons)

        if asset is None:
            self.status.setText(L.t("update.no_asset"))
        elif not getattr(sys, "frozen", False):
            self.status.setText(L.t("update.source_hint"))

    def _start_download(self):
        if not self.asset or self.downloader:
            return
        self.download_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.status.setText(L.t("update.downloading", percent=0))
        self.downloader = UpdateDownloadThread(self.asset, self.release.get("tag_name", VERSION))
        self.downloader.progress.connect(self._on_progress)
        self.downloader.downloaded.connect(self._on_downloaded)
        self.downloader.failed.connect(self._on_failed)
        self.downloader.start()

    def _on_progress(self, value):
        if value < 0:
            self.progress.setRange(0, 0)
            self.status.setText(L.t("update.downloading", percent="..."))
            return
        self.progress.setRange(0, 100)
        self.progress.setValue(value)
        self.status.setText(L.t("update.downloading", percent=value))

    def _on_downloaded(self, path):
        self.downloaded_path = path
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status.setText(L.t("update.ready"))
        self.install_requested.emit(path)
        self.accept()

    def _on_failed(self, error):
        self.progress.setVisible(False)
        self.download_btn.setEnabled(True)
        self.status.setText(L.t("update.download_error", error=error))

    def closeEvent(self, event):
        if self.downloader and self.downloader.isRunning():
            self.downloader.wait(1500)
        super().closeEvent(event)


class HomePage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addStretch(1)

        self.gif = QLabel()
        self.gif.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gif.setFixedSize(340, 340)
        self.gif.setStyleSheet("background-color: transparent;")
        if GIF_PATH.exists():
            m = QMovie(str(GIF_PATH))
            m.setScaledSize(QSize(340, 340))
            self.gif.setMovie(m)
            m.start()
        else:
            self.gif.setText("devers_gif.gif not found")
            self.gif.setStyleSheet("color: #333333; font-size: 12px; background: transparent;")
        layout.addWidget(self.gif, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(35)

        title = QLabel(L.t("app.title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #FFFFFF; font-size: 40px; font-weight: 900; letter-spacing: -2px;")
        layout.addWidget(title)

        layout.addSpacing(8)

        ver = QLabel(L.t("app.subtitle"))
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet("color: #555555; font-size: 11px; letter-spacing: 5px;")
        layout.addWidget(ver)

        layout.addSpacing(25)

        desc = QLabel(L.t("app.description"))
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #666666; font-size: 13px; line-height: 22px;")
        layout.addWidget(desc)

        layout.addStretch(1)

        footer = QLabel(L.t("app.footer"))
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("color: #2A2A2A; font-size: 10px; letter-spacing: 1px;")
        layout.addWidget(footer)


class LibraryPage(QWidget):
    play_requested = pyqtSignal(str)
    context_requested = pyqtSignal(str, QPoint)
    favorite_toggled = pyqtSignal(str)
    add_requested = pyqtSignal()
    folder_requested = pyqtSignal()
    steam_requested = pyqtSignal()

    def __init__(self, config, favorites_getter, play_times_getter, launch_counts_getter, page_title, show_tools=True):
        super().__init__()
        self.config = config
        self.favorites_getter = favorites_getter
        self.play_times_getter = play_times_getter
        self.launch_counts_getter = launch_counts_getter
        self.current_manifests = {}
        self.card_widgets = {}
        self._layout_order = []
        self._layout_sig = None
        self._relayout_timer = QTimer(self)
        self._relayout_timer.setSingleShot(True)
        self._relayout_timer.setInterval(50)
        self._relayout_timer.timeout.connect(self._apply_layout)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 26)
        layout.setSpacing(14)

        tool_style = """
            QPushButton {
                background-color: #0F0F0F; color: #CCCCCC;
                border: 1px solid #1A1A1A; border-radius: 9px;
                padding: 8px 14px; font-size: 12px;
            }
            QPushButton:hover { background-color: #1C1C1C; color: #FFFFFF; border-color: #2E2E2E; }
            QPushButton:pressed { background-color: #262626; }
        """

        # --- top row: title + live count + refresh ----------------------
        header = QHBoxLayout()
        header.setSpacing(12)

        title = QLabel(page_title)
        title.setObjectName("PageTitle")
        header.addWidget(title)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #6E6E6E; font-size: 11px; padding-bottom: 5px;")
        header.addWidget(self.status, alignment=Qt.AlignmentFlag.AlignBottom)
        header.addStretch()

        self.refresh_btn = QPushButton()
        self.refresh_btn.setFixedSize(38, 38)
        self.refresh_btn.setToolTip(L.t("library.refresh"))
        refresh_icon = get_icon("refresh", 18)
        if refresh_icon:
            self.refresh_btn.setIcon(refresh_icon)
            self.refresh_btn.setIconSize(QSize(18, 18))
        else:
            self.refresh_btn.setText("↻")
        self.refresh_btn.setStyleSheet(tool_style)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)

        # --- second row: actions on the left, search/sort on the right ---
        toolbar_row = QHBoxLayout()
        toolbar_row.setSpacing(8)

        self.add_btn = QPushButton(L.t("library.add_game"))
        self.add_btn.setStyleSheet(tool_style)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setToolTip(L.t("dialog.add.filter"))
        self.add_btn.clicked.connect(self.add_requested)
        self.add_btn.setVisible(show_tools)
        toolbar_row.addWidget(self.add_btn)

        self.folder_btn = QPushButton("＋")
        self.folder_btn.setFixedSize(38, 36)
        folder_icon = get_icon("folder", 16)
        if folder_icon:
            self.folder_btn.setIcon(folder_icon)
            self.folder_btn.setIconSize(QSize(16, 16))
            self.folder_btn.setText("")
        self.folder_btn.setStyleSheet(tool_style + "QPushButton { font-size: 16px; padding: 0; }")
        self.folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder_btn.setToolTip(L.t("library.add_folder"))
        self.folder_btn.clicked.connect(self.folder_requested)
        self.folder_btn.setVisible(show_tools)
        toolbar_row.addWidget(self.folder_btn)

        self.steam_btn = QPushButton(L.t("library.steam"))
        self.steam_btn.setStyleSheet(tool_style)
        self.steam_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.steam_btn.setToolTip(L.t("steam.title"))
        self.steam_btn.clicked.connect(self.steam_requested)
        self.steam_btn.setVisible(show_tools)
        toolbar_row.addWidget(self.steam_btn)

        toolbar_row.addStretch()

        self.search = QLineEdit()
        self.search.setPlaceholderText(L.t("library.search_placeholder"))
        self.search.setFixedWidth(230)
        self.search.setStyleSheet("""
            QLineEdit {
                background-color: #0F0F0F; color: #FFFFFF;
                border: 1px solid #1A1A1A; border-radius: 9px;
                padding: 8px 14px; font-size: 12px;
            }
            QLineEdit:focus { border: 1px solid #3A3A3A; background-color: #121212; }
        """)
        search_icon = get_icon("search", 16)
        if search_icon:
            self.search.addAction(search_icon, QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(lambda: self.render(self.current_manifests))
        toolbar_row.addWidget(self.search)

        self.sort_combo = QComboBox()
        self.sort_combo.addItem(L.t("library.sort.name"))
        self.sort_combo.addItem(L.t("library.sort.size"))
        self.sort_combo.addItem(L.t("library.sort.date"))
        self.sort_combo.addItem(L.t("library.sort.time"))
        self.sort_combo.addItem(L.t("library.sort.favorites"))
        self.sort_combo.setMinimumWidth(160)
        self.sort_combo.setStyleSheet("""
            QComboBox {
                background-color: #0F0F0F; color: #CCCCCC;
                border: 1px solid #1A1A1A; border-radius: 9px;
                padding: 8px 14px; font-size: 12px;
            }
            QComboBox:hover { border-color: #2E2E2E; }
            QComboBox::drop-down { border: none; width: 22px; }
        """)
        self.sort_combo.currentIndexChanged.connect(lambda: self.render(self.current_manifests))
        toolbar_row.addWidget(self.sort_combo)
        layout.addLayout(toolbar_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.grid_host = QWidget()
        self.grid_host.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(15)
        self.grid.setContentsMargins(0, 5, 0, 5)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.scroll.setWidget(self.grid_host)
        layout.addWidget(self.scroll, stretch=1)

        # Centred "empty" overlay, shown instead of the grid when there is
        # nothing to display.  Kept out of the grid so it can be centred both
        # horizontally and vertically regardless of the column count.
        self.empty_host = QWidget()
        self.empty_host.setStyleSheet("background: transparent;")
        el = QVBoxLayout(self.empty_host)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(16)
        el.addStretch(1)

        self.empty_logo = QLabel()
        self.empty_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_path = ICON_DIR / "logo.png"
        if logo_path.exists():
            pm = QPixmap(str(logo_path))
            if not pm.isNull():
                self.empty_logo.setPixmap(pm.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                                    Qt.TransformationMode.SmoothTransformation))
        if self.empty_logo.pixmap().isNull():
            self.empty_logo.setText("✦")
            self.empty_logo.setStyleSheet("color: #2E2E2E; font-size: 44px;")
        el.addWidget(self.empty_logo, alignment=Qt.AlignmentFlag.AlignCenter)

        self._empty_message = L.t("library.empty")
        self.empty_label = QLabel(self._empty_message)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #4A4A4A; font-size: 13px; line-height: 20px;")
        el.addWidget(self.empty_label, alignment=Qt.AlignmentFlag.AlignCenter)
        el.addStretch(1)

        self.empty_host.setVisible(False)
        layout.addWidget(self.empty_host, stretch=1)

    def show_skeleton(self):
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        cols = self._columns()
        spacing = self.grid.spacing()
        margins = self.grid.contentsMargins()
        available = max(320, self.scroll.viewport().width() - margins.left() - margins.right())
        card_width = max(190, (available - spacing * (cols - 1)) // cols)
        height = CARD_HEIGHT
        for i in range(min(8, cols * 2)):
            r, c = divmod(i, cols)
            skeleton = SkeletonCard()
            skeleton.setFixedSize(card_width, height)
            self.grid.addWidget(skeleton, r, c)

    def _columns(self):
        w = self.scroll.viewport().width() if hasattr(self, 'scroll') else 800
        cols = max(1, (w - 20) // (CARD_WIDTH + 15))
        return min(cols, 5)

    def render(self, manifests):
        self.current_manifests = manifests
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        self.card_widgets.clear()
        self._layout_order = []
        self._layout_sig = None

        if not manifests:
            self.empty_label.setText(self._empty_message)
            self.empty_host.setVisible(True)
            self.scroll.setVisible(False)
            self.status.setText("")
            return

        self.empty_host.setVisible(False)
        self.scroll.setVisible(True)

        query = self.search.text().strip().lower()
        favorites = set(self.favorites_getter())
        play_times = self.play_times_getter()
        launch_counts = self.launch_counts_getter()

        items = []
        for key, meta in manifests.items():
            name = meta.get("name", key)
            if query and query not in name.lower():
                continue
            items.append((key, meta))

        mode = self.sort_combo.currentIndex()
        if mode == 0:
            items.sort(key=lambda x: x[1].get("name", "").lower())
        elif mode == 1:
            items.sort(key=lambda x: x[1].get("size", 0), reverse=True)
        elif mode == 2:
            items.sort(key=lambda x: x[1].get("mtime", 0), reverse=True)
        elif mode == 3:
            items.sort(key=lambda x: play_times.get(x[0], 0), reverse=True)
        elif mode == 4:
            items.sort(key=lambda x: (x[0] not in favorites, x[1].get("name", "").lower()))

        show_ext = self.config.get("show_extensions", False)

        # Build every card once.  Layout (columns + widths) is applied
        # separately in _apply_layout so a window resize never rebuilds them.
        for key, meta in items:
            card = GameCard(key, meta, is_favorite=key in favorites,
                            show_ext=show_ext, play_time=play_times.get(key, 0),
                            launch_count=launch_counts.get(key, 0))
            card.play_requested.connect(self.play_requested)
            card.context_menu_requested.connect(self.context_requested)
            card.favorite_toggled.connect(self.favorite_toggled)
            self.card_widgets[key] = card
            self._layout_order.append(key)

        self._layout_sig = None
        self._apply_layout()

        if ANIM.enabled():
            for i, key in enumerate(self._layout_order[:24]):
                fade_in_widget(self.card_widgets[key], 300, delay=min(260, i * 26), start=0.0)

        self.status.setText(L.t("library.found", count=len(items)))

    def _apply_layout(self):
        """(Re)position existing cards for the current viewport width.

        Cheap: it only re-adds the already-built widgets to the grid and
        resizes them in place.  Returns immediately when nothing changed,
        so repeated resize events (window drag, sidebar collapse) are free.
        """
        if not self._layout_order:
            return
        cols = self._columns()
        spacing = self.grid.spacing()
        margins = self.grid.contentsMargins()
        available = max(320, self.scroll.viewport().width() - margins.left() - margins.right())
        card_width = max(190, (available - spacing * (cols - 1)) // cols)

        sig = (cols, card_width, len(self._layout_order))
        if sig == self._layout_sig:
            return
        self._layout_sig = sig

        for i, key in enumerate(self._layout_order):
            r, c = divmod(i, cols)
            card = self.card_widgets.get(key)
            if card is None:
                continue
            card.set_card_width(card_width)
            self.grid.addWidget(card, r, c)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Debounced: many resize events collapse into a single relayout.
        self._relayout_timer.start()

    def set_empty_message(self, text):
        self._empty_message = text
        self.empty_label.setText(text)

    def set_card_progress(self, key, visible, value=0):
        card = self.card_widgets.get(key)
        if card:
            card.progress.setVisible(visible)
            if visible:
                card.set_progress_value(value)

    def update_card_stats(self, key, play_time=None, launch_count=None):
        card = self.card_widgets.get(key)
        if card:
            card.update_stats(play_time=play_time, launch_count=launch_count)


class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_json(CONFIG_PATH, DEFAULT_CONFIG)
        self.cache = load_json(CACHE_PATH, {})
        self.external = load_json(LIBRARY_PATH, {})
        self.stats = load_json(STATS_PATH, {"play_times": {}, "launch_counts": {}})
        self.manifests = {}
        self.cover_pool = QThreadPool()
        self.scanner = None
        self.steam_thread = None
        self.steam_dialog = None
        self.update_thread = None
        self.update_dialog = None
        self.latest_release = None
        self.latest_asset = None
        self.check_dialog = None
        self.manual_update_check = False
        self._steam_syncing = False
        self.extract_worker = None
        self.active_process = None
        self.active_game_key = None
        self.game_start_time = None
        self.game_start_pid = None
        self._ext_timer = None
        self._ext_baseline = None
        self._ext_started = False
        self.temp_dir = None
        self.current_page = None
        self._initialized = False
        self._shown_once = False
        self._page_animations = None

        ANIM.configure(self.config)

        self.setWindowTitle(L.t("app.title"))
        self.setWindowIcon(QApplication.windowIcon())
        self.resize(1300, 850)
        self.setMinimumSize(1050, 680)
        self.setAcceptDrops(True)

        self._apply_styles()
        self._build_ui()
        self._build_tray()
        self._build_shortcuts()

        if self.config.get("sidebar_collapsed", False):
            QTimer.singleShot(120, self.sidebar.toggle)

        QTimer.singleShot(50, self._post_show_init)

    def _post_show_init(self):
        self._initialized = True
        self.sidebar.switch("home")
        self.scan_library()
        QTimer.singleShot(2500, self._maybe_auto_check_updates)
        QTimer.singleShot(5000, self._auto_steam_sync)

    def _apply_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #000000; }
            QFrame#Sidebar { background-color: #0A0A0A; border-right: 1px solid #151515; }
            QFrame#BottomBar { background-color: #0A0A0A; border-top: 1px solid #151515; }
            QLabel#Logo { color: #FFFFFF; font-size: 24px; font-weight: 900; letter-spacing: -1px; }
            QLabel { color: #CCCCCC; font-size: 13px; }
            QLabel#PageTitle { color: #FFFFFF; font-size: 26px; font-weight: 900; letter-spacing: -1px; }
            QFrame#GameCard {
                background-color: #0D0D0D;
                border: 1px solid #1A1A1A;
                border-radius: 12px;
            }
            QFrame#GameCard:hover { border: 1px solid #2E2E2E; background-color: #111111; }
            QScrollArea { background: transparent; border: none; }
            QScrollArea > QWidget > QWidget { background: transparent; }
            QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
            QScrollBar::handle:vertical { background: #222222; border-radius: 4px; min-height: 40px; }
            QScrollBar::handle:vertical:hover { background: #444444; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        main = QHBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        self.sidebar = CollapsibleSidebar()
        self.sidebar.page_changed.connect(self.switch_page)
        self.sidebar.btn_settings.clicked.connect(self.open_settings)
        self.sidebar.btn_about.clicked.connect(self.open_about)

        self.content = QFrame()
        self.content.setStyleSheet("background-color: #000000;")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        self.page_stack = QStackedWidget()
        self.page_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self.page_stack.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        self.home_page = HomePage()
        self.library_page = LibraryPage(
            self.config,
            favorites_getter=lambda: self.config.get("favorites", []),
            play_times_getter=lambda: self.stats.get("play_times", {}),
            launch_counts_getter=lambda: self.stats.get("launch_counts", {}),
            page_title=L.t("library.title")
        )
        self.library_page.refresh_btn.clicked.connect(self.refresh_library)
        self.library_page.play_requested.connect(self.play_by_key)
        self.library_page.context_requested.connect(self.show_context_menu)
        self.library_page.favorite_toggled.connect(self.toggle_favorite)
        self.library_page.add_requested.connect(self.open_add_games)
        self.library_page.folder_requested.connect(self.open_add_folder)
        self.library_page.steam_requested.connect(self.open_steam_import)

        self.fav_page = LibraryPage(
            self.config,
            favorites_getter=lambda: self.config.get("favorites", []),
            play_times_getter=lambda: self.stats.get("play_times", {}),
            launch_counts_getter=lambda: self.stats.get("launch_counts", {}),
            page_title=L.t("sidebar.favorites"),
            show_tools=False
        )
        self.fav_page.set_empty_message(L.t("favorites.empty"))
        self.fav_page.refresh_btn.clicked.connect(self.refresh_library)
        self.fav_page.play_requested.connect(self.play_by_key)
        self.fav_page.context_requested.connect(self.show_context_menu)
        self.fav_page.favorite_toggled.connect(self.toggle_favorite)

        self.page_stack.addWidget(self.home_page)
        self.page_stack.addWidget(self.library_page)
        self.page_stack.addWidget(self.fav_page)
        self.content_layout.addWidget(self.page_stack)

        main.addWidget(self.sidebar)
        main.addWidget(self.content, stretch=1)
        root.addLayout(main, stretch=1)

        bottom = QFrame()
        bottom.setObjectName("BottomBar")
        bottom.setFixedHeight(32)
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(20, 0, 20, 0)
        self.bottom_left = QLabel(L.t("bottom.version"))
        self.bottom_left.setStyleSheet("color: #333333; font-size: 10px; letter-spacing: 0.5px;")
        bl.addWidget(self.bottom_left)
        bl.addSpacing(14)

        self.bottom_stats = QLabel("")
        self.bottom_stats.setStyleSheet("color: #3A3A3A; font-size: 10px; letter-spacing: 0.5px;")
        bl.addWidget(self.bottom_stats)
        bl.addSpacing(14)

        self.update_chip = QPushButton("")
        self.update_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_chip.setVisible(False)
        self.update_chip.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF; color: #000000;
                border: none; border-radius: 9px;
                padding: 3px 12px; font-size: 10px; font-weight: bold;
            }
            QPushButton:hover { background-color: #D8D8D8; }
        """)
        self.update_chip.clicked.connect(self._open_latest_update)
        bl.addWidget(self.update_chip)
        bl.addStretch()
        self.bottom_right = QLabel("")
        self.bottom_right.setStyleSheet("color: #333333; font-size: 10px; letter-spacing: 0.5px;")
        bl.addWidget(self.bottom_right)
        root.addWidget(bottom)
        self._update_bottom()

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self)
        if APP_ICON.exists():
            self.tray.setIcon(QIcon(str(APP_ICON)))
        else:
            tray_icon = get_icon("tray", 64)
            if tray_icon:
                self.tray.setIcon(tray_icon)
            else:
                self.tray.setIcon(QApplication.windowIcon())
        self.tray.setToolTip(L.t("app.title"))

        menu = QMenu()
        show_action = QAction(L.t("tray.show"), self)
        show_action.triggered.connect(self._show_from_tray)
        check_action = QAction(L.t("tray.check_updates"), self)
        check_action.triggered.connect(lambda: QTimer.singleShot(150, lambda: self.check_updates(manual=True)))
        settings_action = QAction(L.t("tray.settings"), self)
        settings_action.triggered.connect(self.open_settings)
        quit_action = QAction(L.t("tray.quit"), self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(check_action)
        menu.addAction(settings_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _build_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self.scan_library)
        QShortcut(QKeySequence("Esc"), self, activated=lambda: self.sidebar.switch("home"))
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self._quit_app)

    def _focus_search(self):
        if self.current_page in ("library", "favorites"):
            page = self.library_page if self.current_page == "library" else self.fav_page
            page.search.setFocus()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self):
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event):
        if self.tray.isVisible():
            event.ignore()
            self.hide()
            self.tray.showMessage(L.t("tray.minimized_title"), L.t("tray.minimized_msg"),
                                  QSystemTrayIcon.MessageIcon.Information, 1500)
        else:
            event.accept()

    def showEvent(self, event):
        super().showEvent(event)
        if self._shown_once or not ANIM.enabled():
            return
        self._shown_once = True
        duration = ANIM.duration(300)
        if duration <= 0:
            return
        try:
            self.setWindowOpacity(0.0)
            self._window_fade = QPropertyAnimation(self, b"windowOpacity", self)
            self._window_fade.setDuration(duration)
            self._window_fade.setStartValue(0.0)
            self._window_fade.setEndValue(1.0)
            self._window_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._window_fade.start()
        except Exception:
            self.setWindowOpacity(1.0)

    def switch_page(self, key, animate=True):
        order = {"home": 0, "library": 1, "favorites": 2}
        pages = {"home": self.home_page, "library": self.library_page, "favorites": self.fav_page}
        target = pages.get(key)
        if not target or key not in order:
            return
        if key == self.current_page and self._initialized:
            return

        previous_index = self.page_stack.currentIndex()
        index = self.page_stack.indexOf(target)
        self.current_page = key

        for k, btn in self.sidebar.nav_buttons.items():
            if k in ("settings", "about"):
                continue
            want = (k == key)
            if btn.isChecked() != want:
                btn.blockSignals(True)
                btn.setChecked(want)
                btn.blockSignals(False)
                self.sidebar._render(btn, self.sidebar.is_collapsed)

        if index == previous_index:
            return

        if animate and self._initialized and ANIM.enabled() and previous_index >= 0:
            direction = 1 if index > previous_index else -1
            self._animate_page_switch(previous_index, index, direction)
        else:
            self.page_stack.setCurrentIndex(index)

        if key in ("library", "favorites") and self._initialized:
            self.scan_library()

    def _animate_page_switch(self, previous_index, index, direction=1):
        """Slides / fades between pages for a smooth navigation feel."""
        stack = self.page_stack
        old_widget = stack.widget(previous_index)
        new_widget = stack.widget(index)
        width = stack.width()
        height = stack.height()

        snapshot = None
        if old_widget is not None and width > 10 and height > 10:
            try:
                snapshot = old_widget.grab()
            except Exception:
                snapshot = None

        stack.setCurrentIndex(index)
        if new_widget is None or width <= 10 or height <= 10:
            return

        duration = ANIM.duration(320)
        group = QParallelAnimationGroup(self)
        sliding = ANIM.style == "slide"
        offset = width * (1 if direction >= 0 else -1)

        overlay = None
        if snapshot is not None and not snapshot.isNull():
            overlay = QLabel(stack)
            overlay.setPixmap(snapshot)
            overlay.setGeometry(0, 0, width, height)
            overlay.show()
            overlay.raise_()
            overlay_effect = QGraphicsOpacityEffect(overlay)
            overlay_effect.setOpacity(1.0)
            overlay.setGraphicsEffect(overlay_effect)
            fade_out = QPropertyAnimation(overlay_effect, b"opacity", self)
            fade_out.setDuration(duration)
            fade_out.setStartValue(1.0)
            fade_out.setEndValue(0.0)
            fade_out.setEasingCurve(QEasingCurve.Type.InOutCubic)
            group.addAnimation(fade_out)
            if sliding:
                move_out = QPropertyAnimation(overlay, b"pos", self)
                move_out.setDuration(duration)
                move_out.setStartValue(QPoint(0, 0))
                move_out.setEndValue(QPoint(-offset, 0))
                move_out.setEasingCurve(QEasingCurve.Type.OutCubic)
                group.addAnimation(move_out)

        if sliding:
            new_widget.setGeometry(0, 0, width, height)
            new_widget.move(offset, 0)
            move_in = QPropertyAnimation(new_widget, b"pos", self)
            move_in.setDuration(duration)
            move_in.setStartValue(QPoint(offset, 0))
            move_in.setEndValue(QPoint(0, 0))
            move_in.setEasingCurve(QEasingCurve.Type.OutCubic)
            group.addAnimation(move_in)
        else:
            new_effect = QGraphicsOpacityEffect(new_widget)
            new_effect.setOpacity(0.0)
            new_widget.setGraphicsEffect(new_effect)
            fade_in = QPropertyAnimation(new_effect, b"opacity", self)
            fade_in.setDuration(duration)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
            group.addAnimation(fade_in)
            group.finished.connect(lambda: self._clean_page_effect(new_widget))

        def cleanup():
            if overlay is not None:
                overlay.hide()
                overlay.deleteLater()
            try:
                new_widget.move(0, 0)
            except Exception:
                pass

        group.finished.connect(cleanup)
        group.start()
        self._page_animations = group
        self._page_animation_widget = new_widget

    @staticmethod
    def _clean_page_effect(widget):
        try:
            widget.setGraphicsEffect(None)
        except Exception:
            pass

    def _update_bottom(self):
        t = self.config.get("temp_dir", str(CACHE_DIR))
        self.bottom_right.setText(L.t("bottom.temp", size=human_size(dir_size(t))))
        steam_count = sum(1 for meta in self.manifests.values() if meta.get("type") == "steam")
        self.bottom_stats.setText(L.t("bottom.stats", games=len(self.manifests), steam=steam_count))

    def scan_library(self):
        games_dir = self.config.get("games_dir", str(GAMES_DIR))
        os.makedirs(games_dir, exist_ok=True)
        self.library_page.show_skeleton()
        if self.current_page == "favorites":
            self.fav_page.show_skeleton()

        self.scanner = ManifestScanner(games_dir, self.cache, self.external)
        self.scanner.finished.connect(self._on_scan_done)
        self.scanner.start()

    def _on_scan_done(self, manifests):
        self.manifests = manifests
        cache_to_save = {}
        for key, meta in manifests.items():
            if meta.get("external"):
                continue
            entry = dict(meta)
            entry.pop("cover_data", None)
            cache_to_save[key] = entry
        self.cache = cache_to_save
        save_json(CACHE_PATH, cache_to_save)
        self.library_page.render(manifests)
        self._render_favorites()
        self._update_bottom()

    def _render_favorites(self):
        favs = set(self.config.get("favorites", []))
        filtered = {k: v for k, v in self.manifests.items() if k in favs}
        self.fav_page.render(filtered)

    def toggle_favorite(self, key):
        favs = self.config.get("favorites", [])
        if key in favs:
            favs.remove(key)
        else:
            favs.append(key)
        self.config["favorites"] = favs
        save_json(CONFIG_PATH, self.config)
        self.library_page.render(self.manifests)
        self._render_favorites()

    def show_context_menu(self, key, global_pos):
        if key not in self.manifests:
            return
        meta = self.manifests[key]
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0F0F0F; color: #FFFFFF;
                border: 1px solid #222222; border-radius: 8px;
                padding: 6px;
            }
            QMenu::item { padding: 8px 24px; border-radius: 6px; }
            QMenu::item:selected { background-color: #222222; }
            QMenu::separator { height: 1px; background: #1A1A1A; margin: 4px 8px; }
        """)
        favs = set(self.config.get("favorites", []))

        act_play = QAction(L.t("menu.play"), self)
        play_icon = get_icon("play", 16)
        if play_icon: act_play.setIcon(play_icon)
        menu.addAction(act_play)

        if key in favs:
            act_fav = QAction(L.t("menu.favorite_remove"), self)
            ic = get_icon_tinted("star_filled", 16, QColor(255, 209, 102))
            if ic: act_fav.setIcon(ic)
        else:
            act_fav = QAction(L.t("menu.favorite_add"), self)
            ic = get_icon("star", 16)
            if ic: act_fav.setIcon(ic)
        menu.addAction(act_fav)

        menu.addSeparator()

        act_open = QAction(L.t("menu.open_folder"), self)
        ic = get_icon("folder", 16)
        if ic: act_open.setIcon(ic)
        menu.addAction(act_open)

        act_rename = QAction(L.t("menu.rename"), self)
        ic = get_icon("edit", 16)
        if ic: act_rename.setIcon(ic)
        menu.addAction(act_rename)

        menu.addSeparator()

        is_external = bool(meta.get("external"))
        act_delete = QAction(L.t("menu.remove") if is_external else L.t("menu.delete"), self)
        ic = get_icon_tinted("trash", 16, QColor(255, 107, 107))
        if ic: act_delete.setIcon(ic)
        menu.addAction(act_delete)

        action = menu.exec(global_pos)
        if action == act_play:
            self.play_by_key(key)
        elif action == act_fav:
            self.toggle_favorite(key)
        elif action == act_open:
            self._open_game_folder(meta)
        elif action == act_rename:
            new_name, ok = QInputDialog.getText(self, L.t("dialog.rename.title"),
                                                L.t("dialog.rename.prompt"),
                                                text=meta.get("name", ""))
            if ok and new_name:
                self._rename_game(key, new_name)
        elif action == act_delete:
            if is_external:
                self._remove_external_game(key)
            else:
                r = QMessageBox.question(self, L.t("dialog.delete.title"),
                                         L.t("dialog.delete.confirm", name=meta.get("name")))
                if r == QMessageBox.StandardButton.Yes:
                    try:
                        os.remove(meta["path"])
                        log.info(f"Удалена игра: {key}")
                        self.scan_library()
                    except Exception as e:
                        QMessageBox.critical(self, L.t("dialog.delete.title"),
                                             L.t("dialog.delete.error", error=str(e)))

    def _rename_game(self, key, new_name):
        meta = self.manifests[key]
        meta["name"] = new_name
        if meta.get("external"):
            if key in self.external:
                self.external[key]["name"] = new_name
                save_json(LIBRARY_PATH, self.external)
        else:
            self.cache[key] = meta
            save_json(CACHE_PATH, self.cache)
        self.library_page.render(self.manifests)
        self._render_favorites()

    def _open_game_folder(self, meta):
        target = meta.get("path") or meta.get("exe") or ""
        if os.path.isfile(target):
            folder = os.path.dirname(target)
        else:
            folder = target
        if not folder or not os.path.exists(folder):
            QMessageBox.information(self, L.t("menu.open_folder"),
                                    L.t("launch.missing_path", path=target))
            return
        if os.name == 'nt':
            os.startfile(folder)  # type: ignore[attr-defined]
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', folder])
        else:
            subprocess.Popen(['xdg-open', folder])

    def _remove_external_game(self, key):
        meta = self.manifests.get(key, {})
        r = QMessageBox.question(self, L.t("dialog.remove.title"),
                                 L.t("dialog.remove.confirm", name=meta.get("name", key)))
        if r != QMessageBox.StandardButton.Yes:
            return
        entry = self.external.pop(key, None)
        if meta.get("type") == "steam":
            appid = str(meta.get("appid") or key.split(":")[-1])
            hidden = set(map(str, self.config.get("steam_hidden", [])))
            hidden.add(appid)
            self.config["steam_hidden"] = sorted(hidden)
        favorites = self.config.get("favorites", [])
        if key in favorites:
            favorites.remove(key)
            self.config["favorites"] = favorites
        save_json(CONFIG_PATH, self.config)
        save_json(LIBRARY_PATH, self.external)
        if entry:
            log.info(f"Игра удалена из библиотеки: {key}")
        self.scan_library()

    def _guess_type(self, meta):
        if meta.get("appid"):
            return "steam"
        path = meta.get("path", "")
        ext = os.path.splitext(path)[1].lower()
        return {
            ".dvp": "dvp", ".zip": "zip", ".exe": "exe",
            ".bat": "script", ".cmd": "script",
            ".lnk": "shortcut", ".url": "shortcut",
        }.get(ext, "dvp")

    def play_by_key(self, key):
        if key not in self.manifests:
            return
        if self.active_game_key and self.game_start_time:
            # A session (local or Steam/shortcut) is still running.
            still_running = (self.active_process is None) or (self.active_process.poll() is None)
            if still_running:
                QMessageBox.warning(self, L.t("menu.play"), L.t("launch.already_running"))
                return
        meta = self.manifests[key]
        if meta.get("error"):
            QMessageBox.critical(self, L.t("card.error"),
                                 L.t("launch.corrupted", error=meta["error"]))
            return

        game_type = meta.get("type") or self._guess_type(meta)
        name = meta.get("name", "game")

        if game_type == "steam":
            appid = str(meta.get("appid") or key.split(":")[-1])
            try:
                launch_steam_game(appid)
                self._register_launch(key)
                self._start_session(key)  # no Popen handle → watch processes
                self.library_page.status.setText(L.t("launch.steam_launch", name=name))
                log.info(f"Запуск через Steam: {name} (appid {appid})")
            except Exception as e:
                log.exception("Ошибка запуска Steam-игры")
                QMessageBox.critical(self, L.t("launch.start_error"),
                                     L.t("launch.steam_error", error=str(e)))
            return

        if game_type == "folder":
            folder = meta.get("path", "")
            exe = meta.get("exe") or detect_executable(folder)
            if not folder or not os.path.isdir(folder):
                QMessageBox.critical(self, L.t("launch.start_error"),
                                     L.t("launch.missing_path", path=folder))
                return
            if not exe or not os.path.exists(exe):
                QMessageBox.critical(self, L.t("launch.start_error"),
                                     L.t("launch.no_exe", name=name))
                return
            self._launch_executable(key, exe, meta)
            return

        if game_type in ("exe", "script"):
            target = meta.get("exe") or meta.get("path", "")
            self._launch_executable(key, target, meta)
            return

        if game_type == "shortcut":
            self._launch_shortcut(key, meta)
            return

        dvp_path = meta["path"]
        safe = "".join(c for c in name if c.isalnum() or c in "._- ") or "game"
        base_temp = self.config.get("temp_dir", str(CACHE_DIR))
        self.temp_dir = os.path.join(base_temp, safe)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        os.makedirs(self.temp_dir, exist_ok=True)

        self.active_game_key = key
        self.library_page.set_card_progress(key, True, 0)
        self.fav_page.set_card_progress(key, True, 0)
        self.library_page.status.setText(L.t("launch.extracting", name=name))

        self.extract_worker = ExtractWorker(dvp_path, self.temp_dir)
        self.extract_worker.progress.connect(self._on_extract_progress)
        self.extract_worker.status.connect(self.library_page.status.setText)
        self.extract_worker.finished_extract.connect(lambda p, ok, e: self._on_extracted(p, ok, e, meta))
        self.extract_worker.start()

    def _launch_executable(self, key, exe_path, meta, keep_temp=False):
        name = meta.get("name", "game")
        if not exe_path or not os.path.exists(exe_path):
            QMessageBox.critical(self, L.t("launch.start_error"),
                                 L.t("launch.missing_path", path=exe_path))
            return
        try:
            cwd = os.path.dirname(exe_path) or None
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            if exe_path.lower().endswith((".bat", ".cmd")):
                self.active_process = subprocess.Popen(
                    ["cmd", "/c", exe_path], cwd=cwd, shell=False, creationflags=flags)
            else:
                self.active_process = subprocess.Popen(
                    [exe_path], cwd=cwd, shell=False, creationflags=flags)
            if not keep_temp:
                self.temp_dir = None
            self._register_launch(key)
            self._start_session(key, process=self.active_process)
            self.library_page.status.setText(L.t("launch.playing", name=name,
                                                 pid=self.active_process.pid))
            log.info(f"Запуск: {name} (PID {self.active_process.pid})")
        except Exception as e:
            log.exception("Ошибка запуска")
            QMessageBox.critical(self, L.t("launch.start_error"), str(e))

    def _launch_shortcut(self, key, meta):
        target = meta.get("path", "")
        name = meta.get("name", "game")
        if not target or not os.path.exists(target):
            QMessageBox.critical(self, L.t("launch.start_error"),
                                 L.t("launch.missing_path", path=target))
            return
        try:
            if os.name == 'nt':
                os.startfile(target)  # type: ignore[attr-defined]
            elif sys.platform == 'darwin':
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
            self._register_launch(key)
            self._start_session(key)  # no Popen handle → watch processes
            self.library_page.status.setText(L.t("launch.direct", name=name))
        except Exception as e:
            log.exception("Ошибка запуска ярлыка")
            QMessageBox.critical(self, L.t("launch.start_error"), str(e))

    def _on_extract_progress(self, value):
        if self.active_game_key:
            self.library_page.set_card_progress(self.active_game_key, True, value)
            self.fav_page.set_card_progress(self.active_game_key, True, value)

    def _on_extracted(self, path, ok, err, meta):
        key = self.active_game_key
        self.library_page.set_card_progress(key, False)
        self.fav_page.set_card_progress(key, False)

        if not ok:
            log.error(f"Распаковка не удалась: {err}")
            QMessageBox.critical(self, L.t("launch.extract_error"), err)
            self.library_page.status.setText(L.t("launch.extract_error"))
            return

        exe_name = meta.get("exe", "")
        exe_path = None
        if exe_name:
            for root, _, files in os.walk(self.temp_dir):
                for f in files:
                    if f.lower() == os.path.basename(exe_name).lower():
                        exe_path = os.path.join(root, f)
                        break
                if exe_path:
                    break

        if not exe_path:
            detected = detect_executable(self.temp_dir)
            if detected:
                exe_path = detected
                log.info(f"Автоопределение exe: {detected}")

        if not exe_path:
            msg = L.t("launch.no_exe", name=meta.get("name", ""))
            log.error(msg)
            QMessageBox.critical(self, L.t("launch.start_error"), msg)
            self.library_page.status.setText(msg)
            return

        self._launch_executable(key, exe_path, meta, keep_temp=True)

    def _register_launch(self, key):
        """Count a launch for this game and refresh only its stats line."""
        counts = self.stats.setdefault("launch_counts", {})
        counts[key] = counts.get(key, 0) + 1
        save_json(STATS_PATH, self.stats)
        self.library_page.update_card_stats(key, launch_count=counts[key])
        self.fav_page.update_card_stats(key, launch_count=counts[key])

    def _start_session(self, key, process=None):
        """Begin a play-time session.

        When a Popen handle is available it is polled directly (accurate).
        Otherwise (Steam / shortcuts) we fall back to watching for new
        processes appearing and disappearing.
        """
        self.active_game_key = key
        self.game_start_time = time.time()
        self.active_process = process
        self._ext_baseline = snapshot_pids() if process is None else None
        self._ext_started = False
        if not hasattr(self, "_ext_timer") or self._ext_timer is None:
            self._ext_timer = QTimer(self)
            self._ext_timer.setInterval(2500)
            self._ext_timer.timeout.connect(self._poll_external_session)
        self._ext_timer.start()

    def _poll_external_session(self):
        if self.active_process is not None:
            # Local game: poll its handle directly.
            if self.active_process.poll() is not None:
                self._ext_timer.stop()
                self._finish_session()
            return

        # Steam / shortcut: watch for a new non-noise process appearing.
        baseline = self._ext_baseline or {}
        current = snapshot_pids()
        if not current:
            return
        new_procs = {pid: name for pid, name in current.items()
                     if pid not in baseline and not any(n in name for n in _LAUNCH_NOISE)}
        if new_procs:
            self._ext_started = True
            self._ext_baseline.update(new_procs)
        elif self._ext_started:
            # The game process disappeared → session over.
            self._ext_timer.stop()
            self._finish_session()

    def _finish_session(self):
        key = self.active_game_key
        duration = time.time() - self.game_start_time if self.game_start_time else 0
        if key and duration > 5:
            times = self.stats.setdefault("play_times", {})
            times[key] = times.get(key, 0) + int(duration)
            save_json(STATS_PATH, self.stats)
            self.library_page.update_card_stats(key, play_time=times[key])
            self.fav_page.update_card_stats(key, play_time=times[key])
            log.info(f"Игра {key} закрыта, время сессии: {int(duration)}с")

        self.library_page.status.setText(L.t("launch.closed"))
        if self.config.get("auto_cleanup", True) and self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                self.library_page.status.setText(L.t("launch.cleaned"))
            except Exception as e:
                log.warning(f"Не удалось очистить: {e}")
        self.temp_dir = None
        self.active_process = None
        self.active_game_key = None
        self.game_start_time = None
        self._ext_baseline = None
        self._ext_started = False
        self._update_bottom()

    def _check_process(self):
        # Back-compat shim; real work happens in _poll_external_session.
        if self.active_process is not None and self.active_process.poll() is not None:
            self._finish_session()

    # ------------------------------------------------------------------
    #  ADDING GAMES
    # ------------------------------------------------------------------

    @staticmethod
    def _external_key(path: str) -> str:
        return "local:" + hashlib.sha1(os.path.abspath(path).lower().encode("utf-8", "ignore")).hexdigest()[:12]

    def open_add_games(self):
        files, _ = QFileDialog.getOpenFileNames(self, L.t("dialog.add.title"), "", L.t("dialog.add.filter"))
        if files:
            self._add_paths(files)

    def open_add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, L.t("dialog.folder.title"))
        if folder:
            self._add_paths([folder])

    def _add_paths(self, paths):
        games_dir = self.config.get("games_dir", str(GAMES_DIR))
        os.makedirs(games_dir, exist_ok=True)
        added = 0
        errors = []

        for p in paths:
            try:
                if os.path.isdir(p):
                    key = self._external_key(p)
                    if key in self.external:
                        continue
                    self.external[key] = {
                        "type": "folder",
                        "name": Path(p).name,
                        "path": p,
                        "exe": detect_executable(p),
                        "size": dir_size(p),
                        "added": time.time(),
                    }
                    added += 1
                    continue

                ext = os.path.splitext(p)[1].lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue

                if ext in ARCHIVE_EXTENSIONS:
                    dest = os.path.join(games_dir, os.path.basename(p))
                    if os.path.abspath(dest) != os.path.abspath(p):
                        base, suffix = os.path.splitext(dest)
                        counter = 2
                        while os.path.exists(dest):
                            dest = f"{base} ({counter}){suffix}"
                            counter += 1
                        shutil.copy2(p, dest)
                    added += 1
                else:
                    key = self._external_key(p)
                    if key in self.external:
                        continue
                    if ext in (".bat", ".cmd"):
                        game_type = "script"
                    elif ext in (".lnk", ".url"):
                        game_type = "shortcut"
                    else:
                        game_type = "exe"
                    self.external[key] = {
                        "type": game_type,
                        "name": prettify_name(Path(p).stem),
                        "path": p,
                        "exe": p,
                        "size": os.path.getsize(p),
                        "added": time.time(),
                    }
                    added += 1
            except Exception as e:
                log.exception(f"Не удалось добавить {p}")
                errors.append(f"{os.path.basename(p)}: {e}")

        if added:
            save_json(LIBRARY_PATH, self.external)
            self.sidebar.switch("library")
            self.scan_library()
            self.library_page.status.setText(L.t("library.added", count=added))
            log.info(f"Добавлено игр: {added}")
        if errors:
            QMessageBox.warning(self, L.t("dialog.add.title"),
                                L.t("dialog.add.error", error="\n".join(errors[:5])))

    # ------------------------------------------------------------------
    #  STEAM IMPORT
    # ------------------------------------------------------------------

    def open_steam_import(self):
        steam_path = find_steam_path(self.config.get("steam_path", ""))
        if not steam_path:
            QMessageBox.information(self, L.t("steam.title"), L.t("steam.not_found"))
            return
        dialog = SteamImportDialog(steam_path, list(self.external.keys()), self)
        self.steam_dialog = dialog
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._apply_steam_selection(dialog.games, getattr(dialog, "selected_keys", set()))

    def _apply_steam_selection(self, games, selected_keys):
        """Adds checked Steam games and removes unchecked ones from the library."""
        hidden = set(map(str, self.config.get("steam_hidden", [])))
        added = removed = 0

        for game in games:
            key = game.get("key")
            if not key or not game.get("appid"):
                continue
            appid = str(game["appid"])
            if key in selected_keys:
                hidden.discard(appid)
                if key in self.external:
                    entry = self.external[key]
                    entry.update({
                        "name": game.get("name", entry.get("name", key)),
                        "path": game.get("path", entry.get("path", "")),
                        "size": game.get("size", entry.get("size", 0)),
                        "cover_path": game.get("cover_path") or entry.get("cover_path", ""),
                        "cover_url": game.get("cover_url") or entry.get("cover_url", ""),
                    })
                else:
                    self.external[key] = {
                        "type": "steam",
                        "appid": appid,
                        "name": game.get("name", key),
                        "path": game.get("path", ""),
                        "size": game.get("size", 0),
                        "cover_path": game.get("cover_path", ""),
                        "cover_url": game.get("cover_url", ""),
                        "added": time.time(),
                    }
                    added += 1
            elif key in self.external:
                self.external.pop(key, None)
                hidden.add(appid)
                removed += 1

        self.config["steam_hidden"] = sorted(hidden)
        self.config["steam_import_done"] = True
        save_json(CONFIG_PATH, self.config)
        save_json(LIBRARY_PATH, self.external)
        self.scan_library()
        if added or removed:
            self.library_page.status.setText(
                L.t("steam.selection_applied", added=added, removed=removed))
            log.info(f"Библиотека Steam: +{added} / -{removed}")

    def _add_steam_games(self, games):
        hidden = set(map(str, self.config.get("steam_hidden", [])))
        added = 0
        for game in games:
            key = game.get("key") or f"steam:{game.get('appid')}"
            if not game.get("appid") or key in self.external:
                continue
            hidden.discard(str(game["appid"]))
            self.external[key] = {
                "type": "steam",
                "appid": str(game["appid"]),
                "name": game.get("name", key),
                "path": game.get("path", ""),
                "size": game.get("size", 0),
                "cover_path": game.get("cover_path", ""),
                "cover_url": game.get("cover_url", ""),
                "added": time.time(),
            }
            added += 1

        if added:
            self.config["steam_hidden"] = sorted(hidden)
            self.config["steam_import_done"] = True
            save_json(CONFIG_PATH, self.config)
            save_json(LIBRARY_PATH, self.external)
            self.scan_library()
            self.library_page.status.setText(L.t("steam.added", count=added))
            log.info(f"Добавлено из Steam: {added}")

    def _auto_steam_sync(self):
        if not self.config.get("auto_steam_import", True) or self._steam_syncing:
            return
        steam_path = find_steam_path(self.config.get("steam_path", ""))
        if not steam_path:
            log.info("Steam не найден, автодобавление пропущено")
            return
        self._steam_syncing = True
        self.steam_thread = SteamScanThread(steam_path)
        self.steam_thread.scanned.connect(self._on_auto_steam)
        self.steam_thread.start()

    def _on_auto_steam(self, games, error):
        self._steam_syncing = False
        if error:
            log.warning(f"Автоимпорт Steam: {error}")
            return
        hidden = set(map(str, self.config.get("steam_hidden", [])))
        fresh_by_key = {g.get("key"): g for g in games}

        changed = False
        for key, entry in self.external.items():
            if entry.get("type") != "steam":
                continue
            fresh = fresh_by_key.get(key)
            if not fresh:
                continue
            for field in ("name", "path", "size"):
                value = fresh.get(field)
                if value is not None and entry.get(field) != value:
                    entry[field] = value
                    changed = True
            if fresh.get("cover_path"):
                if entry.get("cover_path") != fresh["cover_path"]:
                    entry["cover_path"] = fresh["cover_path"]
                    changed = True
            elif fresh.get("cover_url") and entry.get("cover_url") != fresh["cover_url"]:
                entry["cover_url"] = fresh["cover_url"]
                changed = True

        new_games = [
            g for g in games
            if g.get("key") not in self.external and str(g.get("appid", "")) not in hidden
        ]

        if new_games:
            log.info(f"Автодобавление игр Steam: {len(new_games)}")
            self._add_steam_games(new_games)
        elif changed:
            save_json(LIBRARY_PATH, self.external)
            self.scan_library()
        elif not self.config.get("steam_import_done", False):
            self.config["steam_import_done"] = True
            save_json(CONFIG_PATH, self.config)

    def refresh_library(self):
        self.scan_library()
        QTimer.singleShot(500, self._auto_steam_sync)

    # ------------------------------------------------------------------
    #  UPDATES
    # ------------------------------------------------------------------

    def _maybe_auto_check_updates(self):
        if not self.config.get("check_updates", True):
            return
        try:
            last = float(self.config.get("last_update_check", 0) or 0)
        except (TypeError, ValueError):
            last = 0
        if time.time() - last < UPDATE_CHECK_INTERVAL:
            return
        self.check_updates(manual=False)

    def check_updates(self, manual=True):
        if self.update_thread and self.update_thread.isRunning():
            if self.check_dialog is not None:
                self.check_dialog.raise_()
                self.check_dialog.activateWindow()
            return
        self.manual_update_check = manual
        if manual:
            self.library_page.status.setText(L.t("update.checking"))
            self._open_check_dialog()
        self.update_thread = UpdateCheckThread()
        self.update_thread.checked.connect(self._on_update_checked)
        self.update_thread.start()

    def _open_check_dialog(self):
        if self.check_dialog is not None:
            self.check_dialog.raise_()
            return
        dialog = UpdateCheckDialog(self)
        dialog.adjustSize()
        center = self.frameGeometry().center() - dialog.rect().center()
        dialog.move(center)
        dialog.show()
        self.check_dialog = dialog

    def _close_check_dialog(self):
        if self.check_dialog is None:
            return
        self.check_dialog.close()
        self.check_dialog.deleteLater()
        self.check_dialog = None

    def _show_update_info(self, title, message, detail="", retry=False, page_url="", manual=True):
        dialog = UpdateInfoDialog(
            title, message, detail=detail,
            primary_text=L.t("update.retry") if retry else L.t("update.close"),
            retry=retry,
            secondary_text=L.t("update.close") if retry else None,
            page_url=page_url,
            parent=self,
        )
        dialog.exec()
        if dialog.retry_requested:
            QTimer.singleShot(200, lambda: self.check_updates(manual=manual))

    def _on_update_checked(self, release, error):
        self._close_check_dialog()
        self.config["last_update_check"] = int(time.time())
        save_json(CONFIG_PATH, self.config)
        manual = self.manual_update_check
        self.manual_update_check = False

        if error:
            log.warning(f"Проверка обновлений не удалась: {error}")
            if manual:
                self._show_update_info(L.t("update.error_title"),
                                       L.t("update.check_failed", error=error),
                                       detail=L.t("update.check_hint"),
                                       retry=True, page_url=GITHUB_RELEASES_PAGE)
            return

        tag = str(release.get("tag_name") or "")
        if not tag or not is_newer_version(tag, VERSION):
            log.info(f"Обновлений нет (последняя: {tag or '?'}, текущая: {VERSION})")
            if manual:
                self._show_update_info(L.t("update.up_to_date_title"),
                                       L.t("update.up_to_date", version=VERSION),
                                       detail=L.t("update.current_version", version=VERSION),
                                       retry=True)
            return

        log.info(f"Доступно обновление: {tag}")
        self.latest_release = release
        self.latest_asset = pick_update_asset(release.get("assets") or [])
        self.update_chip.setText(L.t("update.chip", version=tag))
        self.update_chip.setVisible(True)
        if self.tray.isVisible():
            self.tray.showMessage(L.t("update.tray_title"),
                                  L.t("update.tray_msg", version=tag),
                                  QSystemTrayIcon.MessageIcon.Information, 5000)
        self._show_update_dialog(release, self.latest_asset)

    def _open_latest_update(self):
        if self.latest_release:
            self._show_update_dialog(self.latest_release, getattr(self, "latest_asset", None))

    def _show_update_dialog(self, release, asset=None):
        if self.update_dialog is not None and self.update_dialog.isVisible():
            self.update_dialog.raise_()
            return
        dialog = UpdateDialog(release, asset, self)
        dialog.install_requested.connect(self._install_update)
        self.update_dialog = dialog
        dialog.exec()

    def _install_update(self, archive_path):
        archive = Path(archive_path)
        if not archive.exists():
            QMessageBox.critical(self, L.t("update.title"),
                                 L.t("update.download_error", error=str(archive)))
            return
        if not getattr(sys, "frozen", False):
            self._open_path(archive.parent)
            QMessageBox.information(self, L.t("update.title"),
                                    L.t("update.source_mode", path=str(archive)))
            return
        if os.name != "nt":
            self._open_path(archive)
            page = (self.latest_release or {}).get("html_url") or GITHUB_RELEASES_PAGE
            webbrowser.open(page)
            return
        try:
            script = self._prepare_windows_update(archive)
            flags = 0
            for flag in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
                flags |= getattr(subprocess, flag, 0)
            subprocess.Popen(["cmd", "/c", str(script)], creationflags=flags, close_fds=True)
            log.info(f"Установка обновления запущена: {script}")
            self.tray.hide()
            self.hide()
            QTimer.singleShot(400, QApplication.quit)
        except Exception as e:
            log.exception("Не удалось запустить установку обновления")
            QMessageBox.critical(self, L.t("update.title"),
                                 L.t("update.apply_error", error=str(e)))

    def _prepare_windows_update(self, archive: Path) -> Path:
        """Extracts the downloaded build, then writes a script that swaps files
        after the launcher exits and restarts it."""
        staging = UPDATES_DIR / "staging"
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)

        exe_name = Path(sys.executable).name
        if archive.suffix.lower() == ".zip":
            with zipfile.ZipFile(archive) as zf:
                root = staging.resolve()
                for info in zf.infolist():
                    target = (staging / info.filename).resolve()
                    if not str(target).startswith(str(root)):
                        log.warning(f"Пропущен подозрительный путь в архиве: {info.filename}")
                        continue
                    zf.extract(info, staging)
        elif archive.suffix.lower() in (".exe", ".msi"):
            shutil.copy2(archive, staging / exe_name)
        else:
            raise ValueError(f"Unsupported update package: {archive.suffix}")

        payload_exe = None
        for candidate in (staging / exe_name, staging / "Devers Launcher.exe"):
            if candidate.exists():
                payload_exe = candidate
                break
        if payload_exe is None:
            found = detect_executable(staging)
            if found:
                payload_exe = Path(found)
        if payload_exe is None:
            raise FileNotFoundError("Launcher executable not found in update package")

        source_dir = payload_exe.parent
        target_exe = BASE_DIR / payload_exe.name
        bat = UPDATES_DIR / "apply_update.bat"
        content = (
            "@echo off\r\n"
            "setlocal\r\n"
            f'powershell -NoProfile -WindowStyle Hidden -Command "Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue"\r\n'
            f'xcopy "{source_dir}\\*" "{BASE_DIR}\\" /E /Y /I >NUL\r\n'
            f'start "" "{target_exe}"\r\n'
            f'rmdir /S /Q "{staging}"\r\n'
            'del "%~f0"\r\n'
        )
        try:
            with open(bat, "w", encoding="mbcs", errors="replace", newline="") as f:
                f.write(content)
        except LookupError:
            with open(bat, "w", encoding="cp1251", errors="replace", newline="") as f:
                f.write(content)
        log.info(f"Скрипт обновления: {bat}")
        return bat

    def _open_path(self, path):
        p = str(path)
        if os.name == 'nt':
            os.startfile(p)  # type: ignore[attr-defined]
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', p])
        else:
            subprocess.Popen(['xdg-open', p])

    def open_settings(self):
        d = SettingsDialog(self.config, self)
        d.settings_applied.connect(self._on_settings)
        d.check_updates_requested.connect(lambda: QTimer.singleShot(500, lambda: self.check_updates(manual=True)))
        d.exec()

    def _on_settings(self, new_conf):
        old_lang = self.config.get("language", "en")
        self.config = new_conf
        new_lang = self.config.get("language", "en")

        if old_lang != new_lang:
            log.info(f"Смена языка: {old_lang} → {new_lang}. Перезапуск интерфейса.")
            QTimer.singleShot(100, self._restart_with_new_language)
        else:
            self.library_page.config = new_conf
            self.fav_page.config = new_conf
            ANIM.configure(self.config)
            self.scan_library()
            self._update_bottom()
            QTimer.singleShot(800, self._auto_steam_sync)

    def _restart_with_new_language(self):
        L.set_language(self.config.get("language", "en"))
        self.tray.hide()
        self.close()
        global _new_window
        _new_window = LauncherWindow()
        _new_window.show()
        QTimer.singleShot(50, lambda: self._close_old())

    def _close_old(self):
        try:
            self.hide()
            self.deleteLater()
        except Exception:
            pass

    def open_about(self):
        dialog = AboutDialog(self)
        dialog.exec()
        if dialog.check_requested:
            QTimer.singleShot(200, lambda: self.check_updates(manual=True))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        if paths:
            event.acceptProposedAction()
            self._add_paths(paths)


_new_window = None


if __name__ == "__main__":
    ensure_default_localization()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    cfg = load_json(CONFIG_PATH, DEFAULT_CONFIG)

    needs_save = False
    if not cfg.get("games_dir") or cfg["games_dir"] in ("games", "games/", ".\\games"):
        cfg["games_dir"] = str(GAMES_DIR)
        needs_save = True
    if not cfg.get("temp_dir") or "DeversGames" in str(cfg["temp_dir"]):
        cfg["temp_dir"] = str(CACHE_DIR)
        needs_save = True
    if needs_save:
        save_json(CONFIG_PATH, cfg)

    L.load_available()
    L.set_language(cfg.get("language", "en"))

    app.setWindowIcon(build_app_icon())

    w = LauncherWindow()
    w.show()
    log.info(f"Devers Launcher v{VERSION} запущен")
    sys.exit(app.exec())
