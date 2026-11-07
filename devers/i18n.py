"""Localization: default English strings and the shared manager."""

import json
import logging

from .paths import LOCALIZATION_DIR, VERSION

log = logging.getLogger("Devers")

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
    "sidebar.studio": "Studio",
    "sidebar.web": "Web",
    "sidebar.command": "Commands",
    "sidebar.about": "About",
    "sidebar.settings": "Settings",
    "sidebar.collapse": "Collapse / Expand",

    "home.eyebrow": "Made by One Studio",
    "home.continue": "Continue playing",
    "home.now_playing": "Now playing",
    "home.recent": "Recently played",
    "home.recent_empty": "Games you launch will show up here.",
    "home.stats.games": "Games",
    "home.stats.playtime": "Playtime",
    "home.stats.favorites": "Favorites",
    "home.stats.disk": "On disk",
    "home.empty.title": "Your library is empty",
    "home.empty.hint": "Add a .dvp, .zip or .exe — or pull in your Steam library.",
    "home.quick.add": "Add game",
    "home.quick.folder": "Add folder",
    "home.quick.steam": "Steam",
    "home.quick.studio": "Studio",
    "home.quick.web": "Web",
    "home.featured": "Featured",
    "home.details": "Details",
    "home.see_all": "All games",
    "home.add_first": "Add first game",
    "home.launches": "{count} launches",
    "home.last_played": "Last played {when}",
    "home.never": "Never played",
    "home.session": "Playing for {time}",

    "studio.title": "Studio",
    "studio.eyebrow": "Made by One Studio",
    "studio.tagline": "Small studio making clean, focused tools for gamers and developers.",
    "studio.products": "Products",
    "studio.release": "Release",
    "studio.license": "License",
    "studio.open_site": "Open website",
    "studio.github": "GitHub",
    "studio.site": "Studio website",
    "studio.loading": "Loading made-by-one.github.io…",
    "studio.offline": "The website could not be loaded. Open it in your browser instead.",
    "studio.news": "Latest from the studio",
    "studio.products_title": "Projects",
    "studio.about_eyebrow": "About the studio",
    "studio.about_title": "Small studio. Clear tools.",
    "studio.about": "Made by One is a small studio building clean, minimal tools for gamers and developers. Everything we ship is designed to feel light, private and honest — no telemetry, no bloated installers, no hidden services running in the background.",
    "studio.chip.opensource": "Open source",
    "studio.chip.mit": "MIT license",
    "studio.chip.windows": "Windows-first",
    "studio.chip.telemetry": "No telemetry",
    "studio.latest_release": "Latest release",
    "studio.current": "Current release",
    "studio.release_page": "Release notes",
    "studio.links": "Links",

    "library.filter.all": "All",
    "library.filter.steam": "Steam",
    "library.filter.local": "Local",

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
    "library.more": "More actions",
    "library.added": "Added games: {count}",

    "card.error": "ERROR",
    "card.no_cover": "NO COVER",
    "card.play": "Play",
    "card.favorite": "Add to favorites",
    "card.unfavorite": "Remove from favorites",
    "card.details": "Game info",

    "menu.play": "Play",
    "menu.details": "Game info",
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

    "gameinfo.title": "Game info",
    "gameinfo.playtime": "Playtime",
    "gameinfo.launches": "Launches",
    "gameinfo.size": "Size",
    "gameinfo.type": "Type",
    "gameinfo.path": "Path",
    "gameinfo.none": "—",

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
    "launch.stop": "Stop",
    "launch.stop_game": "Stop game",
    "launch.stop_title": "Stop game",
    "launch.stop_confirm": "Stop «{name}»? Unsaved progress may be lost.",
    "launch.stopping": "Stopping «{name}»...",
    "launch.stopped": "«{name}» stopped.",
    "launch.not_running": "This game is not running.",
    "launch.session_lost": "Game session ended.",

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
    "settings.section.design": "DESIGN",
    "settings.hover_effects": "Enable hover effects on game cards",
    "settings.grid_backdrop": "Show the technical grid backdrop",
    "settings.compact_cards": "Use compact game cards",
    "settings.design_hint": "Applied instantly across pages, cards and dialogs.",
    "settings.section.web": "IN-APP BROWSER",
    "settings.web_in_app": "Open links inside the launcher",
    "settings.web_cache": "Keep browser cache and cookies",
    "settings.web_home": "Start page:",
    "settings.web_hint": "Powered by QtWebEngine. Disable the in-app browser to send links to your default browser instead.",
    "settings.clear_web_cache": "Clear browser cache",
    "settings.web_cache_cleared": "Browser cache cleared.",
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

    # --- in-app web browser -------------------------------------------------
    "web.title": "Devers Web",
    "web.back": "Back",
    "web.forward": "Forward",
    "web.reload": "Reload",
    "web.stop": "Stop",
    "web.home": "Start page",
    "web.external": "Open in browser",
    "web.bookmark": "Add bookmark",
    "web.unbookmark": "Remove bookmark",
    "web.url_placeholder": "Search or enter an address",
    "web.status.start": "START",
    "web.status.secure": "SECURE",
    "web.status.insecure": "INSECURE",
    "web.loading": "LOADING THE IN-APP BROWSER…",
    "web.error_title": "This page could not be loaded",
    "web.error_hint": "Check the address or your connection, then try again.",
    "web.retry": "Try again",
    "web.offline_title": "In-app browser is unavailable",
    "web.offline_hint": "QtWebEngine was not found. Links will open in your default browser instead.",
    "web.go": "Open",
    "web.menu": "Browser menu",
    "web.copy_url": "Copy address",
    "web.zoom": "Zoom: {percent}%",
    "web.zoom_in": "Zoom in",
    "web.zoom_out": "Zoom out",
    "web.zoom_reset": "Reset zoom",
    "web.clear_cache": "Clear browser cache",
    "web.cache_cleared": "Browser cache cleared",
    "web.copied": "Address copied",
    "web.download.started": "Downloading {name}…",
    "web.download.done": "Downloaded {name}",
    "web.download.error": "Download failed: {error}",
    "web.start.none": "Nothing here yet.",
    "web.start.status": "IN-APP BROWSER",
    "web.start.eyebrow": "MADE BY ONE STUDIO",
    "web.start.hero": "THE WEB, WITHOUT LEAVING THE LAUNCHER.",
    "web.start.sub": "Search, browse and open release pages inside Devers. Use the address bar above for any site, or start with a quick link.",
    "web.start.placeholder": "Search the web or enter an address",
    "web.start.search": "SEARCH",
    "web.start.quick": "QUICK LINKS",
    "web.start.recent": "RECENT",
    "web.start.bookmarks": "BOOKMARKS",
    "web.start.links_inside": "LINKS OPEN INSIDE DEVERS",
    "web.start.footer": "DEVERS LAUNCHER V{version} · MONOCHROME EDITION",
    "web.quick.studio.title": "Studio website",
    "web.quick.studio.desc": "The official Made by One site.",
    "web.quick.github.title": "GitHub profile",
    "web.quick.github.desc": "Projects, source code and experiments.",
    "web.quick.releases.title": "Release notes",
    "web.quick.releases.desc": "Every Devers Launcher release.",
    "web.quick.steam.title": "Steam store",
    "web.quick.steam.desc": "Browse the Steam catalogue.",
    "web.quick.packer.title": "Devers Packer",
    "web.quick.packer.desc": "Packer for .dvp game archives.",
    "web.quick.repo.title": "GitHub repository",
    "web.quick.repo.desc": "Star, fork or open an issue.",
    "web.install": "Install embedded browser",
    "web.install_hint": "The embedded browser needs the PyQt6-WebEngine package for this Python. Install it once — the launcher will restart afterwards.",
    "web.install_unavailable": "This build cannot install the browser automatically. Use your system browser, or install PyQt6-WebEngine for the launcher's Python.",
    "web.installing": "Installing PyQt6-WebEngine…",
    "web.install_done": "The embedded browser is installed. Restart the launcher to use it.",
    "web.install_failed": "Installation failed: {error}",
    "web.restart": "Restart launcher",
    "web.restart_hint": "The launcher will close and open again.",
    "web.install_python": "Python {version}",

    # --- command palette ----------------------------------------------------
    "command.placeholder": "Type a command or search…",
    "command.hint": "↑↓ NAVIGATE   ·   ↵ OPEN   ·   ESC CLOSE",
    "command.hint_short": "Command palette (Ctrl+K)",
    "command.empty": "No matches",
    "command.category.navigate": "NAVIGATE",
    "command.category.games": "GAMES",
    "command.category.actions": "ACTIONS",

    # --- toasts -------------------------------------------------------------
    "toast.settings_saved": "Settings saved",
    "toast.language": "Restarting to apply the new language…",
    "toast.refreshed": "Library refreshed",
    "toast.copied": "Copied",
    "toast.bookmark_added": "Bookmark added",
    "toast.bookmark_removed": "Bookmark removed",
    "toast.update_available": "Update {version} is available",

    # --- game page ----------------------------------------------------------
    "game.eyebrow": "Game",
    "game.close_tab": "Close game tab (Ctrl+W)",
    "game.back": "Back",
    "game.play": "Play",
    "game.about": "About",
    "game.details": "Details",
    "game.playtime": "Playtime",
    "game.launches": "Launches",
    "game.last_played": "Last played",
    "game.achievements": "Achievements",
    "game.screenshots": "Screenshots",
    "game.videos": "Videos",
    "game.developer_media": "From developer",
    "game.user_screenshots": "My screenshots",
    "game.user_clips": "My clips",
    "game.size": "Size",
    "game.type": "Type",
    "game.path": "Path",
    "game.release": "Release",
    "game.developer": "Developer",
    "game.publisher": "Publisher",
    "game.genres": "Genres",
    "game.metacritic": "Metacritic",
    "game.open_store": "Open store page",
    "game.steam_loading": "STEAM DATA · LOADING",
    "game.steam_error": "STEAM DATA · UNAVAILABLE",
    "game.no_description": "No description is available for this game yet.",
    "game.no_achievements": "No achievements were found for this game.",
    "game.no_screenshots": "No screenshots were found for this game.",
    "game.no_videos": "No videos were found for this game.",
    "game.no_time": "Never played",
    "game.never": "Never",
    "game.achievements_count": "{count} achievements",
    "game.completion": "Average global completion {value}%",
    "game.show_all": "Show all ({count})",
    "game.show_less": "Show less",
    "game.showing_count": "Showing {shown} of {total} achievements.",
    "game.hidden_achievement": "Hidden achievement",

    "media.title": "Media viewer",
    "media.screenshot": "Screenshot",
    "media.video": "Video",
    "media.counter": "{current} / {total}",
    "media.screenshot_number": "Screenshot {number}",
    "media.open": "Open in system viewer",
    "media.close": "Close (Esc)",
    "media.prev": "Previous (←)",
    "media.next": "Next (→)",
    "media.loading": "LOADING…",
    "media.error": "This image could not be loaded.",
    "media.video_error": "This video cannot be played here. Open it in the system player.",
    "media.video_unavailable": "Video playback is not available in this build. Open the video externally.",
    "media.play": "Play",
    "media.pause": "Pause",
    "media.mute": "Mute",
    "media.unmute": "Unmute",

    "bottom.temp": "Temp files: {size}",
    "bottom.stats": "{games} games  •  {steam} from Steam",
    "bottom.version": f"Devers Launcher v{VERSION}",
}


def ensure_default_localization() -> None:
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
                self.fallback = {**EN_DEFAULT, **json.load(f)}
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
            value = EN_DEFAULT.get(key)
        if value is None:
            value = key
        if kwargs:
            try:
                value = value.format(**kwargs)
            except Exception:
                pass
        return value


L = LocalizationManager()
