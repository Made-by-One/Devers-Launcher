"""In-app web browser: a sharp monochrome page plus a standalone dialog.

QtWebEngine is optional.  When it is missing the page still renders a useful
start screen and every link is handed to the default browser.
"""

import html
import logging
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import webbrowser

from PyQt6.QtCore import (QObject, QPoint, QRunnable, QSize, Qt, QThreadPool,
                          QTimer, QUrl, pyqtSignal)
from PyQt6.QtGui import (QAction, QColor, QDesktopServices, QKeySequence,
                         QPainter, QShortcut)
from PyQt6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout,
                             QLabel, QLineEdit, QMenu, QProgressBar,
                             QPushButton, QScrollArea, QStackedWidget,
                             QVBoxLayout, QWidget)

from .i18n import L
from .paths import (GITHUB_PROFILE, GITHUB_RELEASES_PAGE, USER_AGENT, VERSION,
                    WEB_CACHE_DIR, WEB_DOWNLOADS_DIR, WEB_SEARCH_URL,
                    WEB_STORAGE_DIR, WEBSITE_URL)
from .theme import (ANIM, BLACK, LINE, SURFACE, SURFACE_2, TEXT_DIM,
                    TEXT_MUTED, WHITE, dialog_stylesheet, fade_in_widget,
                    menu_stylesheet, primary_button_style,
                    secondary_button_style)
from .utils import get_icon
from .widgets.page import Page

log = logging.getLogger("Devers")

try:
    from PyQt6.QtWebEngineCore import (QWebEngineDownloadRequest,
                                       QWebEnginePage, QWebEngineProfile,
                                       QWebEngineSettings)
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    QWebEngineDownloadRequest = None
    QWebEnginePage = object
    QWebEngineProfile = None
    QWebEngineSettings = None
    QWebEngineView = None
    WEBENGINE_AVAILABLE = False


# ---------------------------------------------------------------------------
#  Start page
# ---------------------------------------------------------------------------
START_PAGE = """<!doctype html>
<html lang="__LANG__"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Devers Web</title>
<style>
:root { color-scheme: dark; }
* { box-sizing: border-box; }
html, body { margin:0; padding:0; background:#000; color:#f4f4f4;
  font-family:'Segoe UI', Inter, 'Helvetica Neue', Arial, sans-serif; }
body { min-height:100vh;
  background-image:linear-gradient(#0b0b0b 1px, transparent 1px),
                   linear-gradient(90deg, #0b0b0b 1px, transparent 1px);
  background-size:56px 56px; }
.wrap { max-width:1120px; margin:0 auto; padding:46px 42px 60px; }
.top { display:flex; justify-content:space-between; align-items:center; gap:20px; }
.brand { font-size:11px; font-weight:900; letter-spacing:4px; }
.brand span { color:#666; }
.status { border:1px solid #2c2c2c; padding:5px 9px; color:#a6a6a6;
  font-size:9px; font-weight:800; letter-spacing:2px; }
.hero { margin-top:72px; }
.eyebrow { color:#666; font-size:10px; font-weight:800; letter-spacing:4px; }
h1 { font-size:clamp(38px, 5.4vw, 70px); line-height:.95; letter-spacing:-2px;
  margin:16px 0 18px; font-weight:900; max-width:880px; }
.sub { color:#a6a6a6; font-size:14px; max-width:640px; line-height:1.65; }
.search { display:flex; margin-top:30px; max-width:720px;
  border:1px solid #2c2c2c; background:#050505; }
.search input { flex:1; background:transparent; border:0; color:#fff;
  padding:16px; font-size:14px; outline:none; }
.search input::placeholder { color:#555; }
.search button { background:#fff; color:#000; border:0; padding:0 26px;
  font-size:10px; font-weight:900; letter-spacing:2px; cursor:pointer; }
.search button:hover { background:#000; color:#fff;
  box-shadow:inset 0 0 0 1px #fff; }
.section { margin-top:48px; }
.section-head { display:flex; align-items:center; gap:12px; margin-bottom:14px; }
.section-head h2 { font-size:10px; letter-spacing:3px; color:#fff;
  margin:0; font-weight:800; }
.section-head .line { flex:1; height:1px; background:#1a1a1a; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
  gap:10px; }
.card { display:block; text-decoration:none; color:#fff; border:1px solid #1a1a1a;
  background:#050505; padding:18px; transition:background .15s,color .15s,
  border-color .15s; }
.card:hover { background:#fff; color:#000; border-color:#fff; }
.card .idx { font-size:9px; letter-spacing:2px; color:#666; }
.card:hover .idx { color:#000; }
.card .title { font-size:14px; font-weight:800; margin-top:12px; }
.card .desc { font-size:10px; color:#666; margin-top:6px; line-height:1.5; }
.card:hover .desc { color:#333; }
.card .arrow { float:right; font-size:14px; }
.list { border-top:1px solid #1a1a1a; }
.row { display:flex; justify-content:space-between; gap:20px; padding:12px 0;
  border-bottom:1px solid #1a1a1a; text-decoration:none; color:#a6a6a6; }
.row:hover { color:#fff; }
.row .host { color:#666; font-size:10px; }
.empty { color:#555; font-size:11px; padding:14px 0; }
.footer { margin-top:56px; padding-top:18px; border-top:1px solid #1a1a1a;
  display:flex; justify-content:space-between; gap:20px; color:#666;
  font-size:9px; letter-spacing:1px; }
::-webkit-scrollbar { width:8px; height:8px; }
::-webkit-scrollbar-track { background:#000; }
::-webkit-scrollbar-thumb { background:#2c2c2c; }
::-webkit-scrollbar-thumb:hover { background:#666; }
</style></head>
<body><div class="wrap">
  <div class="top">
    <div class="brand">DEVERS <span>// WEB</span></div>
    <div class="status">__STATUS__ &nbsp;·&nbsp; V__VERSION__</div>
  </div>
  <div class="hero">
    <div class="eyebrow">__EYEBROW__</div>
    <h1>__HERO__</h1>
    <p class="sub">__SUB__</p>
    <form class="search" onsubmit="event.preventDefault();
      var q=document.getElementById('q').value.trim();
      if(q){location.href='__SEARCH__'.replace('{query}', encodeURIComponent(q));}">
      <input id="q" autocomplete="off" placeholder="__PLACEHOLDER__">
      <button type="submit">__SEARCH_LABEL__</button>
    </form>
  </div>
  <div class="section">
    <div class="section-head"><h2>__QUICK_LABEL__</h2><div class="line"></div></div>
    <div class="grid">__QUICK__</div>
  </div>
  <div class="section">
    <div class="section-head"><h2>__RECENT_LABEL__</h2><div class="line"></div></div>
    <div class="list">__RECENT__</div>
  </div>
  <div class="section">
    <div class="section-head"><h2>__BOOKMARKS_LABEL__</h2><div class="line"></div></div>
    <div class="list">__BOOKMARKS__</div>
  </div>
  <div class="footer">
    <span>__FOOTER__</span>
    <span>__LINKS_INSIDE__</span>
  </div>
</div></body></html>"""

