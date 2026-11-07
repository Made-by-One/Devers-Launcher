"""Main launcher window: navigation, library state, launching and updates."""

import hashlib
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser
import zipfile
from pathlib import Path

from PyQt6.QtCore import (QEasingCurve, QParallelAnimationGroup, QPoint,
                          QPropertyAnimation, QSize, Qt, QThreadPool, QTimer)
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QApplication, QFileDialog, QFrame,
                             QGraphicsOpacityEffect, QHBoxLayout, QInputDialog,
                             QLabel, QMainWindow, QMenu, QMessageBox,
                             QPushButton, QStackedWidget, QSystemTrayIcon,
                             QTabBar, QVBoxLayout, QWidget)

from .covers import clear_cover_cache, cover_cache_stats  # noqa: F401 (re-export)
from .dialogs.about import AboutDialog
from .dialogs.settings import SettingsDialog
from .dialogs.steam_import import SteamImportDialog, SteamScanThread
from .games import (ExtractWorker, ManifestScanner, detect_executable)
from .i18n import L
from .pages.game import GameDetailPage
from .pages.home import HomePage
from .pages.library import LibraryPage
from .pages.studio import StudioPage
from .paths import (APP_ICON, BASE_DIR, CACHE_DIR, CACHE_PATH, CONFIG_PATH,
                    DEFAULT_CONFIG, GAMES_DIR, GITHUB_PROFILE,
                    GITHUB_RELEASES_PAGE, LIBRARY_PATH, STATS_PATH,
                    SUPPORTED_EXTENSIONS, UPDATES_DIR, VERSION, WEBSITE_URL,
                    open_path)
from .steam import (LAUNCH_NOISE, find_steam_path, game_exe_names,
                    launch_steam_game, pids_for_names, resolve_shortcut_target,
                    snapshot_pids, terminate_pids)
from .theme import (ANIM, BLACK, LINE, SURFACE_2, TEXT_DIM, TEXT_MUTED, UI,
                    WHITE, app_stylesheet, menu_stylesheet)
from .updates import (UpdateCheckDialog, UpdateCheckThread, UpdateDialog,
                      UpdateInfoDialog, is_newer_version, pick_update_asset)
from .utils import (build_app_icon, dir_size_cached, human_size, load_json,
                    save_json)
from .web import BrowserPage, set_url_handler
from .widgets.sidebar import CollapsibleSidebar
from .widgets.toast import ToastManager

log = logging.getLogger("Devers")

STEAM_UPDATE_CHECK_INTERVAL = 6 * 60 * 60


class GameTabBar(QTabBar):
    """Tab bar that keeps tabs readable and scrolls instead of squeezing."""

    MIN_TAB_WIDTH = 150
    MAX_TAB_WIDTH = 240

    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        width = max(self.MIN_TAB_WIDTH, min(size.width(), self.MAX_TAB_WIDTH))
        return QSize(width, max(34, size.height()))


