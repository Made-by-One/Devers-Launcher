"""Home dashboard: hero banner, live session, stats, recents and studio card."""

import time

from PyQt6.QtCore import (QDate, QDateTime, QLocale, Qt, QThreadPool, QTimer,
                          pyqtSignal)
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QLinearGradient, QPainter,
                         QPixmap)
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMenu, QPushButton,
                             QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from ..covers import CoverLoader
from ..i18n import L
from ..paths import VERSION
from ..theme import (BLACK, LINE, SURFACE_2, SURFACE_3, TEXT_MUTED, TEXT_FAINT,
                     WHITE, draw_corner_ticks, menu_stylesheet,
                     primary_button_style)
from ..utils import clock_time, human_size, human_time
from ..widgets.cards import BADGE_LABELS, CoverImage
from ..widgets.page import Page

RECENT_LIMIT = 4


def _open_link(url):
    """Opens a studio link inside the launcher when possible."""
    from ..web import open_url
    open_url(url)


class HeroBanner(QFrame):
    """Full-width featured banner painted from the game's cover."""

    play_requested = pyqtSignal(str)
    stop_requested = pyqtSignal(str)
    details_requested = pyqtSignal(str)
    favorite_toggled = pyqtSignal(str)
    add_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("Hero")
        self.setFixedHeight(266)
        self.setMinimumWidth(360)
        self._pixmap = None
        self._key = None
        self._name = ""
        self._favorite = False
        self._empty = False
        self._now_playing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 24)
        root.setSpacing(0)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.eyebrow = QLabel("")
        self.eyebrow.setObjectName("Eyebrow")
        top.addWidget(self.eyebrow)
        top.addStretch()
        self.chip = QLabel("")
        self.chip.setStyleSheet(
            "color: #FFFFFF; border: 1px solid rgba(255,255,255,120);"
            "padding: 4px 9px; font-size: 9px; font-weight: 800; letter-spacing: 2px;"
            "background-color: rgba(0,0,0,170);"
        )
        top.addWidget(self.chip)
        root.addLayout(top)
        root.addStretch(1)

        self.name = QLabel("")
        self.name.setStyleSheet("color: #FFFFFF; font-size: 32px; font-weight: 900;")
        self.name.setMinimumWidth(10)
        root.addWidget(self.name)
        root.addSpacing(6)

        self.meta = QLabel("")
        self.meta.setStyleSheet("color: #B4B4B4; font-size: 11px; letter-spacing: 1px;")
        root.addWidget(self.meta)
        root.addSpacing(18)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.play_btn = QPushButton("")
        self.play_btn.setStyleSheet(primary_button_style())
        self.play_btn.setFixedHeight(40)
        self.play_btn.setMinimumWidth(126)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.clicked.connect(self._on_play_clicked)
        self.details_btn = QPushButton(L.t("home.details").upper())
        self.details_btn.setFixedHeight(40)
        self.details_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.details_btn.clicked.connect(
            lambda: self.details_requested.emit(self._key) if self._key else None)
        self.fav_btn = QPushButton()
        self.fav_btn.setFixedSize(40, 40)
        self.fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fav_btn.clicked.connect(
            lambda: self.favorite_toggled.emit(self._key) if self._key else None)
        actions.addWidget(self.play_btn)
        actions.addWidget(self.details_btn)
        actions.addWidget(self.fav_btn)
        actions.addStretch()
        root.addLayout(actions)

    # -- data ------------------------------------------------------------
    def set_game(self, key, name, meta_text, is_favorite=False, eyebrow="",
                 chip="", play_label=None):
        self._key = key
        self._name = name
        self._favorite = is_favorite
        self._empty = False
        self._set_now_playing_state(False)
        self.eyebrow.setText(eyebrow.upper())
        self.chip.setText(chip.upper())
        self.chip.setVisible(bool(chip))
        self.meta.setText(meta_text.upper())
        self.play_btn.setText((play_label or L.t("menu.play")).upper() + "   ▶")
        self._set_fav_icon()
        for w in (self.details_btn, self.fav_btn):
            w.setVisible(True)
        self._update_elided()
        self.update()

    def set_empty(self):
        self._key = None
        self._name = ""
        self._empty = True
        self._pixmap = None
        self._set_now_playing_state(False)
        self.eyebrow.setText(L.t("home.eyebrow").upper())
        self.chip.setText("")
        self.chip.setVisible(False)
        self.name.setText(L.t("home.empty.title").upper())
        self.meta.setText(L.t("home.empty.hint"))
        self.play_btn.setText(L.t("home.add_first").upper() + "   +")
        self.details_btn.setVisible(False)
        self.fav_btn.setVisible(False)
        self.update()

    def set_now_playing(self, elapsed=None):
        if self._empty:
            return
        if elapsed is None:
            self.eyebrow.setText(L.t("home.continue").upper())
            self.chip.setText(L.t("home.featured").upper())
            self.chip.setVisible(True)
            self._set_now_playing_state(False)
        else:
            self.eyebrow.setText(L.t("home.now_playing").upper())
            self.chip.setText(clock_time(elapsed))
            self.chip.setVisible(True)
            self._set_now_playing_state(True)

    def _set_now_playing_state(self, running):
        """Turns the hero action into a real Stop button while a game runs."""
        running = bool(running)
        if running == self._now_playing:
            return
        self._now_playing = running
        if running:
            self.play_btn.setText("■   " + L.t("launch.stop").upper())
            self.play_btn.setToolTip(L.t("launch.stop_game"))
            self.play_btn.setStyleSheet(self._stop_style())
        else:
            self.play_btn.setText(
                (L.t("menu.play") if not self._empty else L.t("home.add_first")).upper()
                + ("   ▶" if not self._empty else "   +"))
            self.play_btn.setToolTip("")
            self.play_btn.setStyleSheet(primary_button_style())

    @staticmethod
    def _stop_style():
        return f"""
            QPushButton {{
                background-color: transparent; color: {WHITE};
                border: 1px solid {WHITE}; padding: 0 20px;
                font-size: 10px; font-weight: 800; letter-spacing: 1px;
            }}
            QPushButton:hover {{ background-color: {WHITE}; color: {BLACK}; }}
            QPushButton:pressed {{ background-color: {SURFACE_3}; color: {WHITE}; }}
        """

    def _on_play_clicked(self):
        if self._empty or not self._key:
            self.add_requested.emit("game")
        elif self._now_playing:
            self.stop_requested.emit(self._key)
        else:
            self.play_requested.emit(self._key)

    def set_cover(self, pixmap):
        self._pixmap = pixmap
        self.update()

    def _set_fav_icon(self):
        self.fav_btn.setText("★" if self._favorite else "☆")
        color = WHITE if self._favorite else "#8A8A8A"
        self.fav_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; color: {color};
                border: 1px solid {LINE}; font-size: 17px; padding: 0;
            }}
            QPushButton:hover {{ color: {WHITE}; border-color: {WHITE}; }}
        """)

    def _update_elided(self):
        if not self._name:
            return
        font = self.name.font()
        font.setPointSize(23)
        font.setWeight(QFont.Weight.Black)
        self.name.setFont(font)
        width = max(120, int(self.width() * 0.62) - 60)
        fm = QFontMetrics(font)
        self.name.setText(fm.elidedText(self._name, Qt.TextElideMode.ElideRight, width))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided()

    # -- painting --------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()
        painter.fillRect(rect, QColor(SURFACE_2))

        if self._pixmap is not None and not self._pixmap.isNull():
            w, h = rect.width(), rect.height()
            scaled = self._pixmap.scaled(
                w, h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            if scaled.width() > w or scaled.height() > h:
                scaled = scaled.copy((scaled.width() - w) // 2,
                                     (scaled.height() - h) // 2, w, h)
            painter.drawPixmap(0, 0, scaled)

            horizontal = QLinearGradient(0, 0, w, 0)
            horizontal.setColorAt(0.0, QColor(0, 0, 0, 250))
            horizontal.setColorAt(0.40, QColor(0, 0, 0, 210))
            horizontal.setColorAt(0.62, QColor(0, 0, 0, 120))
            horizontal.setColorAt(0.85, QColor(0, 0, 0, 20))
            horizontal.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillRect(rect, horizontal)

            vertical = QLinearGradient(0, 0, 0, h)
            vertical.setColorAt(0.0, QColor(0, 0, 0, 30))
            vertical.setColorAt(0.7, QColor(0, 0, 0, 0))
            vertical.setColorAt(1.0, QColor(0, 0, 0, 120))
            painter.fillRect(rect, vertical)
        else:
            # empty / coverless hero: faint oversized wordmark
            painter.setPen(QColor(255, 255, 255, 12))
            big = QFont("Segoe UI", 96, QFont.Weight.Black)
            painter.setFont(big)
            painter.drawText(rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             "✦")

        painter.setPen(QColor(LINE))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        draw_corner_ticks(painter, rect.adjusted(7, 7, -8, -8), color=TEXT_FAINT, size=12)
        painter.end()


class StatTile(QFrame):
    def __init__(self, caption):
        super().__init__()
        self.setObjectName("StatTile")
        self.setFixedHeight(66)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 16, 6)
        layout.setSpacing(2)
        self.value = QLabel("0")
        self.value.setObjectName("BigNumber")
        self.caption = QLabel(caption.upper())
        self.caption.setObjectName("Eyebrow")
        layout.addStretch()
        layout.addWidget(self.value)
        layout.addWidget(self.caption)

    def set_value(self, text):
        self.value.setText(str(text))


class RecentTile(QFrame):
    details_requested = pyqtSignal(str)

    def __init__(self, key, meta, play_time=0):
        super().__init__()
        self.key = key
        self.setObjectName("RecentTile")
        self.setFixedSize(158, 132)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QFrame#RecentTile {{ background-color: {BLACK}; border: 1px solid {LINE}; }}"
            f"QFrame#RecentTile:hover {{ border: 1px solid {WHITE}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.cover = CoverImage()
        self.cover.setFixedSize(156, 88)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setStyleSheet(
            f"background-color: {SURFACE_3}; color: {TEXT_MUTED}; "
            "font-size: 9px; letter-spacing: 2px;"
        )
        self.cover.setText(BADGE_LABELS.get(str(meta.get("type", "")), "GAME"))
        layout.addWidget(self.cover)

        info = QWidget()
        il = QVBoxLayout(info)
        il.setContentsMargins(9, 6, 9, 6)
        il.setSpacing(2)
        name = QLabel()
        name_text = meta.get("name", key)
        fm = QFontMetrics(name.font())
        name.setText(fm.elidedText(name_text, Qt.TextElideMode.ElideRight, 136))
        name.setToolTip(name_text)
        name.setStyleSheet("color: #FFFFFF; font-size: 11px; font-weight: 700; background: transparent;")
        sub = QLabel(human_time(play_time) if play_time else L.t("library.not_played"))
        sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; background: transparent;")
        il.addWidget(name)
        il.addWidget(sub)
        layout.addWidget(info)

        if meta.get("cover_path") or meta.get("cover_url") or meta.get("cover_data"):
            data = None
            if meta.get("cover_data"):
                try:
                    data = bytes.fromhex(meta["cover_data"])
                except Exception:
                    data = None
            loader = CoverLoader(key, meta.get("cover_path", ""), meta.get("cover_url", ""), data)
            loader.signals.loaded.connect(self._on_cover)
            QThreadPool.globalInstance().start(loader)

    def _on_cover(self, key, image):
        if key != self.key or image.isNull():
            return
        self.cover.set_cover_pixmap(QPixmap.fromImage(image))
        self.cover.setText("")

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.details_requested.emit(self.key)
        super().mouseReleaseEvent(event)


class StudioCard(QFrame):
    open_site_requested = pyqtSignal()
    open_page_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("StudioCard")
        self.setFixedWidth(282)
        self.setMinimumHeight(150)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        eyebrow = QLabel(L.t("studio.eyebrow").upper())
        eyebrow.setObjectName("Eyebrow")
        layout.addWidget(eyebrow)

        word = QLabel("MADE BY ONE")
        word.setStyleSheet("color: #FFFFFF; font-size: 17px; font-weight: 900; letter-spacing: 3px;")
        layout.addWidget(word)

        tagline = QLabel(L.t("studio.tagline"))
        tagline.setWordWrap(True)
        tagline.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        layout.addWidget(tagline)

        layout.addSpacing(8)
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        site = QPushButton(L.t("studio.open_site").upper())
        site.setCursor(Qt.CursorShape.PointingHandCursor)
        site.clicked.connect(self.open_site_requested)
        page = QPushButton("→")
        page.setFixedSize(32, 30)
        page.setCursor(Qt.CursorShape.PointingHandCursor)
        page.setToolTip(L.t("studio.title"))
        page.clicked.connect(self.open_page_requested)
        buttons.addWidget(site, stretch=1)
        buttons.addWidget(page)
        layout.addLayout(buttons)

        watermark = QLabel("✦")
        watermark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        watermark.setStyleSheet(
            "color: #161616; font-size: 64px; font-weight: 900; background: transparent;"
        )
        layout.addWidget(watermark, stretch=1)
        layout.addSpacing(4)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {LINE}; border: none;")
        layout.addWidget(divider)

        for name, url in (
            ("Devers Launcher", "https://github.com/Made-by-One/Devers-Launcher"),
            ("Devers Packer", "https://github.com/Made-by-One/Devers-Packer"),
        ):
            link = QPushButton(f"{name.upper()}   ↗")
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {TEXT_MUTED};
                    border: none; padding: 2px 0; text-align: left;
                    font-size: 9px; font-weight: 700; letter-spacing: 1px;
                }}
                QPushButton:hover {{ color: {WHITE}; }}
            """)
            link.clicked.connect(lambda _=False, u=url: _open_link(u))
            layout.addWidget(link)

        self.news = QLabel(f"{L.t('studio.release').upper()}  ·  V{VERSION}")
        self.news.setStyleSheet("color: #FFFFFF; font-size: 10px; font-weight: 700; letter-spacing: 1px;")
        layout.addWidget(self.news)

    def set_news(self, text):
        self.news.setText(text)


