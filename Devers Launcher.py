VERSION = "1.2"

import sys
import os
import json
import zipfile
import shutil
import subprocess
import tempfile
import time
import logging
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QFrame,
                             QMessageBox, QProgressBar, QScrollArea, QDialog, 
                             QLineEdit, QDialogButtonBox, QCheckBox,
                             QFileDialog, QMenu, QSystemTrayIcon, QComboBox,
                             QGraphicsOpacityEffect, QSizePolicy, QGridLayout,
                             QInputDialog)
from PyQt6.QtCore import (Qt, QThread, pyqtSignal, QTimer, QSize, QPropertyAnimation, 
                          QEasingCurve, QParallelAnimationGroup, QRunnable, QThreadPool,
                          QObject, QPoint)
from PyQt6.QtGui import (QMovie, QPixmap, QIcon, QAction, QKeySequence, QShortcut,
                         QPainter, QColor, QBrush, QFont, QImage, QPainterPath)


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

CONFIG_FILE       = SAVE_DIR / "devers_config.json"
CACHE_FILE        = SAVE_DIR / "cache.json"
STATS_FILE        = SAVE_DIR / "stats.json"
LOG_FILE          = SAVE_DIR / "launcher.log"

GIF_PATH          = ICON_DIR / "devers_gif.gif"
APP_ICON          = ICON_DIR / "app.ico"
ICONS_DIR         = ICON_DIR 

CONFIG_PATH      = str(CONFIG_FILE)
CACHE_PATH       = str(CACHE_FILE)
STATS_PATH       = str(STATS_FILE)
LOG_PATH         = str(LOG_FILE)
GIF_PATH_S       = str(GIF_PATH)
APP_ICON_S       = str(APP_ICON)
ICONS_DIR_S      = str(ICONS_DIR)
LOCALIZATION_DIR_S = str(LOCALIZATION_DIR)


def ensure_dirs() -> None:
    """Создаёт всю структуру data/ при старте."""
    for d in (DATA_DIR, LOCALIZATION_DIR, ICON_DIR,
              GAMES_DIR, SAVE_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)