QUICK_LINKS = (
    ("web.quick.studio.title", "web.quick.studio.desc", WEBSITE_URL),
    ("web.quick.github.title", "web.quick.github.desc", GITHUB_PROFILE),
    ("web.quick.releases.title", "web.quick.releases.desc", GITHUB_RELEASES_PAGE),
    ("web.quick.steam.title", "web.quick.steam.desc", "https://store.steampowered.com/"),
    ("web.quick.packer.title", "web.quick.packer.desc",
     "https://github.com/Made-by-One/Devers-Packer"),
    ("web.quick.repo.title", "web.quick.repo.desc",
     "https://github.com/Made-by-One/Devers-Launcher"),
)


def _host(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc or url
    except Exception:
        return url


def start_html(home_url, recent=None, bookmarks=None) -> str:
    def esc(key, **kwargs):
        return html.escape(L.t(key, **kwargs))

    cards = []
    for index, (title_key, desc_key, url) in enumerate(QUICK_LINKS, start=1):
        cards.append(
            f'<a class="card" href="{html.escape(url, quote=True)}">'
            f'<span class="idx">0{index}</span><span class="arrow">↗</span>'
            f'<div class="title">{esc(title_key)}</div>'
            f'<div class="desc">{esc(desc_key)}</div></a>')

    def rows(items):
        if not items:
            return f'<div class="empty">{html.escape(L.t("web.start.none"))}</div>'
        out = []
        for url in items[:8]:
            safe = html.escape(str(url), quote=True)
            out.append(
                f'<a class="row" href="{safe}">'
                f'<span>{html.escape(_host(url))}</span>'
                f'<span class="host">{html.escape(str(url))}</span></a>')
        return "".join(out)

    return (START_PAGE
            .replace("__LANG__", html.escape(L.current_lang))
            .replace("__STATUS__", esc("web.start.status"))
            .replace("__EYEBROW__", esc("web.start.eyebrow"))
            .replace("__HERO__", esc("web.start.hero"))
            .replace("__SUB__", esc("web.start.sub"))
            .replace("__PLACEHOLDER__", esc("web.start.placeholder"))
            .replace("__SEARCH_LABEL__", esc("web.start.search"))
            .replace("__QUICK_LABEL__", esc("web.start.quick"))
            .replace("__RECENT_LABEL__", esc("web.start.recent"))
            .replace("__BOOKMARKS_LABEL__", esc("web.start.bookmarks"))
            .replace("__FOOTER__", esc("web.start.footer", version=VERSION))
            .replace("__LINKS_INSIDE__", esc("web.start.links_inside"))
            .replace("__SEARCH__", WEB_SEARCH_URL)
            .replace("__QUICK__", "".join(cards))
            .replace("__RECENT__", rows(recent or []))
            .replace("__BOOKMARKS__", rows(bookmarks or []))
            .replace("__VERSION__", VERSION))


# ---------------------------------------------------------------------------
#  Shared WebEngine profile
# ---------------------------------------------------------------------------
class WebSignals(QObject):
    """Tiny bridge so downloads can report back to whichever page is open."""

    status = pyqtSignal(str)


WEB_SIGNALS = WebSignals()


class WebInstallSignals(QObject):
    status = pyqtSignal(str)
    finished = pyqtSignal(bool, str)


class WebEngineInstallTask(QRunnable):
    """Installs PyQt6-WebEngine for the interpreter running the launcher."""

    def __init__(self):
        super().__init__()
        self.signals = WebInstallSignals()

    def run(self):
        command = [
            sys.executable, "-m", "pip", "install",
            "--only-binary", ":all:", "--upgrade", "PyQt6-WebEngine>=6.6",
        ]
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=flags,
            )
            for line in process.stdout or []:
                line = line.strip()
                if line:
                    self.signals.status.emit(line)
            code = process.wait()
            if code == 0:
                self.signals.finished.emit(True, "")
            else:
                self.signals.finished.emit(False, f"pip exited with {code}")
        except Exception as exc:
            self.signals.finished.emit(False, str(exc))