class HomePage(Page):
    play_requested = pyqtSignal(str)
    stop_requested = pyqtSignal(str)
    details_requested = pyqtSignal(str)
    favorite_toggled = pyqtSignal(str)
    add_requested = pyqtSignal()
    folder_requested = pyqtSignal()
    steam_requested = pyqtSignal()
    studio_requested = pyqtSignal()
    see_all_requested = pyqtSignal()
    web_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.manifests = {}
        self.stats = {}
        self.favorites = set()
        self._now_key = None
        self._now_started = None
        self._featured_key_value = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(36, 24, 36, 22)
        root.setSpacing(16)

        # --- header ---------------------------------------------------------
        header = QHBoxLayout()
        header.setSpacing(14)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        eyebrow = QLabel(L.t("home.eyebrow").upper())
        eyebrow.setObjectName("Eyebrow")
        title = QLabel(L.t("sidebar.home").upper())
        title.setObjectName("PageTitle")
        titles.addWidget(eyebrow)
        titles.addWidget(title)
        header.addLayout(titles)
        header.addStretch()

        clock_box = QVBoxLayout()
        clock_box.setSpacing(0)
        self.clock = QLabel("--:--")
        self.clock.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.clock.setStyleSheet("color: #FFFFFF; font-size: 17px; font-weight: 900;")
        self.date = QLabel("")
        self.date.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.date.setObjectName("Eyebrow")
        clock_box.addWidget(self.clock)
        clock_box.addWidget(self.date)
        header.addLayout(clock_box)

        self.add_btn = QPushButton("+  " + L.t("home.quick.add").upper())
        self.add_btn.setStyleSheet(primary_button_style())
        self.add_btn.setFixedHeight(34)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self.add_requested)
        self.folder_btn = QPushButton(L.t("home.quick.folder").upper())
        self.folder_btn.setFixedHeight(34)
        self.folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder_btn.clicked.connect(self.folder_requested)
        self.steam_btn = QPushButton(L.t("home.quick.steam").upper())
        self.steam_btn.setFixedHeight(34)
        self.steam_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.steam_btn.clicked.connect(self.steam_requested)
        self.web_btn = QPushButton("⌘  " + L.t("home.quick.web").upper())
        self.web_btn.setObjectName("Ghost")
        self.web_btn.setFixedHeight(34)
        self.web_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.web_btn.setToolTip(L.t("sidebar.web"))
        self.web_btn.clicked.connect(self.web_requested)

        # Keep the header quiet: folder/Steam live in a compact overflow menu.
        self.more_btn = QPushButton("⋯")
        self.more_btn.setObjectName("Ghost")
        self.more_btn.setFixedSize(34, 34)
        self.more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more_btn.setToolTip(L.t("library.more"))
        more_menu = QMenu(self.more_btn)
        more_menu.setStyleSheet(menu_stylesheet())
        more_menu.addAction(L.t("home.quick.folder").upper(), self.folder_requested)
        more_menu.addAction(L.t("home.quick.steam").upper(), self.steam_requested)
        self.more_btn.setMenu(more_menu)

        self.folder_btn.setVisible(False)
        self.steam_btn.setVisible(False)
        for btn in (self.add_btn, self.web_btn, self.more_btn):
            header.addWidget(btn)
        root.addLayout(header)

        # --- hero -----------------------------------------------------------
        self.hero = HeroBanner()
        self.hero.play_requested.connect(self._on_hero_play)
        self.hero.stop_requested.connect(self.stop_requested)
        self.hero.details_requested.connect(self.details_requested)
        self.hero.favorite_toggled.connect(self.favorite_toggled)
        self.hero.add_requested.connect(lambda: self.add_requested.emit())
        root.addWidget(self.hero)

        # --- stats ----------------------------------------------------------
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self.tile_games = StatTile(L.t("home.stats.games"))
        self.tile_time = StatTile(L.t("home.stats.playtime"))
        self.tile_favs = StatTile(L.t("home.stats.favorites"))
        self.tile_disk = StatTile(L.t("home.stats.disk"))
        for tile in (self.tile_games, self.tile_time, self.tile_favs, self.tile_disk):
            stats_row.addWidget(tile, stretch=1)
        root.addLayout(stats_row)

        # --- recent + studio -------------------------------------------------
        bottom = QHBoxLayout()
        bottom.setSpacing(16)

        recent_col = QVBoxLayout()
        recent_col.setSpacing(8)
        recent_head = QHBoxLayout()
        recent_title = QLabel(L.t("home.recent").upper())
        recent_title.setObjectName("SectionTitle")
        recent_head.addWidget(recent_title)
        recent_head.addStretch()
        self.see_all_btn = QPushButton(L.t("home.see_all").upper() + "  →")
        self.see_all_btn.setObjectName("Ghost")
        self.see_all_btn.setFixedHeight(26)
        self.see_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.see_all_btn.clicked.connect(self.see_all_requested)
        self.see_all_btn.setVisible(False)
        recent_head.addWidget(self.see_all_btn)
        recent_col.addLayout(recent_head)

        self.recent_scroll = QScrollArea()
        self.recent_scroll.setWidgetResizable(False)
        self.recent_scroll.setFixedHeight(142)
        self.recent_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.recent_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.recent_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:horizontal { background: transparent; height: 4px; margin: 0; }"
            "QScrollBar::handle:horizontal { background: #2E2E2E; min-width: 30px; }"
            "QScrollBar::add-line, QScrollBar::sub-line { width: 0px; height: 0px; }"
        )
        self.recent_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.recent_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.recent_host = QWidget()
        self.recent_host.setStyleSheet("background: transparent;")
        self.recent_layout = QHBoxLayout(self.recent_host)
        self.recent_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_layout.setSpacing(10)
        self.recent_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.recent_scroll.setWidget(self.recent_host)
        recent_col.addWidget(self.recent_scroll)

        self.recent_empty = QLabel(L.t("home.recent_empty"))
        self.recent_empty.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        recent_col.addWidget(self.recent_empty)
        recent_col.addStretch()
        bottom.addLayout(recent_col, stretch=1)

        self.studio_card = StudioCard()
        self.studio_card.open_site_requested.connect(self._open_site)
        self.studio_card.open_page_requested.connect(self.studio_requested)
        bottom.addWidget(self.studio_card)
        root.addLayout(bottom, stretch=1)

        self.ticker = QTimer(self)
        self.ticker.setInterval(1000)
        self.ticker.timeout.connect(self._tick)
        self.ticker.start()

        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(15000)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start()
        self._update_clock()

        self.hero.set_empty()

    # -- clock -----------------------------------------------------------
    def _update_clock(self):
        locale = QLocale(L.current_lang)
        self.clock.setText(locale.toString(QDateTime.currentDateTime(), "HH:mm"))
        self.date.setText(locale.toString(QDate.currentDate(), "ddd d MMM").upper())

    def _open_site(self):
        from ..paths import WEBSITE_URL
        _open_link(WEBSITE_URL)

    # -- data ------------------------------------------------------------
    def update_library(self, manifests, stats, favorites, temp_size=0):
        self.manifests = manifests or {}
        self.stats = stats or {}
        self.favorites = set(favorites or [])

        play_times = self.stats.get("play_times", {})
        launch_counts = self.stats.get("launch_counts", {})
        last_played = self.stats.get("last_played", {})

        total_time = sum(play_times.values())
        total_size = sum(int(m.get("size", 0) or 0) for m in self.manifests.values())
        fav_count = sum(1 for k in self.manifests if k in self.favorites)

        self.tile_games.set_value(len(self.manifests))
        self.tile_time.set_value(human_time(total_time) if total_time else "0m")
        self.tile_favs.set_value(fav_count)
        self.tile_disk.set_value(human_size(total_size))

        if not self.manifests:
            self._featured_key_value = None
            self.hero.set_empty()
        else:
            featured = self._featured_key_value
            if featured not in self.manifests:
                featured = self._pick_featured(last_played)
            self._show_hero(featured, play_times, launch_counts)
        self.studio_card.set_news(f"{L.t('studio.release').upper()}  ·  V{VERSION}")

        self._build_recent(last_played, play_times)
        if self._now_key and self._now_key in self.manifests:
            self._apply_now_playing()

    def _pick_featured(self, last_played):
        candidates = [k for k in last_played if k in self.manifests]
        if candidates:
            return max(candidates, key=lambda k: last_played.get(k, 0))
        by_date = sorted(self.manifests.items(),
                         key=lambda kv: kv[1].get("mtime", 0), reverse=True)
        return by_date[0][0] if by_date else None

    def _show_hero(self, key, play_times, launch_counts):
        if not key:
            self.hero.set_empty()
            return
        self._featured_key_value = key
        meta = self.manifests.get(key, {})
        name = meta.get("name", key)
        kind = BADGE_LABELS.get(str(meta.get("type", "")), "GAME")
        parts = [kind, human_size(meta.get("size", 0))]
        if play_times.get(key):
            parts.append(human_time(play_times[key]))
        elif launch_counts.get(key):
            parts.append(L.t("home.launches", count=launch_counts[key]))
        else:
            parts.append(L.t("library.not_played"))
        played = bool(play_times.get(key))
        self.hero.set_game(
            key, name, "   ·   ".join(parts),
            is_favorite=key in self.favorites,
            eyebrow=L.t("home.continue") if played else L.t("home.featured"),
            chip=L.t("home.featured") if played else "",
        )
        if key == self._now_key:
            self._apply_now_playing()
        self._load_hero_cover(key, meta)

    def _load_hero_cover(self, key, meta):
        self.hero.set_cover(None)
        if not (meta.get("cover_path") or meta.get("cover_url") or meta.get("cover_data")):
            return
        data = None
        if meta.get("cover_data"):
            try:
                data = bytes.fromhex(meta["cover_data"])
            except Exception:
                data = None
        loader = CoverLoader("hero:" + key, meta.get("cover_path", ""),
                             meta.get("cover_url", ""), data)
        loader.signals.loaded.connect(
            lambda k, img: self._on_hero_cover(key, img))
        QThreadPool.globalInstance().start(loader)

    def _on_hero_cover(self, key, image):
        if key != self._featured_key_value or image.isNull():
            return
        self.hero.set_cover(QPixmap.fromImage(image))

    def _build_recent(self, last_played, play_times):
        while self.recent_layout.count():
            item = self.recent_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        keys = [k for k in last_played if k in self.manifests]
        keys.sort(key=lambda k: last_played.get(k, 0), reverse=True)
        if not keys:
            keys = [k for k, _ in sorted(self.manifests.items(),
                                         key=lambda kv: kv[1].get("mtime", 0),
                                         reverse=True)]
        keys = keys[:RECENT_LIMIT]

        self.recent_empty.setVisible(not keys)
        self.see_all_btn.setVisible(bool(keys))
        for key in keys:
            tile = RecentTile(key, self.manifests[key], play_times.get(key, 0))
            tile.details_requested.connect(self.details_requested)
            self.recent_layout.addWidget(tile)

        count = len(keys)
        self.recent_host.setFixedSize(
            max(150, count * 158 + max(0, count - 1) * 10), 134)

    # -- live session -----------------------------------------------------
    def set_now_playing(self, key, started_at=None):
        self._now_key = key
        self._now_started = started_at
        if key in self.manifests:
            self._featured_key_value = key
            meta = self.manifests.get(key, {})
            play_times = self.stats.get("play_times", {})
            launch_counts = self.stats.get("launch_counts", {})
            parts = [BADGE_LABELS.get(str(meta.get("type", "")), "GAME"),
                     human_size(meta.get("size", 0))]
            if play_times.get(key):
                parts.append(human_time(play_times[key]))
            self.hero.set_game(
                key, meta.get("name", key), "   ·   ".join(parts),
                is_favorite=key in self.favorites,
                eyebrow=L.t("home.now_playing"),
                chip=clock_time(0),
            )
            self._load_hero_cover(key, meta)
            self._apply_now_playing()

    def clear_now_playing(self):
        self._now_key = None
        self._now_started = None
        self.hero._set_now_playing_state(False)
        self.update_library(self.manifests, self.stats, self.favorites)

    def set_running(self, running):
        """Keeps the hero action in sync with the live session state."""
        self.hero._set_now_playing_state(bool(running) and bool(self._now_key))

    def _apply_now_playing(self):
        if not self._now_key or not self._now_started:
            return
        elapsed = time.time() - self._now_started
        self.hero.set_now_playing(elapsed)

    def _tick(self):
        if self._now_key and self._now_started:
            self._apply_now_playing()

    def _on_hero_play(self, key):
        if key:
            self.play_requested.emit(key)
        else:
            self.add_requested.emit()