def migrate_legacy() -> None:
    """Переносит файлы из старой структуры (всё в корне) в data/."""
    legacy_files = {
        BASE_DIR / "devers_config.json": CONFIG_FILE,
        BASE_DIR / "cache.json":         CACHE_FILE,
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
    "language": "en"
}


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
    "app.description": "Light game launcher for .dvp format.\nExtracts and runs games right from the launcher,\nwithout leaving any junk on your disk.",
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
    "library.empty": "Library is empty.\nDrag .dvp files into the window or place them into 'data/games' folder.",
    "library.found": "Found games: {count}",
    "library.not_played": "not played yet",

    "card.error": "ERROR",
    "card.no_cover": "NO COVER",
    "card.play": "Play",
    "card.favorite": "Add to favorites",
    "card.unfavorite": "Remove from favorites",

    "menu.play": "Play",
    "menu.favorite_add": "Add to favorites",
    "menu.favorite_remove": "Remove from favorites",
    "menu.open_folder": "Open game folder",
    "menu.rename": "Rename",
    "menu.delete": "Delete",
    "menu.separator": "",

    "dialog.rename.title": "Rename",
    "dialog.rename.prompt": "New name:",
    "dialog.delete.title": "Delete",
    "dialog.delete.confirm": "Delete '{name}'?",
    "dialog.delete.error": "Failed to delete: {error}",

    "launch.extracting": "Extracting «{name}»...",
    "launch.extract_error": "Extraction error",
    "launch.exe_missing": "File '{exe}' not found in archive",
    "launch.start_error": "Launch error",
    "launch.already_running": "Another game is already running!",
    "launch.playing": "▶  {name} launched (PID {pid})",
    "launch.closed": "Game closed. Cleaning up...",
    "launch.cleaned": "Cleaned",
    "launch.corrupted": "Game is corrupted:\n{error}",

    "settings.title": "Settings",
    "settings.subtitle": "Manage storage and launcher behavior",
    "settings.section.storage": "STORAGE",
    "settings.section.temp": "TEMPORARY FILES",
    "settings.section.interface": "INTERFACE",
    "settings.section.language": "LANGUAGE",
    "settings.games_dir": "Games folder:",
    "settings.temp_info": "Folder: {path}\nUsed: {size}",
    "settings.open_folder": "Open folder",
    "settings.clear_now": "Clear now",
    "settings.auto_cleanup": "Automatically clean temp files",
    "settings.show_ext": "Show file extensions",
    "settings.start_collapsed": "Start with collapsed sidebar",
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
    "about.description": "Light game launcher for .dvp format.\n\nDeveloped by Made by One Studio.\nPacks, extracts and runs games,\nwithout leaving any junk on your disk.",
    "about.close": "Close",

    "tray.show": "Show",
    "tray.quit": "Quit",
    "tray.minimized_title": "Devers Launcher",
    "tray.minimized_msg": "Minimized to tray",

    "bottom.temp": "Temp files: {size}",
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
    finished = pyqtSignal(dict)

    def __init__(self, games_dir, cache):
        super().__init__()
        self.games_dir = games_dir
        self.cache = cache

    def run(self):
        manifests = {}
        try:
            files = [f for f in os.listdir(self.games_dir) if f.endswith(".dvp")]
        except Exception as e:
            log.error(f"Не могу прочитать папку игр: {e}")
            self.finished.emit({})
            return

        for f in files:
            p = os.path.join(self.games_dir, f)
            try:
                mtime = os.path.getmtime(p)
                size = os.path.getsize(p)
            except:
                continue

            cached = self.cache.get(f, {})
            if cached.get("mtime") == mtime and cached.get("size") == size:
                manifests[f] = cached
                continue

            entry = {
                "mtime": mtime, "size": size, "path": p,
                "name": f.replace(".dvp", ""), "exe": "unknown",
                "created": "", "cover_data": None, "cover_ext": ".png", "error": None
            }
            try:
                with zipfile.ZipFile(p, 'r') as zf:
                    if "manifest.json" in zf.namelist():
                        mf = json.loads(zf.read("manifest.json").decode("utf-8"))
                        entry["name"] = mf.get("name", entry["name"])
                        entry["exe"] = mf.get("exe", "unknown")
                        entry["created"] = mf.get("created", "")
                        entry["cover_data"] = mf.get("cover_data")
                        entry["cover_ext"] = mf.get("cover_ext", ".png")
                    else:
                        entry["error"] = "manifest.json missing"
            except zipfile.BadZipFile:
                entry["error"] = "Corrupted .dvp"
            except Exception as e:
                entry["error"] = f"Read error: {e}"

            manifests[f] = entry
        self.finished.emit(manifests)


class CoverLoader(QRunnable):
    class Signals(QObject):
        loaded = pyqtSignal(str, QPixmap)

    def __init__(self, key, hex_data):
        super().__init__()
        self.key = key
        self.hex_data = hex_data
        self.signals = CoverLoader.Signals()

    def run(self):
        try:
            data = bytes.fromhex(self.hex_data)
            pm = QPixmap()
            pm.loadFromData(data)
            self.signals.loaded.emit(self.key, pm)
        except Exception as e:
            log.warning(f"Обложка не загрузилась: {e}")
            self.signals.loaded.emit(self.key, QPixmap())


CARD_WIDTH = 240
CARD_HEIGHT = 300
COVER_HEIGHT = 175