_profiles = {}


def _profile(cache_enabled: bool):
    key = bool(cache_enabled)
    profile = _profiles.get(key)
    if profile is not None:
        return profile
    parent = QApplication.instance()
    if key:
        profile = QWebEngineProfile("devers-browser", parent)
        profile.setCachePath(str(WEB_CACHE_DIR))
        profile.setPersistentStoragePath(str(WEB_STORAGE_DIR))
        profile.setHttpCacheType(
            QWebEngineProfile.HttpCacheType.DiskHttpCache)
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
    else:
        profile = QWebEngineProfile(parent)
    profile.setHttpUserAgent(f"{USER_AGENT} (QtWebEngine)")
    # Keep the browser responsive: cap the disk cache and skip expensive
    # background work that a small embedded browser does not need.
    for setter, value in (
        ("setHttpCacheMaximumSize", 128 * 1024 * 1024),
        ("setSpellCheckEnabled", False),
        ("setDnsPrefetchEnabled", True),
    ):
        try:
            getattr(profile, setter)(value)
        except Exception:
            pass
    profile.downloadRequested.connect(_handle_download)
    _profiles[key] = profile
    return profile


def _handle_download(download):
    try:
        WEB_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        download.setDownloadDirectory(str(WEB_DOWNLOADS_DIR))
        name = download.downloadFileName() or "download"
        download.accept()
        WEB_SIGNALS.status.emit(L.t("web.download.started", name=name))

        def changed(state):
            try:
                if state == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
                    WEB_SIGNALS.status.emit(
                        L.t("web.download.done", name=name))
                elif state == QWebEngineDownloadRequest.DownloadState.DownloadInterrupted:
                    WEB_SIGNALS.status.emit(
                        L.t("web.download.error", error=name))
            except Exception:
                pass

        download.stateChanged.connect(changed)
    except Exception as e:
        log.warning(f"Web download failed: {e}")
        WEB_SIGNALS.status.emit(L.t("web.download.error", error=str(e)))


def clear_web_cache():
    for profile in _profiles.values():
        try:
            profile.clearHttpCache()
            profile.clearAllVisitedLinks()
        except Exception:
            pass
    for folder in (WEB_CACHE_DIR, WEB_STORAGE_DIR):
        shutil.rmtree(folder, ignore_errors=True)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


class DeversWebPage(QWebEnginePage):
    """Page subclass: keeps target=_blank inside the same view."""

    def createWindow(self, _window_type):
        return self

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        scheme = url.scheme().lower()
        if scheme in ("mailto", "steam", "discord", "tg"):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def javaScriptConsoleMessage(self, level, message, line, source):
        log.debug(f"WebEngine JS [{level}] {message} ({source}:{line})")