class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_json(CONFIG_PATH, DEFAULT_CONFIG)
        self.cache = load_json(CACHE_PATH, {})
        self.external = load_json(LIBRARY_PATH, {})
        self.stats = load_json(STATS_PATH, {"play_times": {}, "launch_counts": {}, "last_played": {}})
        self.stats.setdefault("play_times", {})
        self.stats.setdefault("launch_counts", {})
        self.stats.setdefault("last_played", {})
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
        self._session_names = []
        self._session_pids = []
        self._session_seen = False
        self._session_missing = 0
        self._session_grace_until = 0.0
        self._session_stopping = False
        self.temp_dir = None
        self.current_page = None
        self.game_pages = {}
        self._game_return_page = "library"
        self._game_tab_guard = False
        self._initialized = False
        self._shown_once = False
        self._page_animations = None
        self._studio_news = ""
        self.web_page = None
        self.command_palette = None
        self.toasts = None

        ANIM.configure(self.config)
        UI.configure(self.config)

        self.setWindowTitle(L.t("app.title"))
        self.setWindowIcon(QApplication.windowIcon())
        self.resize(1320, 860)
        self.setMinimumSize(1060, 700)
        self.setAcceptDrops(True)

        self._apply_styles()
        self._build_ui()
        self._build_tray()
        self._build_shortcuts()
        self.toasts = ToastManager(self)
        self.toasts.setGeometry(self.rect())
        set_url_handler(self.open_web)

        if self.config.get("sidebar_collapsed", False):
            QTimer.singleShot(120, self.sidebar.toggle)

        QTimer.singleShot(50, self._post_show_init)

    # ------------------------------------------------------------------
    #  SETUP
    # ------------------------------------------------------------------
    def _post_show_init(self):
        self._initialized = True
        self.sidebar.set_active("home", animate=False)
        self.switch_page("home", animate=False)
        self.scan_library()
        QTimer.singleShot(2500, self._maybe_auto_check_updates)
        QTimer.singleShot(5000, self._auto_steam_sync)

    def _apply_styles(self):
        self.setStyleSheet(app_stylesheet())

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
        self.sidebar.command_requested.connect(self.open_command_palette)
        self.sidebar.btn_settings.clicked.connect(self.open_settings)
        self.sidebar.btn_about.clicked.connect(self.open_about)

        self.content = QFrame()
        self.content.setStyleSheet(f"background-color: {BLACK};")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        self.page_stack = QStackedWidget()
        self.page_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self.page_stack.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        self.home_page = HomePage()
        self.home_page.play_requested.connect(self.play_by_key)
        self.home_page.stop_requested.connect(self.stop_game)
        self.home_page.details_requested.connect(self.open_game_info)
        self.home_page.favorite_toggled.connect(self.toggle_favorite)
        self.home_page.add_requested.connect(self.open_add_games)
        self.home_page.folder_requested.connect(self.open_add_folder)
        self.home_page.steam_requested.connect(self.open_steam_import)
        self.home_page.studio_requested.connect(lambda: self.sidebar.switch("studio"))
        self.home_page.see_all_requested.connect(lambda: self.sidebar.switch("library"))
        self.home_page.web_requested.connect(lambda: self.open_web())

        self.library_page = LibraryPage(
            self.config,
            favorites_getter=lambda: self.config.get("favorites", []),
            play_times_getter=lambda: self.stats.get("play_times", {}),
            launch_counts_getter=lambda: self.stats.get("launch_counts", {}),
            page_title=L.t("library.title"),
        )
        self.library_page.refresh_btn.clicked.connect(self.refresh_library)
        self.library_page.play_requested.connect(self.play_by_key)
        self.library_page.details_requested.connect(self.open_game_info)
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
            show_tools=False,
        )
        self.fav_page.set_empty_message(L.t("favorites.empty"))
        self.fav_page.refresh_btn.clicked.connect(self.refresh_library)
        self.fav_page.play_requested.connect(self.play_by_key)
        self.fav_page.details_requested.connect(self.open_game_info)
        self.fav_page.context_requested.connect(self.show_context_menu)
        self.fav_page.favorite_toggled.connect(self.toggle_favorite)

        self.studio_page = StudioPage()

        self.page_stack.addWidget(self.home_page)
        self.page_stack.addWidget(self.library_page)
        self.page_stack.addWidget(self.fav_page)
        self.page_stack.addWidget(self.studio_page)

        self.game_tabs = GameTabBar()
        self.game_tabs.setObjectName("GameTabs")
        self.game_tabs.setExpanding(False)
        self.game_tabs.setDrawBase(False)
        self.game_tabs.setMovable(True)
        self.game_tabs.setTabsClosable(True)
        self.game_tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.game_tabs.setUsesScrollButtons(True)
        self.game_tabs.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.game_tabs.setProperty("gameActive", False)
        self.game_tabs.hide()
        self.game_tabs.tabCloseRequested.connect(self._close_game_tab_index)
        self.game_tabs.currentChanged.connect(self._on_game_tab_changed)
        self.game_tabs.tabBarClicked.connect(self._on_game_tab_clicked)
        self.content_layout.addWidget(self.game_tabs)
        self.content_layout.addWidget(self.page_stack)

        main.addWidget(self.sidebar)
        main.addWidget(self.content, stretch=1)
        root.addLayout(main, stretch=1)

        bottom = QFrame()
        bottom.setObjectName("BottomBar")
        bottom.setFixedHeight(30)
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(20, 0, 20, 0)
        self.bottom_left = QLabel(L.t("bottom.version"))
        self.bottom_left.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; letter-spacing: 1px;")
        bl.addWidget(self.bottom_left)
        bl.addSpacing(14)

        self.bottom_stats = QLabel("")
        self.bottom_stats.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; letter-spacing: 1px;")
        bl.addWidget(self.bottom_stats)
        bl.addSpacing(14)

        self.update_chip = QPushButton("")
        self.update_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_chip.setVisible(False)
        self.update_chip.setStyleSheet(f"""
            QPushButton {{
                background-color: {WHITE}; color: {BLACK};
                border: none; padding: 3px 12px;
                font-size: 9px; font-weight: 800; letter-spacing: 1px;
            }}
            QPushButton:hover {{ background-color: #D8D8D8; }}
        """)
        self.update_chip.clicked.connect(self._open_latest_update)
        bl.addWidget(self.update_chip)
        bl.addStretch()
        self.bottom_right = QLabel("")
        self.bottom_right.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; letter-spacing: 1px;")
        bl.addWidget(self.bottom_right)
        root.addWidget(bottom)
        self._update_bottom()

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self)
        if APP_ICON.exists():
            self.tray.setIcon(QIcon(str(APP_ICON)))
        else:
            tray_icon = get_tray_icon()
            self.tray.setIcon(tray_icon or QApplication.windowIcon())
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
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self.sidebar.switch("home"))
        QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda: self.sidebar.switch("library"))
        QShortcut(QKeySequence("Ctrl+3"), self, activated=lambda: self.sidebar.switch("favorites"))
        QShortcut(QKeySequence("Ctrl+4"), self, activated=lambda: self.sidebar.switch("studio"))
        QShortcut(QKeySequence("Ctrl+5"), self, activated=lambda: self.open_web())
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.open_command_palette)
        QShortcut(QKeySequence("Ctrl+W"), self, activated=self._close_current_game_tab)

    def _focus_search(self):
        if self.current_page in ("library", "favorites"):
            page = self.library_page if self.current_page == "library" else self.fav_page
            page.search.setFocus()

    def open_command_palette(self):
        from .widgets.command import CommandPalette
        palette = CommandPalette(self, self._command_actions())
        self.command_palette = palette
        palette.exec()
        self.command_palette = None

    def _command_actions(self):
        """Builds the searchable action list for Ctrl+K."""
        navigate = L.t("command.category.navigate")
        games = L.t("command.category.games")
        actions_cat = L.t("command.category.actions")
        items = [
            {"title": L.t("sidebar.home"), "subtitle": L.t("home.continue"),
             "category": navigate, "callback": lambda: self.sidebar.switch("home")},
            {"title": L.t("sidebar.library"), "subtitle": L.t("library.title"),
             "category": navigate, "callback": lambda: self.sidebar.switch("library")},
            {"title": L.t("sidebar.favorites"), "subtitle": L.t("favorites.empty").split("\n")[0],
             "category": navigate, "callback": lambda: self.sidebar.switch("favorites")},
            {"title": L.t("sidebar.studio"), "subtitle": L.t("studio.eyebrow"),
             "category": navigate, "callback": lambda: self.sidebar.switch("studio")},
            {"title": L.t("sidebar.web"), "subtitle": L.t("web.url_placeholder"),
             "category": navigate, "callback": lambda: self.open_web()},
            {"title": L.t("settings.title"), "subtitle": L.t("settings.subtitle"),
             "category": actions_cat, "callback": self.open_settings},
            {"title": L.t("about.title"), "subtitle": L.t("app.title"),
             "category": actions_cat, "callback": self.open_about},
            {"title": L.t("library.refresh"), "subtitle": L.t("library.title"),
             "category": actions_cat, "callback": self.refresh_library},
            {"title": L.t("library.add_game"), "subtitle": L.t("dialog.add.title"),
             "category": actions_cat, "callback": self.open_add_games},
            {"title": L.t("library.add_folder"), "subtitle": L.t("dialog.folder.title"),
             "category": actions_cat, "callback": self.open_add_folder},
            {"title": L.t("steam.title"), "subtitle": L.t("steam.subtitle"),
             "category": actions_cat, "callback": self.open_steam_import},
            {"title": L.t("settings.check_now"), "subtitle": L.t("update.check_title"),
             "category": actions_cat,
             "callback": lambda: self.check_updates(manual=True)},
            {"title": L.t("studio.open_site"), "subtitle": WEBSITE_URL,
             "category": actions_cat, "callback": lambda: self.open_web(WEBSITE_URL)},
            {"title": L.t("studio.github"), "subtitle": GITHUB_PROFILE,
             "category": actions_cat, "callback": lambda: self.open_web(GITHUB_PROFILE)},
            {"title": L.t("sidebar.collapse"), "subtitle": L.t("settings.section.interface"),
             "category": actions_cat, "callback": self.sidebar.toggle},
        ]
        for key, meta in self.manifests.items():
            name = str(meta.get("name", key))
            kind = str(meta.get("type", "game")).upper()
            items.append({
                "title": name,
                "subtitle": f"{kind}  ·  {human_size(meta.get('size', 0))}",
                "category": games,
                "callback": lambda k=key: self.open_game_tab(k),
            })
        return items

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self):
        self._end_session_on_quit()
        self._shutdown_web()
        self.tray.hide()
        QApplication.quit()

    def _end_session_on_quit(self):
        """Records play time without touching files while a game may run."""
        self._stop_session_timer()
        key = self.active_game_key
        if key and self.game_start_time:
            duration = time.time() - self.game_start_time
            if duration > 5:
                times = self.stats.setdefault("play_times", {})
                times[key] = times.get(key, 0) + int(duration)
                save_json(STATS_PATH, self.stats)
        self.active_process = None
        self.active_game_key = None
        self.game_start_time = None
        self.game_start_pid = None
        self._session_names = []
        self._session_pids = []
        self._session_seen = False
        self._session_missing = 0
        # Keep the extracted files: the game is still using them.
        self.temp_dir = None

    def _shutdown_game_pages(self):
        for page in list(self.game_pages.values()):
            try:
                page.shutdown()
            except Exception:
                pass

    def _shutdown_web(self):
        if self.web_page is not None:
            try:
                self.web_page.shutdown()
            except Exception:
                pass

    def closeEvent(self, event):
        if self.tray.isVisible():
            event.ignore()
            self.hide()
            self._set_web_active(False)
            self.tray.showMessage(L.t("tray.minimized_title"), L.t("tray.minimized_msg"),
                                  QSystemTrayIcon.MessageIcon.Information, 1500)
        else:
            self._end_session_on_quit()
            self._shutdown_game_pages()
            self._shutdown_web()
            event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.toasts is not None:
            self.toasts.setGeometry(self.rect())
            self.toasts.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        if self.current_page == "web":
            self._set_web_active(True)
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

    # ------------------------------------------------------------------
    #  NAVIGATION
    # ------------------------------------------------------------------
    def switch_page(self, key, animate=True):
        if key == "web" and self.web_page is None:
            self.open_web()
            return
        order = {"home": 0, "library": 1, "favorites": 2, "studio": 3, "web": 4}
        pages = {"home": self.home_page, "library": self.library_page,
                 "favorites": self.fav_page, "studio": self.studio_page,
                 "web": self.web_page}
        target = pages.get(key)
        if not target or key not in order:
            return
        if key != "web":
            self._set_web_active(False)
        if self.game_tabs.count():
            self._set_game_tab_active(False)
        if key == self.current_page and self._initialized:
            if key == "web":
                self._set_web_active(True)
            return

        previous_index = self.page_stack.currentIndex()
        index = self.page_stack.indexOf(target)
        self.current_page = key
        self.sidebar.set_active(key)

        if index == previous_index or index < 0:
            if key == "web":
                self._set_web_active(True)
            return

        if animate and self._initialized and ANIM.enabled() and previous_index >= 0:
            direction = 1 if index > previous_index else -1
            self._animate_page_switch(previous_index, index, direction)
        else:
            self.page_stack.setCurrentIndex(index)
        if key == "web":
            self._set_web_active(True)

    def _set_web_active(self, active):
        if self.web_page is not None:
            try:
                self.web_page.set_active(active)
            except Exception:
                pass

    def open_web(self, url=None):
        """Shows the in-app browser, optionally navigating to *url*."""
        if not self.config.get("web_in_app", True):
            webbrowser.open(str(url or self.config.get("web_home") or WEBSITE_URL))
            # Report "handled" so open_url() does not open the same link twice.
            return True
        if self.web_page is None:
            self.web_page = BrowserPage(self.config, self._save_config,
                                        parent=self.page_stack)
            self.web_page.status_message.connect(self.notify)
            self.page_stack.addWidget(self.web_page)
        if self.current_page != "web":
            self.sidebar.set_active("web")
            self.switch_page("web")
        if url:
            QTimer.singleShot(0, lambda u=str(url): self.web_page.navigate(u))
        return True

    # ------------------------------------------------------------------
    #  GAME TABS
    # ------------------------------------------------------------------
    def open_game_tab(self, key):
        """Opens (or focuses) the full page for one library game."""
        meta = self.manifests.get(key)
        if not meta:
            return
        if key in self.game_pages:
            for index in range(self.game_tabs.count()):
                if self.game_tabs.tabData(index) == key:
                    if self.current_page not in (None, "game"):
                        self._game_return_page = self.current_page
                    self.game_tabs.setCurrentIndex(index)
                    self._activate_game_tab(index)
                    break
            return

        if self.current_page not in (None, "game"):
            self._game_return_page = self.current_page

        favorites = set(self.config.get("favorites", []))
        page = GameDetailPage(
            key, meta, self.config, self.stats,
            is_favorite=key in favorites,
            parent=self.page_stack,
        )
        page.play_requested.connect(self.play_by_key)
        page.stop_requested.connect(self.stop_game)
        page.favorite_toggled.connect(self.toggle_favorite)
        page.folder_requested.connect(
            lambda k: self._open_game_folder(self.manifests.get(k, {})))
        page.web_requested.connect(self.open_web)
        page.close_requested.connect(self.close_game_tab)
        page.back_requested.connect(self._back_from_game)

        self.page_stack.addWidget(page)
        self.game_pages[key] = page

        title = str(meta.get("name", key))
        index = self.game_tabs.addTab(title)
        self.game_tabs.setTabData(index, key)
        self.game_tabs.setTabToolTip(index, title)
        self.game_tabs.show()
        self.game_tabs.setCurrentIndex(index)
        # When the bar was hidden, addTab may already have made this tab
        # current before its key was attached, so make the switch explicit.
        self._activate_game_tab(index)

    def _set_game_tab_active(self, active):
        """Highlights the selected tab only while a game page is shown."""
        active = bool(active)
        if self.game_tabs.property("gameActive") == active:
            return
        self.game_tabs.setProperty("gameActive", active)
        style = self.game_tabs.style()
        style.unpolish(self.game_tabs)
        style.polish(self.game_tabs)
        self.game_tabs.update()

    def _on_game_tab_changed(self, index):
        if self._game_tab_guard or index < 0:
            return
        self._activate_game_tab(index)

    def _on_game_tab_clicked(self, index):
        # Needed because QTabBar keeps its selection while a regular page is
        # visible; clicking the already-selected tab would emit nothing.
        if index >= 0:
            self._activate_game_tab(index)

    def _activate_game_tab(self, index):
        key = self.game_tabs.tabData(index)
        page = self.game_pages.get(key)
        if page is None:
            return
        self._set_web_active(False)
        self.current_page = "game"
        self.sidebar.set_active(None, animate=False)
        self.page_stack.setCurrentWidget(page)
        self._set_game_tab_active(True)

    def _back_from_game(self, _key=None):
        target = self._game_return_page
        if target not in ("home", "library", "favorites", "studio", "web"):
            target = "library"
        self.sidebar.switch(target)

    def _close_game_tab_index(self, index):
        key = self.game_tabs.tabData(index)
        if key:
            self.close_game_tab(key)

    def _close_current_game_tab(self):
        if self.current_page != "game":
            return
        index = self.game_tabs.currentIndex()
        if index >= 0:
            self._close_game_tab_index(index)

    def close_game_tab(self, key):
        page = self.game_pages.pop(key, None)
        if page is None:
            return
        index = -1
        for i in range(self.game_tabs.count()):
            if self.game_tabs.tabData(i) == key:
                index = i
                break
        was_current = (self.current_page == "game" and index >= 0
                       and self.game_tabs.currentIndex() == index)

        self._game_tab_guard = True
        if index >= 0:
            self.game_tabs.removeTab(index)
        self.page_stack.removeWidget(page)
        try:
            page.shutdown()
        except Exception:
            pass
        page.deleteLater()
        self._game_tab_guard = False

        if self.game_tabs.count() == 0:
            self.game_tabs.hide()
            self._set_game_tab_active(False)
            if self.current_page == "game":
                self.current_page = None
                self.sidebar.switch("library")
            return
        if was_current:
            self.game_tabs.setCurrentIndex(
                min(index, self.game_tabs.count() - 1))
            self._activate_game_tab(self.game_tabs.currentIndex())
        elif self.current_page != "game":
            self._set_game_tab_active(False)

    def _refresh_game_pages(self):
        favorites = set(self.config.get("favorites", []))
        for key in list(self.game_pages):
            meta = self.manifests.get(key)
            if not meta:
                self.close_game_tab(key)
                continue
            page = self.game_pages.get(key)
            if page is None:
                continue
            page.update_meta(meta, key in favorites)
            page.update_stats(
                play_time=self.stats.get("play_times", {}).get(key),
                launch_count=self.stats.get("launch_counts", {}).get(key),
                last_played=self.stats.get("last_played", {}).get(key),
            )
            for index in range(self.game_tabs.count()):
                if self.game_tabs.tabData(index) == key:
                    self.game_tabs.setTabText(index, str(meta.get("name", key)))
                    self.game_tabs.setTabToolTip(index, str(meta.get("name", key)))
                    break

    def _update_game_page_stats(self, key):
        page = self.game_pages.get(key)
        if page is None:
            return
        page.update_stats(
            play_time=self.stats.get("play_times", {}).get(key),
            launch_count=self.stats.get("launch_counts", {}).get(key),
            last_played=self.stats.get("last_played", {}).get(key),
        )

    def _save_config(self):
        save_json(CONFIG_PATH, self.config)

    def notify(self, message, kind="info", duration=2800):
        if not message:
            return
        if self.toasts is not None:
            self.toasts.show_toast(message, kind=kind, duration=duration)

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

        duration = ANIM.duration(300)
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
        self.bottom_right.setText(
            L.t("bottom.temp", size=human_size(dir_size_cached(t))))
        steam_count = sum(1 for meta in self.manifests.values() if meta.get("type") == "steam")
        self.bottom_stats.setText(L.t("bottom.stats", games=len(self.manifests), steam=steam_count))

    # ------------------------------------------------------------------
    #  LIBRARY
    # ------------------------------------------------------------------
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
        self._refresh_home()
        self._refresh_game_pages()
        self._update_bottom()
        self._update_running_ui()

    def _render_favorites(self):
        favs = set(self.config.get("favorites", []))
        filtered = {k: v for k, v in self.manifests.items() if k in favs}
        self.fav_page.render(filtered)

    def _refresh_home(self):
        try:
            self.home_page.update_library(
                self.manifests, self.stats, self.config.get("favorites", []))
        except Exception as e:
            log.exception(f"Не удалось обновить главную: {e}")

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
        self._refresh_home()
        page = self.game_pages.get(key)
        if page is not None:
            page.set_favorite(key in favs)

    def open_game_info(self, key):
        self.open_game_tab(key)

    def show_context_menu(self, key, global_pos):
        if key not in self.manifests:
            return
        meta = self.manifests[key]
        menu = QMenu(self)
        menu.setStyleSheet(menu_stylesheet())
        favs = set(self.config.get("favorites", []))

        act_play = QAction(L.t("menu.play"), self)
        menu.addAction(act_play)

        act_stop = None
        if key == self.active_game_key and self._session_alive():
            act_stop = QAction(L.t("launch.stop_game"), self)
            menu.addAction(act_stop)

        act_info = QAction(L.t("menu.details"), self)
        menu.addAction(act_info)

        if key in favs:
            act_fav = QAction(L.t("menu.favorite_remove"), self)
        else:
            act_fav = QAction(L.t("menu.favorite_add"), self)
        menu.addAction(act_fav)

        menu.addSeparator()

        act_open = QAction(L.t("menu.open_folder"), self)
        menu.addAction(act_open)

        act_rename = QAction(L.t("menu.rename"), self)
        menu.addAction(act_rename)

        menu.addSeparator()

        is_external = bool(meta.get("external"))
        act_delete = QAction(L.t("menu.remove") if is_external else L.t("menu.delete"), self)
        menu.addAction(act_delete)

        action = menu.exec(global_pos)
        if action == act_play:
            self.play_by_key(key)
        elif act_stop is not None and action == act_stop:
            self.stop_game(key)
        elif action == act_info:
            self.open_game_info(key)
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
        self._refresh_home()
        self._refresh_game_pages()

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
        open_path(folder)

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

    # ------------------------------------------------------------------
    #  LAUNCHING
    # ------------------------------------------------------------------
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
            if self._session_alive():
                QMessageBox.warning(self, L.t("menu.play"), L.t("launch.already_running"))
                return
            # The tracked process is gone but the poll timer has not fired yet.
            self._finish_session()
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
                # Steam starts the game asynchronously, so watch the game's
                # executable names instead of a Popen handle.
                self._start_session(
                    key, names=game_exe_names(meta.get("path")),
                    path=meta.get("path", ""))
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
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            is_script = exe_path.lower().endswith((".bat", ".cmd"))
            process = None
            if is_script:
                # cmd.exe exits as soon as the script finishes; the script
                # itself usually starts the real game, so track processes.
                subprocess.Popen(["cmd", "/c", exe_path], cwd=cwd,
                                 shell=False, creationflags=flags)
                names = game_exe_names(cwd) if cwd else []
            else:
                process = subprocess.Popen(
                    [exe_path], cwd=cwd, shell=False, creationflags=flags)
                names = [os.path.basename(exe_path).lower()]
                extra = game_exe_names(cwd) if cwd else []
                names.extend(n for n in extra if n not in names)
            self.active_process = process
            if not keep_temp:
                self.temp_dir = None
            self._register_launch(key)
            self._start_session(key, process=process, names=names, path=cwd or "")
            pid_text = process.pid if process is not None else "—"
            self.library_page.status.setText(L.t("launch.playing", name=name,
                                                 pid=pid_text))
            log.info(f"Запуск: {name} (PID {pid_text})")
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
            open_path(target)
            resolved = resolve_shortcut_target(target) if target.lower().endswith(".lnk") else target
            names = []
            if resolved and os.path.isfile(resolved):
                names.append(os.path.basename(resolved).lower())
                folder = os.path.dirname(resolved)
                names.extend(n for n in game_exe_names(folder) if n not in names)
            self._register_launch(key)
            self._start_session(key, names=names,
                                path=os.path.dirname(resolved) if resolved else "")
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
        """Count a launch for this game, remember it and refresh stats lines."""
        counts = self.stats.setdefault("launch_counts", {})
        counts[key] = counts.get(key, 0) + 1
        self.stats.setdefault("last_played", {})[key] = int(time.time())
        save_json(STATS_PATH, self.stats)
        self.library_page.update_card_stats(key, launch_count=counts[key])
        self.fav_page.update_card_stats(key, launch_count=counts[key])
        self._update_game_page_stats(key)
        self._refresh_home()

    def _start_session(self, key, process=None, names=None, path=""):
        """Begins a play-time session.

        A Popen handle is polled directly when available; for Steam, shortcuts
        and scripts we watch the game's executable names.  This keeps the
        launcher honest: the session ends when the game really exits, not when
        a helper process or a stale PID disappears.
        """
        self._stop_session_timer()
        self.active_game_key = key
        self.game_start_time = time.time()
        self.active_process = process
        self.game_start_pid = process.pid if process is not None else None
        self._session_names = sorted({
            str(name).lower() for name in (names or []) if name})
        self._session_pids = []
        self._session_seen = False
        self._session_missing = 0
        self._session_stopping = False
        self._ext_started = False
        self._ext_baseline = (snapshot_pids()
                              if process is None and not self._session_names
                              else None)
        # Steam needs a few seconds before the real game process appears.
        self._session_grace_until = (time.time() if process is not None
                                     else time.time() + 25)
        self.home_page.set_now_playing(key, self.game_start_time)
        self._update_running_ui()
        if self._ext_timer is None:
            self._ext_timer = QTimer(self)
            self._ext_timer.setInterval(2000)
            self._ext_timer.timeout.connect(self._poll_external_session)
        self._ext_timer.start()

    def _stop_session_timer(self):
        if self._ext_timer is not None:
            self._ext_timer.stop()

    def _session_alive(self):
        """Cheap liveness check used by UI code (no side effects)."""
        if self.active_game_key is None:
            return False
        if self.active_process is not None:
            if self.active_process.poll() is None:
                return True
            if not self._session_names:
                return False
        if self._session_names and pids_for_names(self._session_names):
            return True
        if self._session_seen:
            return False
        return (self._ext_baseline is not None
                or time.time() < self._session_grace_until)

    def _poll_external_session(self):
        if self.active_game_key is None:
            self._stop_session_timer()
            return
        now = time.time()

        if self.active_process is not None:
            if self.active_process.poll() is None:
                return
            # A launcher often spawns the real game and exits immediately, so
            # fall back to the executable names before ending the session.
            self.active_process = None
            self.game_start_pid = None
            if not self._session_names:
                self._finish_session()
                return
            # Give the real game a few seconds to appear after its launcher.
            self._session_grace_until = max(
                self._session_grace_until, now + 15)

        if self._session_names:
            pids = pids_for_names(self._session_names)
            if pids:
                self._session_pids = pids
                self._session_seen = True
                self._session_missing = 0
                return
            if not self._session_seen:
                if now < self._session_grace_until:
                    return
                self._finish_session(lost=True)
                return
            self._session_missing += 1
            if self._session_missing >= 2:
                self._finish_session()
            return

        # No known executable names: watch for new processes relative to the
        # snapshot taken at launch.  We remember the PIDs we saw so a process
        # that merely changes state does not look like "the game closed".
        current = snapshot_pids()
        if not current:
            return
        if not self._session_seen:
            baseline = self._ext_baseline or {}
            new = {pid: name for pid, name in current.items()
                   if pid not in baseline
                   and not any(noise in name for noise in LAUNCH_NOISE)}
            if new:
                self._session_seen = True
                self._session_pids = list(new)
                self._session_missing = 0
                return
            if now < self._session_grace_until:
                return
            self._finish_session(lost=True)
            return
        alive = [pid for pid in self._session_pids if pid in current]
        if alive:
            self._session_pids = alive
            self._session_missing = 0
            return
        self._session_missing += 1
        if self._session_missing >= 2:
            self._finish_session()

    def stop_game(self, key=None, confirm=True):
        """Force-closes a running game launched from the launcher."""
        if self.active_game_key is None or not self._session_alive():
            self.notify(L.t("launch.not_running"))
            self._finish_session()
            return False
        if key is not None and key != self.active_game_key:
            self.notify(L.t("launch.not_running"))
            return False
        meta = self.manifests.get(self.active_game_key, {})
        name = meta.get("name", self.active_game_key)
        if confirm:
            answer = QMessageBox.question(
                self, L.t("launch.stop_title"),
                L.t("launch.stop_confirm", name=name),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return False

        self._session_stopping = True
        self._stop_session_timer()
        self.library_page.status.setText(L.t("launch.stopping", name=name))

        pids = list(self._session_pids)
        if self.active_process is not None and self.active_process.poll() is None:
            pids.append(self.active_process.pid)
        names = list(self._session_names)
        if names:
            pids.extend(pids_for_names(names))
        pids = sorted({int(pid) for pid in pids if str(pid).isdigit()})
        if pids:
            terminate_pids(pids)
        self._finish_session(stopped=True)

        # The game may take a moment to release its files; check again and
        # retry once so "Stop" really stops the game.
        QTimer.singleShot(1200,
                          lambda: self._ensure_stopped(name, pids, names))
        return True

    def _ensure_stopped(self, name, pids, names=()):
        leftover = [pid for pid in (pids or []) if self._pid_alive(pid)]
        # Never touch processes of a session the user started in the meantime.
        fresh_session = self.active_game_key is not None
        if not leftover and names and not fresh_session:
            leftover = pids_for_names(names)
        if leftover:
            terminate_pids(leftover)
        if not fresh_session:
            self.notify(L.t("launch.stopped", name=name))

    @staticmethod
    def _pid_alive(pid):
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return False
        try:
            if os.name == "nt":
                out = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW)
                return str(pid) in (out.stdout or "")
            os.kill(pid, 0)
            return True
        except Exception:
            return False

    def _finish_session(self, lost=False, stopped=False):
        self._stop_session_timer()
        key = self.active_game_key
        if key is None:
            self._update_running_ui()
            return
        duration = time.time() - self.game_start_time if self.game_start_time else 0
        if duration > 5:
            times = self.stats.setdefault("play_times", {})
            times[key] = times.get(key, 0) + int(duration)
            save_json(STATS_PATH, self.stats)
            self.library_page.update_card_stats(key, play_time=times[key])
            self.fav_page.update_card_stats(key, play_time=times[key])
            self._update_game_page_stats(key)
            log.info(f"Игра {key} закрыта, время сессии: {int(duration)}с")

        if not stopped:
            self.library_page.status.setText(
                L.t("launch.session_lost") if lost else L.t("launch.closed"))
        if (self.config.get("auto_cleanup", True) and self.temp_dir
                and os.path.exists(self.temp_dir)):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                if not stopped:
                    self.library_page.status.setText(L.t("launch.cleaned"))
            except Exception as e:
                log.warning(f"Не удалось очистить: {e}")
        self.temp_dir = None
        self.active_process = None
        self.active_game_key = None
        self.game_start_time = None
        self.game_start_pid = None
        self._session_names = []
        self._session_pids = []
        self._session_seen = False
        self._session_missing = 0
        self._session_stopping = False
        self._ext_baseline = None
        self._ext_started = False
        self.home_page.clear_now_playing()
        self._update_running_ui()
        self._refresh_home()
        self._update_bottom()

    def _update_running_ui(self):
        """Syncs Play/Stop buttons and the home hero with the session state."""
        key = self.active_game_key
        for page_key, page in list(self.game_pages.items()):
            try:
                page.set_running(page_key == key)
            except Exception:
                pass
        try:
            self.home_page.set_running(bool(key))
        except Exception:
            pass
        for page in (self.library_page, self.fav_page):
            try:
                page.set_card_running(key)
            except Exception:
                pass

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

                if ext in (".dvp", ".zip"):
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
                        "name": prettify_stem(p),
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
        if dialog.exec() == SteamImportDialog.DialogCode.Accepted:
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
        if time.time() - last < STEAM_UPDATE_CHECK_INTERVAL:
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
        self.home_page.studio_card.set_news(f"{L.t('studio.release').upper()}  ·  {tag or 'V' + VERSION}")
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
            open_path(archive.parent)
            QMessageBox.information(self, L.t("update.title"),
                                    L.t("update.source_mode", path=str(archive)))
            return
        if os.name != "nt":
            open_path(archive)
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

    # ------------------------------------------------------------------
    #  DIALOGS
    # ------------------------------------------------------------------
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
            self.notify(L.t("toast.language"), "info")
            QTimer.singleShot(100, self._restart_with_new_language)
            return

        UI.configure(self.config)
        ANIM.configure(self.config)
        self.library_page.config = new_conf
        self.fav_page.config = new_conf
        self.library_page.apply_design()
        self.fav_page.apply_design()
        for page in (self.home_page, self.studio_page):
            try:
                page.repaint_backdrop()
            except Exception:
                pass
        if self.web_page is not None:
            self.web_page.apply_config(new_conf)
        self.notify(L.t("toast.settings_saved"), "success")
        self.scan_library()
        self._update_bottom()
        QTimer.singleShot(800, self._auto_steam_sync)

    def _restart_with_new_language(self):
        L.set_language(self.config.get("language", "en"))
        self._shutdown_web()
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

    # ------------------------------------------------------------------
    #  DRAG & DROP
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        if paths:
            event.acceptProposedAction()
            self._add_paths(paths)


_new_window = None


def get_tray_icon():
    from .utils import get_icon
    return get_icon("tray", 64)


def prettify_stem(path):
    from .utils import prettify_name
    return prettify_name(Path(path).stem)