class GameCard(QFrame):
    play_requested = pyqtSignal(str)
    context_menu_requested = pyqtSignal(str, QPoint)
    favorite_toggled = pyqtSignal(str)

    def __init__(self, key, meta, is_favorite=False, show_ext=False, play_time=0):
        super().__init__()
        self.key = key
        self.meta = meta
        self.setObjectName("GameCard")
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
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
        elif meta.get("cover_data"):
            QThreadPool.globalInstance().start(self._make_cover_loader(meta["cover_data"]))

        outer.addWidget(self.cover)

        info_wrap = QWidget()
        info_wrap.setStyleSheet(
            "background-color: #0D0D0D; "
            "border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;"
        )
        info = QVBoxLayout(info_wrap)
        info.setContentsMargins(14, 10, 14, 12)
        info.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self.name_label = QLabel(meta.get("name", "Unknown"))
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

        info.addLayout(top_row)

        size_display = human_size(meta.get("size", 0))
        time_display = human_time(play_time) if play_time else L.t("library.not_played")

        stats = QLabel(f"{size_display}  •  {time_display}")
        stats.setStyleSheet("color: #666666; font-size: 10px; background: transparent;")
        info.addWidget(stats)

        info.addStretch()

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        self.progress.setFixedHeight(14)
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

    def _make_cover_loader(self, hex_data):
        loader = CoverLoader(self.key, hex_data)
        loader.signals.loaded.connect(self._on_cover_loaded)
        return loader

    def _on_cover_loaded(self, key, pixmap):
        if key == self.key and not pixmap.isNull():
            self.cover.set_rounded_pixmap(pixmap)
            self.cover.setText("")

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

        a1 = QPropertyAnimation(self, b"minimumWidth")
        a1.setDuration(260); a1.setStartValue(self.width()); a1.setEndValue(target)
        a1.setEasingCurve(QEasingCurve.Type.InOutCubic)
        a2 = QPropertyAnimation(self, b"maximumWidth")
        a2.setDuration(260); a2.setStartValue(self.width()); a2.setEndValue(target)
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


class SettingsDialog(QDialog):
    settings_applied = pyqtSignal(dict)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config.copy()
        self.setWindowTitle(L.t("settings.title"))
        self.setWindowIcon(QApplication.windowIcon())
        self.resize(580, 560)
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
            QPushButton#Danger { background-color: #1A1A1A; color: #FF6B6B; border: 1px solid #3A1A1A; }
            QPushButton#Danger:hover { background-color: #3A1A1A; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 30, 35, 30)
        layout.setSpacing(12)

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
        b = QPushButton("..."); b.setObjectName("Secondary"); b.setFixedWidth(45)
        b.clicked.connect(self._browse)
        games_row.addWidget(self.games_input); games_row.addWidget(b)
        row = QHBoxLayout(); lbl = QLabel(L.t("settings.games_dir")); lbl.setFixedWidth(150)
        row.addWidget(lbl); row.addLayout(games_row); layout.addLayout(row)

        layout.addSpacing(10)
        sec2 = QLabel(L.t("settings.section.temp")); sec2.setObjectName("SectionTitle"); layout.addWidget(sec2)

        self.temp_label = QLabel(""); self.temp_label.setStyleSheet("color: #888888; font-size: 12px;")
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
        r = QPushButton(L.t("settings.reset")); r.setObjectName("Secondary"); r.clicked.connect(self._reset)
        c2 = QPushButton(L.t("settings.cancel")); c2.setObjectName("Secondary"); c2.clicked.connect(self.reject)
        s = QPushButton(L.t("settings.save")); s.clicked.connect(self._save)
        btns.addWidget(r); btns.addStretch(); btns.addWidget(c2); btns.addWidget(s)
        layout.addLayout(btns)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, L.t("settings.games_dir"))
        if d: self.games_input.setText(d)

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
            for i in range(self.lang_combo.count()):
                if self.lang_combo.itemData(i) == "en":
                    self.lang_combo.setCurrentIndex(i)
                    break

    def _save(self):
        self.config["games_dir"] = self.games_input.text()
        self.config["auto_cleanup"] = self.auto_cleanup.isChecked()
        self.config["show_extensions"] = self.show_ext.isChecked()
        self.config["sidebar_collapsed"] = self.start_collapsed.isChecked()
        self.config["language"] = self.lang_combo.currentData()
        save_json(CONFIG_PATH, self.config)
        self.settings_applied.emit(self.config)
        self.accept()