class BrowserPage(Page):
    """A compact, sharp browser with a start page, bookmarks and downloads."""

    status_message = pyqtSignal(str)

    def __init__(self, config=None, save_config=None, compact=False, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self._save_config = save_config or (lambda: None)
        self._compact = compact
        self._home_url = self.config.get("web_home") or WEBSITE_URL
        self._recent = list(self.config.get("web_recent", []) or [])
        self._bookmarks = list(self.config.get("web_bookmarks", []) or [])
        self._view = None
        self._profile = None
        self._page = None
        self._fallback = None
        self._loading = False
        self._showing_start = True
        self._start_loaded = False
        self._start_page_loading = False
        self._current_url = ""
        self._zoom = float(self.config.get("web_zoom", 1.0) or 1.0)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(450)
        self._save_timer.timeout.connect(self._flush_config)
        self._menu = QMenu(self)
        self._build_menu()
        self._build_ui()
        self._shortcuts()
        WEB_SIGNALS.status.connect(self.status_message.emit)

    # -- construction ------------------------------------------------------
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("WebBar")
        bar.setFixedHeight(54)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 9, 12, 9)
        bl.setSpacing(5)

        self.back_btn = self._tool_button("‹", L.t("web.back"))
        self.forward_btn = self._tool_button("›", L.t("web.forward"))
        self.reload_btn = self._tool_button("↻", L.t("web.reload"))
        self.home_btn = self._tool_button("⌂", L.t("web.home"))
        for btn in (self.back_btn, self.forward_btn, self.reload_btn, self.home_btn):
            bl.addWidget(btn)

        self.scheme = QLabel(L.t("web.status.start"))
        self.scheme.setObjectName("Micro")
        self.scheme.setFixedWidth(58)
        self.scheme.setToolTip(L.t("web.status.start"))
        self.scheme.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(self.scheme)

        self.url_bar = QLineEdit()
        self.url_bar.setObjectName("WebUrl")
        self.url_bar.setPlaceholderText(L.t("web.url_placeholder"))
        self.url_bar.setClearButtonEnabled(True)
        self.url_bar.returnPressed.connect(self._navigate_from_bar)
        bl.addWidget(self.url_bar, stretch=1)

        self.bookmark_btn = self._tool_button("☆", L.t("web.bookmark"))
        self.external_btn = self._tool_button("↗", L.t("web.external"))
        self.menu_btn = self._tool_button("⋯", L.t("web.menu"))
        self.menu_btn.setMenu(self._menu)
        bl.addWidget(self.bookmark_btn)
        bl.addWidget(self.external_btn)
        bl.addWidget(self.menu_btn)
        outer.addWidget(bar)

        self.progress = QProgressBar()
        self.progress.setObjectName("WebProgress")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        outer.addWidget(self.progress)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent; border: none;")
        outer.addWidget(self._stack, stretch=1)

        self._placeholder = QWidget()
        ph = QVBoxLayout(self._placeholder)
        ph.setContentsMargins(40, 40, 40, 40)
        ph.setSpacing(10)
        ph.addStretch(1)
        mark = QLabel("DEVERS  //  WEB")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet(
            "color: #FFFFFF; font-size: 12px; font-weight: 900; "
            "letter-spacing: 5px; background: transparent;")
        hint = QLabel(L.t("web.loading"))
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; letter-spacing: 2px; "
            "background: transparent;")
        ph.addWidget(mark)
        ph.addWidget(hint)
        ph.addStretch(1)
        self._stack.addWidget(self._placeholder)

        self.error_page = QWidget()
        el = QVBoxLayout(self.error_page)
        el.setContentsMargins(40, 40, 40, 40)
        el.setSpacing(10)
        el.addStretch(1)
        self.error_title = QLabel(L.t("web.error_title"))
        self.error_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_title.setStyleSheet(
            "color: #FFFFFF; font-size: 20px; font-weight: 900; "
            "background: transparent;")
        self.error_hint = QLabel(L.t("web.error_hint"))
        self.error_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_hint.setWordWrap(True)
        self.error_hint.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        el.addWidget(self.error_title)
        el.addWidget(self.error_hint)
        actions = QHBoxLayout()
        actions.addStretch()
        retry = QPushButton(L.t("web.retry"))
        retry.clicked.connect(self._retry)
        ext = QPushButton(L.t("web.external"))
        ext.setObjectName("Secondary")
        ext.clicked.connect(self._open_external)
        actions.addWidget(retry)
        actions.addWidget(ext)
        actions.addStretch()
        el.addLayout(actions)
        el.addStretch(1)
        self._stack.addWidget(self.error_page)
        self._stack.setCurrentWidget(self._placeholder)

        self.back_btn.clicked.connect(self._go_back)
        self.forward_btn.clicked.connect(self._go_forward)
        self.reload_btn.clicked.connect(self.reload)
        self.home_btn.clicked.connect(self.go_home)
        self.bookmark_btn.clicked.connect(self._toggle_bookmark)
        self.external_btn.clicked.connect(self._open_external)
        self._update_nav_buttons()
        self._update_bookmark_button()

    def _tool_button(self, text, tooltip):
        btn = QPushButton(text)
        btn.setObjectName("WebTool")
        btn.setFixedSize(32, 32)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tooltip)
        return btn

    def _shortcuts(self):
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.focus_url)
        QShortcut(QKeySequence("Alt+Left"), self, activated=self._go_back)
        QShortcut(QKeySequence("Alt+Right"), self, activated=self._go_forward)
        QShortcut(QKeySequence("F5"), self, activated=self.reload)
        QShortcut(QKeySequence("Ctrl+0"), self, activated=self._reset_zoom)

    def _build_menu(self):
        self._menu.setStyleSheet(menu_stylesheet())
        act_external = QAction(L.t("web.external"), self)
        act_external.triggered.connect(self._open_external)
        act_copy = QAction(L.t("web.copy_url"), self)
        act_copy.triggered.connect(self._copy_url)
        act_zoom_in = QAction(L.t("web.zoom_in"), self)
        act_zoom_in.triggered.connect(self._zoom_in)
        act_zoom_out = QAction(L.t("web.zoom_out"), self)
        act_zoom_out.triggered.connect(self._zoom_out)
        act_zoom_reset = QAction(L.t("web.zoom_reset"), self)
        act_zoom_reset.triggered.connect(self._reset_zoom)
        act_cache = QAction(L.t("web.clear_cache"), self)
        act_cache.triggered.connect(self._clear_cache)
        self._menu.addAction(act_external)
        self._menu.addAction(act_copy)
        self._menu.addSeparator()
        self._menu.addAction(act_zoom_in)
        self._menu.addAction(act_zoom_out)
        self._menu.addAction(act_zoom_reset)
        self._menu.addSeparator()
        self._menu.addAction(act_cache)

    # -- WebEngine lifecycle ----------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if self._ensure_view() and not self._start_loaded:
            self.go_home()
        self.set_active(True)

    def hideEvent(self, event):
        super().hideEvent(event)
        # QWidget is still "visible" inside hideEvent, so defer the freeze
        # until Qt has actually hidden the view.
        QTimer.singleShot(0, self._freeze_if_hidden)

    def set_active(self, active):
        """Freezes Chromium while the browser tab is in the background.

        QtWebEngine only honours the frozen state once the view is hidden, so
        the freeze is re-applied on the next event-loop turn.  This is the
        single biggest win for launcher responsiveness: an open page keeps
        timers and compositing work alive otherwise.
        """
        if self._page is None:
            return
        self._apply_lifecycle(active)
        if not active:
            QTimer.singleShot(0, self._freeze_if_hidden)

    def _apply_lifecycle(self, active):
        if self._page is None:
            return
        try:
            state = (QWebEnginePage.LifecycleState.Active if active
                     else QWebEnginePage.LifecycleState.Frozen)
            self._page.setLifecycleState(state)
        except Exception:
            pass

    def _freeze_if_hidden(self):
        if self._page is not None and not self.isVisible():
            self._apply_lifecycle(False)

    def _ensure_view(self) -> bool:
        if self._view is not None:
            return True
        if not WEBENGINE_AVAILABLE:
            self._build_fallback()
            return False
        try:
            self._profile = _profile(self.config.get("web_cache", True))
            self._page = DeversWebPage(self._profile, self)
            self._page.setBackgroundColor(QColor(BLACK))
            self._view = QWebEngineView(self)
            self._view.setPage(self._page)
            self._view.setStyleSheet("background-color: #000000;")
            settings = self._view.settings()
            attributes = {
                "JavascriptEnabled": True,
                "JavascriptCanOpenWindows": True,
                "JavascriptCanAccessClipboard": True,
                "LocalStorageEnabled": True,
                "LocalContentCanAccessRemoteUrls": True,
                "FullScreenSupportEnabled": True,
                "PlaybackRequiresUserGesture": True,
                "ErrorPageEnabled": True,
                # Performance: no animated scrolling, and let Chromium use
                # the GPU/canvas pipeline where it is available.
                "ScrollAnimatorEnabled": False,
                "Accelerated2dCanvasEnabled": True,
                "WebGLEnabled": True,
                "DnsPrefetchEnabled": True,
            }
            for attr, value in attributes.items():
                try:
                    settings.setAttribute(
                        getattr(QWebEngineSettings.WebAttribute, attr), value)
                except Exception:
                    pass
            self._view.setZoomFactor(self._zoom)
            self._view.loadStarted.connect(self._on_load_started)
            self._view.loadProgress.connect(self._on_load_progress)
            self._view.loadFinished.connect(self._on_load_finished)
            self._view.urlChanged.connect(self._on_url_changed)
            self._view.renderProcessTerminated.connect(
                self._on_render_terminated)
            self._stack.addWidget(self._view)
            self._stack.setCurrentWidget(self._view)
            return True
        except Exception as e:
            log.exception("Не удалось запустить WebEngine")
            self._build_fallback(str(e))
            return False

    def _build_fallback(self, error=""):
        if self._fallback is not None:
            self._stack.setCurrentWidget(self._fallback)
            return
        self.install_btn = None
        self.restart_btn = None
        self.install_status = None
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(42, 36, 42, 36)
        layout.setSpacing(14)

        eyebrow = QLabel("DEVERS  //  WEB")
        eyebrow.setObjectName("Eyebrow")
        layout.addWidget(eyebrow)

        title = QLabel(L.t("web.offline_title"))
        title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: 900;")
        layout.addWidget(title)

        hint = QLabel(L.t("web.offline_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px; line-height: 19px;")
        layout.addWidget(hint)
        if error:
            detail = QLabel(str(error))
            detail.setWordWrap(True)
            detail.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
            layout.addWidget(detail)

        if not WEBENGINE_AVAILABLE:
            if getattr(sys, "frozen", False):
                note = QLabel(L.t("web.install_unavailable"))
                note.setWordWrap(True)
                note.setStyleSheet(
                    f"color: {TEXT_MUTED}; font-size: 11px; line-height: 18px;")
                layout.addWidget(note)
            else:
                note = QLabel(L.t("web.install_hint"))
                note.setWordWrap(True)
                note.setStyleSheet(
                    f"color: {TEXT_MUTED}; font-size: 11px; line-height: 18px;")
                layout.addWidget(note)

                version = "%d.%d.%d" % sys.version_info[:3]
                version_label = QLabel(
                    L.t("web.install_python", version=version))
                version_label.setStyleSheet(
                    f"color: {TEXT_MUTED}; font-size: 9px;"
                    " letter-spacing: 1px;")
                layout.addWidget(version_label)

                actions = QHBoxLayout()
                actions.setSpacing(8)
                self.install_btn = QPushButton(L.t("web.install").upper())
                self.install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                self.install_btn.setStyleSheet(primary_button_style())
                self.install_btn.clicked.connect(self._install_webengine)
                actions.addWidget(self.install_btn)

                self.restart_btn = QPushButton(L.t("web.restart").upper())
                self.restart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                self.restart_btn.setStyleSheet(primary_button_style())
                self.restart_btn.setToolTip(L.t("web.restart_hint"))
                self.restart_btn.setVisible(False)
                self.restart_btn.clicked.connect(self._restart_launcher)
                actions.addWidget(self.restart_btn)
                actions.addStretch()
                layout.addLayout(actions)

                self.install_status = QLabel("")
                self.install_status.setWordWrap(True)
                self.install_status.setVisible(False)
                self.install_status.setStyleSheet(
                    f"color: {TEXT_MUTED}; font-size: 10px;")
                layout.addWidget(self.install_status)

        row = QHBoxLayout()
        field = QLineEdit()
        field.setPlaceholderText(L.t("web.url_placeholder"))
        go = QPushButton(L.t("web.go"))
        go.setCursor(Qt.CursorShape.PointingHandCursor)
        go.setStyleSheet(secondary_button_style())
        go.clicked.connect(lambda: webbrowser.open(field.text().strip()))
        field.returnPressed.connect(lambda: webbrowser.open(field.text().strip()))
        row.addWidget(field, stretch=1)
        row.addWidget(go)
        layout.addLayout(row)

        for title_key, _desc_key, url in QUICK_LINKS:
            btn = QPushButton(f"{L.t(title_key).upper()}   ↗")
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {TEXT_DIM};"
                f" border: 1px solid {LINE}; padding: 10px 12px;"
                "font-size: 10px; font-weight: 700; letter-spacing: 1px;"
                "text-align: left; }"
                f"QPushButton:hover {{ color: {WHITE}; border-color: {WHITE}; }}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, u=url: webbrowser.open(u))
            layout.addWidget(btn)

        layout.addStretch()
        self._fallback = host
        self._stack.addWidget(host)
        self._stack.setCurrentWidget(host)

    def _install_webengine(self):
        if self.install_btn is None:
            return
        self.install_btn.setEnabled(False)
        self.install_btn.setText(L.t("web.installing").upper())
        if self.install_status is not None:
            self.install_status.setText(L.t("web.installing"))
            self.install_status.setVisible(True)
        task = WebEngineInstallTask()
        task.signals.status.connect(self._on_install_status)
        task.signals.finished.connect(self._on_install_finished)
        self._install_task = task
        QThreadPool.globalInstance().start(task)

    def _on_install_status(self, line):
        if self.install_status is None:
            return
        text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line).strip()
        if len(text) > 180:
            text = "…" + text[-180:]
        self.install_status.setText(text)

    def _on_install_finished(self, ok, error):
        if self.install_btn is None:
            return
        if ok:
            self.install_btn.setVisible(False)
            if self.install_status is not None:
                self.install_status.setText(L.t("web.install_done"))
                self.install_status.setVisible(True)
            if self.restart_btn is not None:
                self.restart_btn.setVisible(True)
        else:
            self.install_btn.setEnabled(True)
            self.install_btn.setText(L.t("web.install").upper())
            if self.install_status is not None:
                self.install_status.setText(
                    L.t("web.install_failed", error=error))
                self.install_status.setVisible(True)

    def _restart_launcher(self):
        try:
            if getattr(sys, "frozen", False):
                args = [sys.executable, *sys.argv[1:]]
                cwd = None
            else:
                script = os.path.abspath(sys.argv[0])
                args = [sys.executable, script, *sys.argv[1:]]
                cwd = os.path.dirname(script) or None
            subprocess.Popen(args, cwd=cwd, close_fds=True)
        except Exception:
            log.exception("Не удалось перезапустить лаунчер")
        QApplication.quit()

    # -- navigation --------------------------------------------------------
    def navigate(self, url_or_text):
        text = str(url_or_text or "").strip()
        if not text or text.lower() in ("devers://start", "about:start"):
            self.go_home()
            return
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", text) and not text.startswith("about:"):
            if (re.match(r"^[\w.-]+\.[a-zA-Z]{2,}([/:?#].*)?$", text)
                    or text.startswith("localhost")):
                text = "https://" + text
            else:
                text = WEB_SEARCH_URL.format(
                    query=urllib.parse.quote_plus(text))
        self.url_bar.setText(text)
        self._showing_start = False
        if not self._ensure_view():
            webbrowser.open(text)
            return
        self._stack.setCurrentWidget(self._view)
        self._view.setUrl(QUrl(text))

    def _navigate_from_bar(self):
        self.navigate(self.url_bar.text())

    def go_home(self):
        self._showing_start = True
        self._start_page_loading = True
        self._start_loaded = True
        self._current_url = ""
        self.url_bar.setText("devers://start")
        self.scheme.setText(L.t("web.status.start"))
        self.scheme.setToolTip(L.t("web.status.start"))
        self.progress.setVisible(False)
        self._update_bookmark_button()
        if not self._ensure_view():
            return
        self._stack.setCurrentWidget(self._view)
        self._view.setHtml(
            start_html(self._home_url, self._recent, self._bookmarks),
            QUrl(self._home_url))
        self._update_nav_buttons()

    def focus_url(self):
        self.url_bar.setFocus()
        self.url_bar.selectAll()

    def _go_back(self):
        if self._view is not None:
            self._view.back()

    def _go_forward(self):
        if self._view is not None:
            self._view.forward()

    def reload(self):
        if self._view is None or self._showing_start:
            self.go_home()
            return
        if self._loading:
            self._view.stop()
        else:
            self._view.reload()

    # -- WebEngine signals -------------------------------------------------
    def _on_load_started(self):
        self._loading = True
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.reload_btn.setText("×")
        self.reload_btn.setToolTip(L.t("web.stop"))
        self._stack.setCurrentWidget(self._view)
        # A real load started after the internal start page finished.  This
        # also catches a link to the configured home URL, where urlChanged()
        # is not emitted because the page URL is already the base URL.
        if self._showing_start and not self._start_page_loading:
            self._showing_start = False
            self._sync_url(self._view.url())

    def _on_load_progress(self, value):
        self.progress.setValue(int(value))

    def _on_load_finished(self, ok):
        self._loading = False
        self.reload_btn.setText("↻")
        self.reload_btn.setToolTip(L.t("web.reload"))
        if self._showing_start:
            # The internal start page has finished loading.  From this point
            # on a real navigation (even to the home URL) must leave start mode.
            self._start_page_loading = False
        if ok:
            QTimer.singleShot(240, lambda: self.progress.setVisible(False))
            if not self._showing_start:
                self._remember(self._current_url)
                self._update_bookmark_button()
            self._update_nav_buttons()
        else:
            self.progress.setVisible(False)
            if not self._showing_start and self._current_url:
                self._show_error()

    def _on_url_changed(self, url):
        text = url.toString()
        if self._showing_start:
            # Ignore the synthetic URL emitted by setHtml() while the start
            # page is loading.  A link to the configured home page is a real
            # navigation, so it must not be filtered out by URL comparison.
            if self._start_page_loading:
                if (not text or text == "about:blank"
                        or text.rstrip("/") == str(self._home_url).rstrip("/")):
                    return
            self._showing_start = False
            self._start_page_loading = False
        self._sync_url(url)

    def _sync_url(self, url):
        """Update the address bar, scheme badge and bookmark state."""
        text = url.toString()
        self._current_url = text
        if text and text != "about:blank":
            self.url_bar.setText(text)
        scheme = url.scheme().lower()
        if scheme == "https":
            label, tip = "HTTPS", L.t("web.status.secure")
        elif scheme == "http":
            label, tip = "HTTP", L.t("web.status.insecure")
        else:
            label, tip = (scheme or "web").upper()[:6], scheme.upper()
        self.scheme.setText(label)
        self.scheme.setToolTip(tip)
        self._update_nav_buttons()
        self._update_bookmark_button()

    def _on_render_terminated(self, status, code):
        log.warning(f"WebEngine renderer stopped: {status} ({code})")
        self.error_title.setText(L.t("web.error_title"))
        self.error_hint.setText(L.t("web.error_hint"))
        self._stack.setCurrentWidget(self.error_page)

    def _show_error(self):
        self.error_title.setText(L.t("web.error_title"))
        self.error_hint.setText(L.t("web.error_hint"))
        self._stack.setCurrentWidget(self.error_page)

    def _retry(self):
        self.navigate(self._current_url or self._home_url)

    # -- small actions -----------------------------------------------------
    def _update_nav_buttons(self):
        history = self._view.history() if self._view is not None else None
        self.back_btn.setEnabled(bool(history and history.canGoBack()))
        self.forward_btn.setEnabled(bool(history and history.canGoForward()))

    def _update_bookmark_button(self):
        current = "" if self._showing_start else self._current_url
        marked = bool(current and current in self._bookmarks)
        self.bookmark_btn.setText("★" if marked else "☆")
        self.bookmark_btn.setToolTip(
            L.t("web.unbookmark") if marked else L.t("web.bookmark"))

    def _queue_save(self):
        """Debounces config writes: browsing should never hit the disk per click."""
        self._save_timer.start()

    def _flush_config(self):
        try:
            self._save_config()
        except Exception:
            pass

    def _toggle_bookmark(self):
        current = "" if self._showing_start else self._current_url
        if not current:
            current = self._home_url
        if current in self._bookmarks:
            self._bookmarks.remove(current)
            message = L.t("toast.bookmark_removed")
        else:
            self._bookmarks.insert(0, current)
            self._bookmarks = self._bookmarks[:12]
            message = L.t("toast.bookmark_added")
        self.config["web_bookmarks"] = list(self._bookmarks)
        self._queue_save()
        self._update_bookmark_button()
        self.status_message.emit(message)
        if self._showing_start:
            self.go_home()

    def _remember(self, url):
        if not url or not url.startswith(("http://", "https://")):
            return
        if url in self._recent:
            self._recent.remove(url)
        self._recent.insert(0, url)
        self._recent = self._recent[:8]
        self.config["web_recent"] = list(self._recent)
        self._queue_save()

    def _copy_url(self):
        target = (self._home_url if self._showing_start else self._current_url)
        QApplication.clipboard().setText(target or self._home_url)
        self.status_message.emit(L.t("web.copied"))

    def _open_external(self):
        target = (self._home_url if self._showing_start else self._current_url)
        webbrowser.open(target or self._home_url)

    def _set_zoom(self, value):
        self._zoom = max(0.5, min(2.0, round(value, 2)))
        if self._view is not None:
            self._view.setZoomFactor(self._zoom)
        self.config["web_zoom"] = self._zoom
        self._queue_save()
        self.status_message.emit(
            L.t("web.zoom", percent=int(self._zoom * 100)))

    def _zoom_in(self):
        self._set_zoom(self._zoom + 0.1)

    def _zoom_out(self):
        self._set_zoom(self._zoom - 0.1)

    def _reset_zoom(self):
        self._set_zoom(1.0)

    def _clear_cache(self):
        clear_web_cache()
        self.status_message.emit(L.t("web.cache_cleared"))

    def apply_config(self, config):
        self.config = config or {}
        self._home_url = self.config.get("web_home") or WEBSITE_URL
        self._recent = list(self.config.get("web_recent", []) or [])
        self._bookmarks = list(self.config.get("web_bookmarks", []) or [])
        zoom = float(self.config.get("web_zoom", 1.0) or 1.0)
        if abs(zoom - self._zoom) > 0.001:
            self._set_zoom(zoom)
        self._update_bookmark_button()
        if self._showing_start:
            self.go_home()

    def shutdown(self):
        try:
            if self._save_timer.isActive():
                self._save_timer.stop()
                self._flush_config()
        except Exception:
            pass
        if self._view is not None:
            try:
                self._view.stop()
                self._view.deleteLater()
            except Exception:
                pass
            self._view = None
        self._page = None

    def sizeHint(self):
        return QSize(960, 640)


