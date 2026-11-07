"""Filesystem layout, defaults and app-wide constants."""

import logging
import os
import shutil
import sys
from pathlib import Path

VERSION = "1.6"


def _is_writable(path: Path) -> bool:
    try:
        probe = path / ".devers_write_test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def get_base_dir() -> Path:
    """Корневая папка приложения (рядом с .exe или main.py).

    A packaged launcher may sit in a read-only folder (Program Files).  In
    that case user data goes to %LOCALAPPDATA% so the app still starts.
    """
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
        if _is_writable(root):
            return root
        fallback = Path(os.environ.get("LOCALAPPDATA") or Path.home()) \
            / "Devers Launcher"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
# PyInstaller extracts bundled read-only assets into ``_MEIPASS``.
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", "")) \
    if getattr(sys, "frozen", False) else None
DATA_DIR = BASE_DIR / "data"
LOCALIZATION_DIR = DATA_DIR / "localization"
ICON_DIR = DATA_DIR / "icon"
GAMES_DIR = DATA_DIR / "games"
SAVE_DIR = DATA_DIR / "save"
CACHE_DIR = SAVE_DIR / "cache"
COVERS_DIR = CACHE_DIR / "covers"
UPDATES_DIR = SAVE_DIR / "updates"
WEB_DIR = SAVE_DIR / "web"
WEB_CACHE_DIR = WEB_DIR / "cache"
WEB_STORAGE_DIR = WEB_DIR / "storage"
WEB_DOWNLOADS_DIR = WEB_DIR / "downloads"

CONFIG_FILE = SAVE_DIR / "devers_config.json"
CACHE_FILE = SAVE_DIR / "cache.json"
LIBRARY_FILE = SAVE_DIR / "library.json"
STATS_FILE = SAVE_DIR / "stats.json"
LOG_FILE = SAVE_DIR / "launcher.log"

GIF_PATH = ICON_DIR / "devers_gif.gif"
APP_ICON = ICON_DIR / "app.ico"

CONFIG_PATH = str(CONFIG_FILE)
CACHE_PATH = str(CACHE_FILE)
LIBRARY_PATH = str(LIBRARY_FILE)
STATS_PATH = str(STATS_FILE)
LOG_PATH = str(LOG_FILE)


def _copy_missing(source: Path, target: Path) -> None:
    if not source.is_dir():
        return
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            _copy_missing(item, destination)
        elif not destination.exists():
            try:
                shutil.copy2(item, destination)
            except OSError:
                pass


def sync_bundled_data() -> None:
    """Copies localization and icons shipped inside a PyInstaller build."""
    if BUNDLE_DIR is None:
        return
    bundled = BUNDLE_DIR / "data"
    if not bundled.is_dir():
        return
    _copy_missing(bundled / "localization", LOCALIZATION_DIR)
    _copy_missing(bundled / "icon", ICON_DIR)


def ensure_dirs() -> None:
    """Создаёт всю структуру data/ при старте."""
    for d in (DATA_DIR, LOCALIZATION_DIR, ICON_DIR,
              GAMES_DIR, SAVE_DIR, CACHE_DIR, COVERS_DIR, UPDATES_DIR,
              WEB_DIR, WEB_CACHE_DIR, WEB_STORAGE_DIR, WEB_DOWNLOADS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    sync_bundled_data()


def migrate_legacy() -> None:
    """Переносит файлы из старой структуры (всё в корне) в data/."""
    legacy_files = {
        BASE_DIR / "devers_config.json": CONFIG_FILE,
        BASE_DIR / "cache.json": CACHE_FILE,
        BASE_DIR / "library.json": LIBRARY_FILE,
        BASE_DIR / "stats.json": STATS_FILE,
        BASE_DIR / "launcher.log": LOG_FILE,
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


ARCHIVE_EXTENSIONS = (".dvp", ".zip")
DIRECT_EXTENSIONS = (".exe", ".bat", ".cmd", ".lnk", ".url")
SUPPORTED_EXTENSIONS = ARCHIVE_EXTENSIONS + DIRECT_EXTENSIONS

GITHUB_REPO = "Made-by-One/Devers-Launcher"
GITHUB_RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"
GITHUB_PROFILE = "https://github.com/Made-by-One"
GITHUB_USER_API = "https://api.github.com/users/Made-by-One/repos?per_page=20&sort=updated"
WEBSITE_URL = "https://made-by-one.github.io/"
WEB_SEARCH_URL = "https://duckduckgo.com/?q={query}"
STEAM_STORE_URL = "https://store.steampowered.com/app/{appid}/"
STEAM_COMMUNITY_URL = "https://steamcommunity.com/app/{appid}/"
UPDATE_CHECK_INTERVAL = 6 * 60 * 60
USER_AGENT = f"DeversLauncher/{VERSION}"

STEAM_CDN_HEADER = "https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"

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
    # --- web / design -------------------------------------------------------
    "web_in_app": True,
    "web_home": WEBSITE_URL,
    "web_cache": True,
    "web_zoom": 1.0,
    "web_bookmarks": [],
    "web_recent": [],
    "hover_effects": True,
    "grid_backdrop": True,
    "compact_cards": False,
    "search_debounce": 170,
}


def setup_logging() -> logging.Logger:
    ensure_dirs()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger = logging.getLogger("Devers")
    logger.info(f"=== Devers Launcher v{VERSION} ===")
    logger.info(f"BASE_DIR: {BASE_DIR}")
    logger.info(f"DATA_DIR: {DATA_DIR}")
    return logger


def open_path(path) -> None:
    """Opens a file/folder with the OS default handler."""
    target = str(path)
    if os.name == "nt":
        os.startfile(target)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        import subprocess
        subprocess.Popen(["open", target])
    else:
        import subprocess
        subprocess.Popen(["xdg-open", target])