class AboutDialog(QDialog):
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
        """)
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

        ok = QPushButton(L.t("about.close"))
        ok.clicked.connect(self.accept)
        l.addWidget(ok, alignment=Qt.AlignmentFlag.AlignCenter)


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

    def __init__(self, config, favorites_getter, play_times_getter, page_title):
        super().__init__()
        self.config = config
        self.favorites_getter = favorites_getter
        self.play_times_getter = play_times_getter
        self.current_manifests = {}
        self.card_widgets = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 35, 40, 35)
        layout.setSpacing(15)

        header = QHBoxLayout()
        title = QLabel(page_title)
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch()

        self.search = QLineEdit()
        self.search.setPlaceholderText(L.t("library.search_placeholder"))
        self.search.setFixedWidth(240)
        self.search.setStyleSheet("""
            QLineEdit {
                background-color: #0F0F0F; color: #FFFFFF;
                border: 1px solid #1A1A1A; border-radius: 8px;
                padding: 8px 14px; font-size: 12px;
            }
            QLineEdit:focus { border: 1px solid #333333; }
        """)
        search_icon = get_icon("search", 16)
        if search_icon:
            self.search.addAction(search_icon, QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(lambda: self.render(self.current_manifests))
        header.addWidget(self.search)

        self.sort_combo = QComboBox()
        self.sort_combo.addItem(L.t("library.sort.name"))
        self.sort_combo.addItem(L.t("library.sort.size"))
        self.sort_combo.addItem(L.t("library.sort.date"))
        self.sort_combo.addItem(L.t("library.sort.time"))
        self.sort_combo.addItem(L.t("library.sort.favorites"))
        self.sort_combo.setStyleSheet("""
            QComboBox {
                background-color: #0F0F0F; color: #CCCCCC;
                border: 1px solid #1A1A1A; border-radius: 8px;
                padding: 8px 14px; font-size: 12px;
            }
            QComboBox::drop-down { border: none; width: 20px; }
        """)
        self.sort_combo.currentIndexChanged.connect(lambda: self.render(self.current_manifests))
        header.addWidget(self.sort_combo)

        self.refresh_btn = QPushButton()
        self.refresh_btn.setFixedSize(38, 38)
        self.refresh_btn.setToolTip(L.t("library.refresh"))
        refresh_icon = get_icon("refresh", 18)
        if refresh_icon:
            self.refresh_btn.setIcon(refresh_icon)
            self.refresh_btn.setIconSize(QSize(18, 18))
        else:
            self.refresh_btn.setText("↻")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #0F0F0F; color: #AAAAAA;
                border: 1px solid #1A1A1A; border-radius: 8px;
                font-size: 16px;
            }
            QPushButton:hover { background-color: #1A1A1A; color: #FFFFFF; }
        """)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #777777; font-size: 11px;")
        layout.addWidget(self.status)

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
        layout.addWidget(self.scroll)

    def show_skeleton(self):
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        for i in range(6):
            r, c = divmod(i, self._columns())
            self.grid.addWidget(SkeletonCard(), r, c)

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

        if not manifests:
            empty = QLabel(L.t("library.empty"))
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #333333; font-size: 13px; padding: 60px;")
            self.grid.addWidget(empty, 0, 0, 1, 3)
            self.status.setText("")
            return

        query = self.search.text().strip().lower()
        favorites = set(self.favorites_getter())
        play_times = self.play_times_getter()

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
        cols = self._columns()

        for i, (key, meta) in enumerate(items):
            r, c = divmod(i, cols)
            card = GameCard(key, meta, is_favorite=key in favorites,
                            show_ext=show_ext, play_time=play_times.get(key, 0))
            card.play_requested.connect(self.play_requested)
            card.context_menu_requested.connect(self.context_requested)
            card.favorite_toggled.connect(self.favorite_toggled)
            self.grid.addWidget(card, r, c)
            self.card_widgets[key] = card

        self.status.setText(L.t("library.found", count=len(items)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_manifests:
            QTimer.singleShot(50, lambda: self.render(self.current_manifests))

    def set_card_progress(self, key, visible, value=0):
        card = self.card_widgets.get(key)
        if card:
            card.progress.setVisible(visible)
            if visible:
                card.progress.setValue(value)


class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_json(CONFIG_PATH, DEFAULT_CONFIG)
        self.cache = load_json(CACHE_PATH, {})
        self.stats = load_json(STATS_PATH, {"play_times": {}})
        self.manifests = {}
        self.cover_pool = QThreadPool()
        self.scanner = None
        self.extract_worker = None
        self.active_process = None
        self.active_game_key = None
        self.game_start_time = None
        self.temp_dir = None
        self.current_page = None
        self._initialized = False

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

        self.home_page.setVisible(False)
        self.library_page.setVisible(False)
        self.fav_page.setVisible(False)

        QTimer.singleShot(50, self._post_show_init)

    def _post_show_init(self):
        self._initialized = True
        self.sidebar.switch("home")
        self.scan_library()

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

        self.home_page = HomePage()
        self.library_page = LibraryPage(
            self.config,
            favorites_getter=lambda: self.config.get("favorites", []),
            play_times_getter=lambda: self.stats.get("play_times", {}),
            page_title=L.t("library.title")
        )
        self.library_page.refresh_btn.clicked.connect(self.scan_library)
        self.library_page.play_requested.connect(self.play_by_key)
        self.library_page.context_requested.connect(self.show_context_menu)
        self.library_page.favorite_toggled.connect(self.toggle_favorite)

        self.fav_page = LibraryPage(
            self.config,
            favorites_getter=lambda: self.config.get("favorites", []),
            play_times_getter=lambda: self.stats.get("play_times", {}),
            page_title=L.t("sidebar.favorites")
        )
        self.fav_page.refresh_btn.clicked.connect(self.scan_library)
        self.fav_page.play_requested.connect(self.play_by_key)
        self.fav_page.context_requested.connect(self.show_context_menu)
        self.fav_page.favorite_toggled.connect(self.toggle_favorite)

        self.content_layout.addWidget(self.home_page)
        self.content_layout.addWidget(self.library_page)
        self.content_layout.addWidget(self.fav_page)

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
        bl.addStretch()
        self.bottom_right = QLabel("")
        self.bottom_right.setStyleSheet("color: #333333; font-size: 10px; letter-spacing: 0.5px;")
        bl.addWidget(self.bottom_right)
        root.addWidget(bottom)
        self._update_bottom()

        self.opacity_effect = QGraphicsOpacityEffect(self.content)
        self.content.setGraphicsEffect(self.opacity_effect)
        self.opacity_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.opacity_anim.setDuration(220)
        self.opacity_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

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
        quit_action = QAction(L.t("tray.quit"), self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(show_action)
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

    def switch_page(self, key, animate=True):
        pages = {"home": self.home_page, "library": self.library_page, "favorites": self.fav_page}
        target = pages.get(key)
        if not target:
            return
        if key == self.current_page and self._initialized:
            return

        self.current_page = key
        for k, p in pages.items():
            p.setVisible(k == key)

        for k, btn in self.sidebar.nav_buttons.items():
            if k in ("settings", "about"):
                continue
            want = (k == key)
            if btn.isChecked() != want:
                btn.blockSignals(True)
                btn.setChecked(want)
                btn.blockSignals(False)
                self.sidebar._render(btn, self.sidebar.is_collapsed)

        if animate and self._initialized:
            self.opacity_anim.stop()
            self.opacity_anim.setStartValue(0.0)
            self.opacity_anim.setEndValue(1.0)
            self.opacity_anim.start()

        if key in ("library", "favorites") and self._initialized:
            self.scan_library()

    def _update_bottom(self):
        t = self.config.get("temp_dir", str(CACHE_DIR))
        self.bottom_right.setText(L.t("bottom.temp", size=human_size(dir_size(t))))

    def scan_library(self):
        games_dir = self.config.get("games_dir", str(GAMES_DIR))
        os.makedirs(games_dir, exist_ok=True)
        self.library_page.show_skeleton()
        if self.current_page == "favorites":
            self.fav_page.show_skeleton()

        self.scanner = ManifestScanner(games_dir, self.cache)
        self.scanner.finished.connect(self._on_scan_done)
        self.scanner.start()

    def _on_scan_done(self, manifests):
        self.manifests = manifests
        save_json(CACHE_PATH, manifests)
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

        act_delete = QAction(L.t("menu.delete"), self)
        ic = get_icon_tinted("trash", 16, QColor(255, 107, 107))
        if ic: act_delete.setIcon(ic)
        menu.addAction(act_delete)

        action = menu.exec(global_pos)
        if action == act_play:
            self.play_by_key(key)
        elif action == act_fav:
            self.toggle_favorite(key)
        elif action == act_open:
            if os.name == 'nt':
                subprocess.Popen(['explorer', '/select,', self.manifests[key]["path"]])
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', '-R', self.manifests[key]["path"]])
            else:
                subprocess.Popen(['xdg-open', os.path.dirname(self.manifests[key]["path"])])
        elif action == act_rename:
            new_name, ok = QInputDialog.getText(self, L.t("dialog.rename.title"),
                                                L.t("dialog.rename.prompt"),
                                                text=self.manifests[key].get("name", ""))
            if ok and new_name:
                self.manifests[key]["name"] = new_name
                save_json(CACHE_PATH, self.manifests)
                self.library_page.render(self.manifests)
                self._render_favorites()
        elif action == act_delete:
            r = QMessageBox.question(self, L.t("dialog.delete.title"),
                                     L.t("dialog.delete.confirm", name=self.manifests[key].get("name")))
            if r == QMessageBox.StandardButton.Yes:
                try:
                    os.remove(self.manifests[key]["path"])
                    log.info(f"Удалена игра: {key}")
                    self.scan_library()
                except Exception as e:
                    QMessageBox.critical(self, L.t("dialog.delete.title"),
                                         L.t("dialog.delete.error", error=str(e)))

    def play_by_key(self, key):
        if key not in self.manifests:
            return
        if self.active_process and self.active_process.poll() is None:
            QMessageBox.warning(self, L.t("menu.play"), L.t("launch.already_running"))
            return
        meta = self.manifests[key]
        if meta.get("error"):
            QMessageBox.critical(self, L.t("card.error"),
                                 L.t("launch.corrupted", error=meta["error"]))
            return
        dvp_path = meta["path"]
        name = meta.get("name", "game")
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
        for root, _, files in os.walk(self.temp_dir):
            for f in files:
                if f.lower() == exe_name.lower():
                    exe_path = os.path.join(root, f); break
            if exe_path: break

        if not exe_path:
            msg = L.t("launch.exe_missing", exe=exe_name)
            log.error(msg)
            QMessageBox.critical(self, L.t("launch.start_error"), msg)
            self.library_page.status.setText(L.t("launch.exe_missing", exe=exe_name))
            return

        try:
            self.active_process = subprocess.Popen(
                [exe_path], cwd=os.path.dirname(exe_path), shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            self.game_start_time = time.time()
            self.library_page.status.setText(L.t("launch.playing", name=meta.get('name'),
                                                 pid=self.active_process.pid))
            log.info(f"Запуск: {meta.get('name')} (PID {self.active_process.pid})")
            QTimer.singleShot(2000, self._check_process)
        except Exception as e:
            log.exception("Ошибка запуска")
            QMessageBox.critical(self, L.t("launch.start_error"), str(e))

    def _check_process(self):
        if self.active_process is None:
            return
        if self.active_process.poll() is not None:
            duration = time.time() - self.game_start_time if self.game_start_time else 0
            key = self.active_game_key
            if key and duration > 5:
                times = self.stats.setdefault("play_times", {})
                times[key] = times.get(key, 0) + int(duration)
                save_json(STATS_PATH, self.stats)
                log.info(f"Игра {key} закрыта, время сессии: {int(duration)}с")

            self.library_page.status.setText(L.t("launch.closed"))
            if self.config.get("auto_cleanup", True) and self.temp_dir and os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir, ignore_errors=True)
                    self.library_page.status.setText(L.t("launch.cleaned"))
                except Exception as e:
                    log.warning(f"Не удалось очистить: {e}")
            self.active_process = None
            self.active_game_key = None
            self.game_start_time = None
            self._update_bottom()
            self.library_page.render(self.manifests)
            self._render_favorites()
        else:
            QTimer.singleShot(2000, self._check_process)

    def open_settings(self):
        d = SettingsDialog(self.config, self)
        d.settings_applied.connect(self._on_settings)
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
            self.scan_library()
            self._update_bottom()

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
        AboutDialog(self).exec()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        games_dir = self.config.get("games_dir", str(GAMES_DIR))
        os.makedirs(games_dir, exist_ok=True)
        added = 0
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p.lower().endswith(".dvp"):
                try:
                    dest = os.path.join(games_dir, os.path.basename(p))
                    shutil.copy(p, dest)
                    added += 1
                except Exception as e:
                    log.error(f"Не удалось скопировать {p}: {e}")
        if added:
            log.info(f"Добавлено игр: {added}")
            self.sidebar.switch("library")
            self.scan_library()


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