# ---------------------------------------------------------------------------
#  Standalone browser window + link routing
# ---------------------------------------------------------------------------
class WebBrowserDialog(QDialog):
    """A full in-app browser window used by modal dialogs and external links.

    It shares the same persistent profile as the Web page, so bookmarks,
    cookies and the cache stay in one place.
    """

    def __init__(self, url="", config=None, save_config=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(L.t("web.title"))
        self.setWindowIcon(QApplication.windowIcon())
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.resize(1080, 720)
        self.setStyleSheet(dialog_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.browser = BrowserPage(config, save_config, compact=True, parent=self)
        self.browser.status_message.connect(self._on_status)
        layout.addWidget(self.browser)

        self._pending_url = str(url or "")
        QTimer.singleShot(0, self._start)

    def _start(self):
        if self._pending_url:
            self.browser.navigate(self._pending_url)
        else:
            self.browser.go_home()

    def _on_status(self, message):
        if message:
            self.setWindowTitle(f"{L.t('web.title')}  ·  {message}")

    def closeEvent(self, event):
        try:
            self.browser.shutdown()
        except Exception:
            pass
        super().closeEvent(event)


_url_handler = None


def set_url_handler(handler):
    """Registers the launcher callback used to open links in-app."""
    global _url_handler
    _url_handler = handler


def _in_app_enabled() -> bool:
    """Reads the live preference from the registered launcher window."""
    owner = getattr(_url_handler, "__self__", None)
    config = getattr(owner, "config", None)
    if isinstance(config, dict):
        return bool(config.get("web_in_app", True))
    return True


def open_url(url, parent=None):
    """Opens *url* inside Devers when possible, otherwise in the OS browser.

    Modal dialogs get their own browser window so the link is still visible;
    the main window simply switches to the Web page.
    """
    target = str(url or "").strip()
    if not target:
        return False

    if not WEBENGINE_AVAILABLE or not _in_app_enabled():
        webbrowser.open(target)
        return False

    # A modal dialog is on top: the main window cannot be used right now.
    try:
        modal = QApplication.activeModalWidget()
    except Exception:
        modal = None
    if modal is not None and not isinstance(modal, WebBrowserDialog):
        try:
            dialog = WebBrowserDialog(target, parent=modal)
            dialog.exec()
            return True
        except Exception as e:
            log.warning(f"In-app browser dialog failed: {e}")
            webbrowser.open(target)
            return False

    if _url_handler is not None:
        try:
            if _url_handler(target) is not False:
                return True
        except Exception as e:
            log.warning(f"In-app browser failed: {e}")

    webbrowser.open(target)
    return False
