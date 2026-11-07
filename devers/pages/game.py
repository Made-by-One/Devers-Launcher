"""Full game page: hero, stats, Steam achievements, screenshots and videos."""

import os
import time
from datetime import datetime

from PyQt6.QtCore import QSize, Qt, QThreadPool, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QLinearGradient, QPainter,
                         QPixmap)
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel,
                             QProgressBar, QPushButton, QScrollArea,
                             QSizePolicy, QVBoxLayout, QWidget)

from ..covers import CoverLoader
from ..i18n import L
from ..steam import find_steam_path
from ..steam_info import SteamInfoTask, steam_language
from ..theme import (BLACK, LINE, LINE_STRONG, SURFACE_2, SURFACE_3, TEXT,
                     TEXT_DIM, TEXT_FAINT, TEXT_MUTED, WHITE,
                     primary_button_style)
from ..utils import get_icon, human_size, human_time
from ..widgets.media import MediaViewer
from ..widgets.page import Page

STEAM_BADGE = "STEAM"
ACHIEVEMENT_RENDER_LIMIT = 240


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
            continue
        child = item.layout()
        if child is not None:
            _clear_layout(child)


def _micro(text, color=TEXT_MUTED):
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {color}; font-size: 9px; font-weight: 700; letter-spacing: 2px;"
        "background: transparent;")
    return label


def _pretty_date(timestamp):
    if not timestamp:
        return L.t("game.never")
    try:
        return datetime.fromtimestamp(float(timestamp)).strftime("%d.%m.%Y")
    except (TypeError, ValueError, OSError):
        return L.t("game.never")


class GameHero(QFrame):
    """Wide cover banner with a left-to-right black scrim."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self.setFixedHeight(248)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 24)
        layout.setSpacing(6)
        layout.addStretch(1)

        self.eyebrow = _micro("", WHITE)
        self.title = QLabel("")
        self.title.setWordWrap(False)
        self.title.setStyleSheet(
            "color: #FFFFFF; font-size: 34px; font-weight: 900;"
            "letter-spacing: -1px; background: transparent;")
        self.meta = QLabel("")
        self.meta.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 11px; background: transparent;")
        self.genres = QLabel("")
        self.genres.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; letter-spacing: 1px;"
            "background: transparent;")

        layout.addWidget(self.eyebrow)
        layout.addWidget(self.title)
        layout.addWidget(self.meta)
        layout.addWidget(self.genres)

        self._full_title = ""

    def set_cover(self, pixmap):
        self._pixmap = pixmap
        self.update()

    def set_title(self, text):
        self._full_title = text or ""
        self._elide_title()

    def _elide_title(self):
        if not self._full_title:
            return
        font = self.title.font()
        font.setPointSize(24)
        font.setWeight(QFont.Weight.Black)
        self.title.setFont(font)
        width = max(160, self.width() - 80)
        fm = QFontMetrics(font)
        self.title.setText(fm.elidedText(
            self._full_title, Qt.TextElideMode.ElideRight, width))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide_title()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()
        painter.fillRect(rect, QColor(SURFACE_2))

        if self._pixmap is not None and not self._pixmap.isNull():
            w, h = rect.width(), rect.height()
            scaled = self._pixmap.scaled(
                w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            if scaled.width() > w or scaled.height() > h:
                scaled = scaled.copy((scaled.width() - w) // 2,
                                     (scaled.height() - h) // 2, w, h)
            painter.drawPixmap(0, 0, scaled)

            horizontal = QLinearGradient(0, 0, w, 0)
            horizontal.setColorAt(0.0, QColor(0, 0, 0, 248))
            horizontal.setColorAt(0.46, QColor(0, 0, 0, 214))
            horizontal.setColorAt(0.72, QColor(0, 0, 0, 120))
            horizontal.setColorAt(1.0, QColor(0, 0, 0, 40))
            painter.fillRect(rect, horizontal)

            bottom = QLinearGradient(0, h * 0.45, 0, h)
            bottom.setColorAt(0.0, QColor(0, 0, 0, 0))
            bottom.setColorAt(1.0, QColor(0, 0, 0, 190))
            painter.fillRect(rect, bottom)

        painter.setPen(QColor(LINE))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.end()
        super().paintEvent(event)


class StatTile(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("GameStat")
        self.setFixedHeight(56)
        self.setStyleSheet(
            "QFrame#GameStat { background-color: transparent; border: none; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 14, 6)
        layout.setSpacing(1)
        self.value = QLabel("—")
        self.value.setStyleSheet(
            "color: #FFFFFF; font-size: 20px; font-weight: 900;"
            "letter-spacing: -0.5px; background: transparent;")
        self.label = _micro(title)
        layout.addWidget(self.value)
        layout.addWidget(self.label)

    def set_value(self, value):
        self.value.setText(str(value))


class ImageTile(QLabel):
    """Square-ish clickable image with a cover-cache loader."""

    clicked = pyqtSignal()

    def __init__(self, key, path="", url="", width=246, height=138, parent=None):
        super().__init__(parent)
        self._key = key
        self._hover = False
        self.setFixedSize(width, height)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"background-color: {SURFACE_3}; border: 1px solid {LINE};"
            f" color: {TEXT_MUTED}; font-size: 9px;")
        if path or url:
            loader = CoverLoader(key, path or "", url or "")
            loader.signals.loaded.connect(self._on_loaded)
            QThreadPool.globalInstance().start(loader)

    def enterEvent(self, event):
        self._hover = True
        self.setStyleSheet(
            f"background-color: {SURFACE_3}; border: 1px solid {WHITE};"
            f" color: {TEXT_MUTED}; font-size: 9px;")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.setStyleSheet(
            f"background-color: {SURFACE_3}; border: 1px solid {LINE};"
            f" color: {TEXT_MUTED}; font-size: 9px;")
        super().leaveEvent(event)

    def _on_loaded(self, key, image):
        if key != self._key or image.isNull():
            return
        pixmap = QPixmap.fromImage(image)
        pixmap = pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation)
        if pixmap.width() > self.width() or pixmap.height() > self.height():
            pixmap = pixmap.copy(
                (pixmap.width() - self.width()) // 2,
                (pixmap.height() - self.height()) // 2,
                self.width(), self.height())
        self.setPixmap(pixmap)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class VideoTile(QFrame):
    clicked = pyqtSignal()

    def __init__(self, key, thumb, title, width=300, parent=None,
                 thumb_path=""):
        super().__init__(parent)
        self.setObjectName("VideoTile")
        self.setStyleSheet(
            f"QFrame#VideoTile {{ background-color: {SURFACE_2};"
            f" border: 1px solid {LINE}; }}"
            f"QFrame#VideoTile:hover {{ border-color: {WHITE}; }}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(width)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.image = ImageTile(
            key, thumb_path, "" if thumb_path else thumb,
            width, int(width * 9 / 16))
        self.image.clicked.connect(self.clicked)
        layout.addWidget(self.image)

        play = QLabel("▶", self.image)
        play.setStyleSheet(
            "color: #FFFFFF; font-size: 18px; background: transparent;")
        play.move(width // 2 - 8, int(width * 9 / 16) // 2 - 14)
        play.show()

        caption = QLabel(title or "")
        caption.setWordWrap(True)
        caption.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 10px; padding: 8px 10px;"
            "background: transparent;")
        layout.addWidget(caption)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class AchievementRow(QFrame):
    def __init__(self, achievement, parent=None):
        super().__init__(parent)
        self.setObjectName("AchievementRow")
        self.setStyleSheet(
            f"QFrame#AchievementRow {{ background: transparent;"
            f" border-bottom: 1px solid {LINE}; }}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 9, 0, 9)
        layout.setSpacing(12)

        self.icon = QLabel()
        self.icon.setFixedSize(34, 34)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setStyleSheet(f"background-color: {SURFACE_3}; border: 1px solid {LINE};")
        layout.addWidget(self.icon)

        text = QVBoxLayout()
        text.setSpacing(1)
        name = QLabel(achievement.get("name") or achievement.get("api_name", ""))
        name.setStyleSheet(
            "color: #FFFFFF; font-size: 12px; font-weight: 700; background: transparent;")
        description = achievement.get("description", "")
        if not description and achievement.get("hidden"):
            description = L.t("game.hidden_achievement")
        desc = QLabel(description or "")
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;")
        text.addWidget(name)
        text.addWidget(desc)
        layout.addLayout(text, stretch=1)

        percent = achievement.get("percent")
        value = int(round(percent)) if percent is not None else 0
        right = QVBoxLayout()
        right.setSpacing(3)
        pct = QLabel(f"{value}%" if percent is not None else "—")
        pct.setAlignment(Qt.AlignmentFlag.AlignRight)
        pct.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 10px; font-weight: 700; background: transparent;")
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(max(0, min(100, value)))
        bar.setFixedSize(88, 3)
        bar.setTextVisible(False)
        bar.setStyleSheet(
            f"QProgressBar {{ background-color: {SURFACE_3}; border: none; }}"
            f"QProgressBar::chunk {{ background-color: {WHITE}; }}")
        right.addWidget(pct)
        right.addWidget(bar)
        layout.addLayout(right)

        icon = achievement.get("icon", "")
        if icon:
            loader = CoverLoader(f"ach:{icon}", "", icon)
            loader.signals.loaded.connect(self._on_icon)
            QThreadPool.globalInstance().start(loader)

    def _on_icon(self, _key, image):
        if image.isNull():
            return
        self.icon.setPixmap(QPixmap.fromImage(image).scaled(
            32, 32, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))


class GameDetailPage(Page):
    """One game, one page.  Opened as a tab from the library."""

    play_requested = pyqtSignal(str)
    stop_requested = pyqtSignal(str)
    favorite_toggled = pyqtSignal(str)
    folder_requested = pyqtSignal(str)
    web_requested = pyqtSignal(str)
    close_requested = pyqtSignal(str)
    back_requested = pyqtSignal(str)

    def __init__(self, key, meta, config, stats, is_favorite=False, parent=None):
        super().__init__(parent)
        self.key = key
        self.meta = dict(meta or {})
        self.config = config or {}
        self.stats = stats or {}
        self._favorite = bool(is_favorite)
        self._steam_payload = None
        self._steam_task = None
        self._achievements = []
        self._show_all_achievements = False
        self._is_steam = bool(self.meta.get("appid")) or self.meta.get("type") == "steam"
        self._running = False
        self._viewer = None
        self._shot_items = []
        self._video_items = []
        self._show_all_shots = False
        self._show_all_videos = False
        self._user_media = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        outer.addWidget(scroll, stretch=1)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(36, 22, 36, 28)
        root.setSpacing(18)

        self.hero = GameHero()
        root.addWidget(self.hero)

        self.status = _micro("")
        self.status.setVisible(False)
        root.addWidget(self.status)

        # --- stats ---------------------------------------------------------
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self.stat_playtime = StatTile(L.t("game.playtime"))
        self.stat_launches = StatTile(L.t("game.launches"))
        self.stat_last = StatTile(L.t("game.last_played"))
        self.stat_fourth = StatTile(
            L.t("game.achievements") if self._is_steam else L.t("game.size"))
        for tile in (self.stat_playtime, self.stat_launches,
                     self.stat_last, self.stat_fourth):
            stats_row.addWidget(tile, stretch=1)
        root.addLayout(stats_row)

        # --- about + details ----------------------------------------------
        split = QHBoxLayout()
        split.setSpacing(18)

        left = QVBoxLayout()
        left.setSpacing(10)
        about_box, self.about_body = self._section(L.t("game.about"))
        self.about_label = QLabel("")
        self.about_label.setWordWrap(True)
        self.about_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.about_label.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 12px; background: transparent;")
        self.about_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.about_body.addWidget(self.about_label)
        left.addWidget(about_box)
        split.addLayout(left, stretch=2)

        right = QVBoxLayout()
        right.setSpacing(10)
        details_box, self.details_body = self._section(L.t("game.details"))
        self.details_card = QFrame()
        self.details_card.setObjectName("GameDetails")
        self.details_card.setStyleSheet(
            "QFrame#GameDetails { background: transparent; border: none; }")
        self.details_layout = QVBoxLayout(self.details_card)
        self.details_layout.setContentsMargins(0, 0, 0, 0)
        self.details_layout.setSpacing(0)
        self.details_body.addWidget(self.details_card)
        right.addWidget(details_box)
        right.addStretch(1)
        split.addLayout(right, stretch=1)
        root.addLayout(split)

        # --- achievements --------------------------------------------------
        self.ach_box, self.ach_body = self._section(L.t("game.achievements"))
        self.ach_box.setVisible(self._is_steam)
        self.ach_body.setSpacing(0)
        root.addWidget(self.ach_box)

        # --- screenshots ---------------------------------------------------
        self.shots_box, self.shots_body = self._section(L.t("game.screenshots"))
        self.shots_box.setVisible(self._is_steam)
        root.addWidget(self.shots_box)

        # --- videos --------------------------------------------------------
        self.videos_box, self.videos_body = self._section(L.t("game.videos"))
        self.videos_box.setVisible(self._is_steam)
        root.addWidget(self.videos_box)

        self._populate_local()
        if self._is_steam:
            self.status.setText(L.t("game.steam_loading"))
            self.status.setVisible(True)
            self._start_steam()

    # ------------------------------------------------------------------
    #  Layout helpers
    # ------------------------------------------------------------------
    def _build_header(self):
        bar = QFrame()
        bar.setObjectName("GameHeader")
        bar.setFixedHeight(54)
        bar.setStyleSheet(
            f"QFrame#GameHeader {{ background-color: {SURFACE_2};"
            f" border-bottom: 1px solid {LINE}; }}")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 9, 18, 9)
        layout.setSpacing(8)

        back = QPushButton("←")
        back.setFixedSize(34, 34)
        back.setToolTip(L.t("game.back"))
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.setStyleSheet(self._tool_style())
        back.clicked.connect(lambda: self.back_requested.emit(self.key))
        layout.addWidget(back)

        crumb = _micro(f"{L.t('sidebar.library').upper()}   /   {L.t('game.eyebrow').upper()}")
        layout.addWidget(crumb)
        layout.addStretch()

        self.fav_btn = QPushButton()
        self.fav_btn.setFixedSize(34, 34)
        self.fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fav_btn.clicked.connect(lambda: self.favorite_toggled.emit(self.key))
        layout.addWidget(self.fav_btn)
        self._render_favorite()

        folder = QPushButton()
        folder.setFixedSize(34, 34)
        folder.setToolTip(L.t("menu.open_folder"))
        folder.setCursor(Qt.CursorShape.PointingHandCursor)
        icon = get_icon("folder", 15)
        if icon is not None:
            folder.setIcon(icon)
            folder.setIconSize(QSize(15, 15))
        else:
            folder.setText("▣")
        folder.setStyleSheet(self._tool_style())
        folder.clicked.connect(lambda: self.folder_requested.emit(self.key))
        layout.addWidget(folder)

        self.play_btn = QPushButton("▶   " + L.t("game.play").upper())
        self.play_btn.setFixedHeight(34)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.setStyleSheet(primary_button_style())
        self.play_btn.clicked.connect(self._on_play_clicked)
        layout.addWidget(self.play_btn)
        return bar

    def _on_play_clicked(self):
        if self._running:
            self.stop_requested.emit(self.key)
        else:
            self.play_requested.emit(self.key)

    @staticmethod
    def _stop_style():
        return f"""
            QPushButton {{
                background-color: transparent; color: {WHITE};
                border: 1px solid {WHITE}; padding: 9px 16px;
                font-size: 10px; font-weight: 800; letter-spacing: 1px;
            }}
            QPushButton:hover {{ background-color: {WHITE}; color: {BLACK}; }}
            QPushButton:pressed {{ background-color: {SURFACE_3}; color: {WHITE}; }}
        """

    def set_running(self, running):
        """Switches the header action between Play and Stop."""
        running = bool(running)
        if running == self._running:
            return
        self._running = running
        if running:
            self.play_btn.setText("■   " + L.t("launch.stop").upper())
            self.play_btn.setToolTip(L.t("launch.stop_game"))
            self.play_btn.setStyleSheet(self._stop_style())
        else:
            self.play_btn.setText("▶   " + L.t("game.play").upper())
            self.play_btn.setToolTip("")
            self.play_btn.setStyleSheet(primary_button_style())

    def shutdown(self):
        """Releases the media window when the tab is closed."""
        if self._viewer is not None:
            try:
                self._viewer.shutdown()
            except Exception:
                pass
            self._viewer = None

    @staticmethod
    def _tool_style():
        return f"""
            QPushButton {{
                background-color: transparent; color: {TEXT_DIM};
                border: 1px solid {LINE}; padding: 0;
                font-size: 15px; font-weight: 600;
            }}
            QPushButton:hover {{ color: {WHITE}; border-color: {WHITE}; }}
        """

    def _render_favorite(self):
        self.fav_btn.setText("★" if self._favorite else "☆")
        self.fav_btn.setToolTip(
            L.t("card.unfavorite") if self._favorite else L.t("card.favorite"))
        color = WHITE if self._favorite else TEXT_MUTED
        self.fav_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; color: {color};
                border: 1px solid {LINE}; font-size: 16px; padding: 0;
            }}
            QPushButton:hover {{ color: {WHITE}; border-color: {WHITE}; }}
        """)

    def _section(self, title):
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)
        label = QLabel(title.upper())
        label.setStyleSheet(
            f"color: {WHITE}; font-size: 10px; font-weight: 800;"
            "letter-spacing: 3px; background: transparent;")
        head.addWidget(label)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {LINE}; border: none;")
        head.addWidget(line, stretch=1)
        layout.addLayout(head)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)
        body.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addLayout(body)
        return box, body

    def _placeholder(self, text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        return label

    def _detail_row(self, title, value):
        row = QFrame()
        row.setObjectName("DetailRow")
        row.setStyleSheet(
            f"QFrame#DetailRow {{ background: transparent;"
            f" border-bottom: 1px solid {LINE}; }}")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 9, 0, 9)
        layout.setSpacing(10)
        key = _micro(title)
        key.setFixedWidth(94)
        val = QLabel(value or "—")
        val.setWordWrap(True)
        val.setStyleSheet(
            f"color: {TEXT}; font-size: 11px; background: transparent;")
        layout.addWidget(key, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(val, stretch=1)
        self.details_layout.addWidget(row)

    # ------------------------------------------------------------------
    #  Local data
    # ------------------------------------------------------------------
    def _populate_local(self):
        meta = self.meta
        name = meta.get("name", self.key)
        badge = STEAM_BADGE if self._is_steam else str(meta.get("type", "GAME")).upper()
        self.hero.eyebrow.setText(badge)
        self.hero.set_title(name)
        self.hero.meta.setText(self._hero_meta())
        self.hero.genres.setText("")

        cover_path = meta.get("cover_path", "")
        cover_url = meta.get("cover_url", "")
        cover_data = None
        if meta.get("cover_data"):
            try:
                cover_data = bytes.fromhex(meta["cover_data"])
            except Exception:
                cover_data = None
        if cover_path or cover_url or cover_data:
            loader = CoverLoader(f"hero:{self.key}", cover_path, cover_url, cover_data)
            loader.signals.loaded.connect(self._on_hero_cover)
            QThreadPool.globalInstance().start(loader)

        self._update_stats()
        self._render_details({})
        self.about_label.setText(L.t("game.no_description"))

    def _hero_meta(self):
        meta = self.meta
        parts = []
        if meta.get("size"):
            parts.append(human_size(meta.get("size", 0)))
        release = (self._steam_payload or {}).get("store", {}).get("release_date")
        if release:
            parts.append(release)
        return "   ·   ".join(parts)

    def _update_stats(self):
        play_times = self.stats.get("play_times", {})
        launch_counts = self.stats.get("launch_counts", {})
        last_played = self.stats.get("last_played", {})
        play_time = play_times.get(self.key, 0)
        launches = launch_counts.get(self.key, 0)
        self.stat_playtime.set_value(
            human_time(play_time) if play_time else L.t("game.no_time"))
        self.stat_launches.set_value(str(launches))
        self.stat_last.set_value(_pretty_date(last_played.get(self.key)))
        if self._is_steam:
            total = len(self._achievements)
            self.stat_fourth.set_value(str(total) if total else "—")
        else:
            self.stat_fourth.set_value(human_size(self.meta.get("size", 0)))

    def _on_hero_cover(self, _key, image):
        if not image.isNull():
            self.hero.set_cover(QPixmap.fromImage(image))

    def _render_details(self, store):
        _clear_layout(self.details_layout)
        store = store or {}
        rows = [
            (L.t("game.release"), store.get("release_date") or "—"),
            (L.t("game.developer"), ", ".join(store.get("developers") or []) or "—"),
            (L.t("game.publisher"), ", ".join(store.get("publishers") or []) or "—"),
            (L.t("game.genres"), ", ".join(store.get("genres") or []) or "—"),
        ]
        if store.get("metacritic"):
            rows.append((L.t("game.metacritic"), str(store["metacritic"])))
        if not self._is_steam:
            rows = [
                (L.t("game.type"), str(self.meta.get("type", "game")).upper()),
                (L.t("game.size"), human_size(self.meta.get("size", 0))),
                (L.t("game.path"), self.meta.get("path", "") or "—"),
            ]
        for title, value in rows:
            self._detail_row(title, value)
        if store.get("store_url"):
            link = QPushButton(L.t("game.open_store").upper())
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.setStyleSheet(self._ghost_style())
            link.clicked.connect(
                lambda _=False, url=store["store_url"]: self.web_requested.emit(url))
            self.details_layout.addWidget(link)
        self.details_layout.addStretch(1)

    @staticmethod
    def _ghost_style():
        return f"""
            QPushButton {{
                background-color: transparent; color: {TEXT_DIM};
                border: 1px solid {LINE}; padding: 8px 12px;
                font-size: 9px; font-weight: 700; letter-spacing: 1px;
            }}
            QPushButton:hover {{ color: {WHITE}; border-color: {WHITE}; }}
        """

    # ------------------------------------------------------------------
    #  Steam data
    # ------------------------------------------------------------------
    def _start_steam(self):
        appid = str(self.meta.get("appid") or self.key.split(":")[-1])
        if not appid.isdigit():
            self.status.setVisible(False)
            return
        steam_path = find_steam_path(self.config.get("steam_path", ""))
        task = SteamInfoTask(self.key, appid, steam_language(), steam_path)
        task.signals.loaded.connect(self._on_steam_loaded)
        task.signals.failed.connect(self._on_steam_failed)
        self._steam_task = task
        QThreadPool.globalInstance().start(task)

    def _on_steam_loaded(self, key, payload):
        if key != self.key:
            return
        self._steam_payload = payload or {}
        store = self._steam_payload.get("store") or {}
        achievements = self._steam_payload.get("achievements") or {}
        self._achievements = list(achievements.get("achievements") or [])
        self._user_media = self._steam_payload.get("user_media") or {}
        if not self._user_media.get("screenshots"):
            self._user_media["screenshots"] = \
                self._steam_payload.get("local_screenshots") or []

        self.status.setVisible(False)
        self.hero.meta.setText(self._hero_meta())
        if store.get("genres"):
            self.hero.genres.setText("  /  ".join(store["genres"]))

        if (self.hero._pixmap is None or self.hero._pixmap.isNull()) \
                and store.get("header_image"):
            loader = CoverLoader(f"hero-steam:{self.key}", "", store["header_image"])
            loader.signals.loaded.connect(self._on_hero_cover)
            QThreadPool.globalInstance().start(loader)

        about = store.get("about") or store.get("short_description") or ""
        self.about_label.setText(about or L.t("game.no_description"))
        self._render_details(store)
        self._render_achievements()
        self._render_screenshots()
        self._render_videos(store.get("movies") or [])
        self._update_stats()

    def _on_steam_failed(self, key, error):
        if key != self.key:
            return
        self.status.setText(L.t("game.steam_error"))
        self.status.setVisible(True)
        self.about_label.setText(L.t("game.no_description"))
        _clear_layout(self.ach_body)
        self.ach_body.addWidget(self._placeholder(L.t("game.no_achievements")))
        _clear_layout(self.shots_body)
        self.shots_body.addWidget(self._placeholder(L.t("game.no_screenshots")))
        _clear_layout(self.videos_body)
        self.videos_body.addWidget(self._placeholder(L.t("game.no_videos")))
        self._update_stats()

    def _render_achievements(self):
        _clear_layout(self.ach_body)
        self.ach_body.setSpacing(0)
        if not self._achievements:
            self.ach_body.addWidget(self._placeholder(L.t("game.no_achievements")))
            return

        values = [a.get("percent") for a in self._achievements
                  if a.get("percent") is not None]
        average = round(sum(values) / len(values), 1) if values else 0

        summary = QWidget()
        summary.setStyleSheet("background: transparent;")
        sl = QHBoxLayout(summary)
        sl.setContentsMargins(0, 0, 0, 4)
        sl.setSpacing(12)
        count = QLabel(L.t("game.achievements_count",
                           count=len(self._achievements)))
        count.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 11px; background: transparent;")
        avg = QLabel(L.t("game.completion", value=average))
        avg.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;")
        sl.addWidget(count)
        sl.addWidget(avg)
        sl.addStretch()
        self.ach_body.addWidget(summary)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(round(average)))
        bar.setFixedHeight(3)
        bar.setTextVisible(False)
        bar.setStyleSheet(
            f"QProgressBar {{ background-color: {SURFACE_3}; border: none; }}"
            f"QProgressBar::chunk {{ background-color: {WHITE}; }}")
        self.ach_body.addWidget(bar)

        if self._show_all_achievements:
            visible = self._achievements[:ACHIEVEMENT_RENDER_LIMIT]
        else:
            visible = self._achievements[:12]
        for achievement in visible:
            self.ach_body.addWidget(AchievementRow(achievement))

        if self._show_all_achievements \
                and len(self._achievements) > ACHIEVEMENT_RENDER_LIMIT:
            self.ach_body.addWidget(self._placeholder(
                L.t("game.showing_count",
                    shown=len(visible), total=len(self._achievements))))

        if len(self._achievements) > 12:
            toggle = QPushButton(
                L.t("game.show_less").upper() if self._show_all_achievements
                else L.t("game.show_all", count=len(self._achievements)).upper())
            toggle.setCursor(Qt.CursorShape.PointingHandCursor)
            toggle.setStyleSheet(self._ghost_style())
            toggle.clicked.connect(self._toggle_achievements)
            self.ach_body.addWidget(toggle)

    def _toggle_achievements(self):
        self._show_all_achievements = not self._show_all_achievements
        self._render_achievements()

    def _media_heading(self, text):
        label = _micro(text)
        label.setContentsMargins(0, 6, 0, 0)
        return label

    def _add_image_grid(self, body, items, offset):
        host = QWidget()
        host.setStyleSheet("background: transparent;")
        rows = QVBoxLayout(host)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(8)
        for start in range(0, len(items), 3):
            row = QHBoxLayout()
            row.setSpacing(8)
            for position in range(start, min(start + 3, len(items))):
                item = items[position]
                index = offset + position
                tile = ImageTile(
                    f"shot:{self.key}:{index}",
                    item.get("path", ""),
                    item.get("thumb_url") or item.get("url", ""),
                    246, 138,
                )
                tile.clicked.connect(lambda idx=index: self._open_media(idx))
                row.addWidget(tile)
            row.addStretch(1)
            rows.addLayout(row)
        body.addWidget(host)

    def _add_video_grid(self, body, items, offset):
        host = QWidget()
        host.setStyleSheet("background: transparent;")
        rows = QVBoxLayout(host)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(10)
        for start in range(0, len(items), 2):
            row = QHBoxLayout()
            row.setSpacing(10)
            for position in range(start, min(start + 2, len(items))):
                item = items[position]
                index = offset + position
                tile = VideoTile(
                    f"video:{self.key}:{index}",
                    item.get("thumb_url", ""),
                    item.get("title", ""),
                    292,
                    thumb_path=item.get("thumb_path", ""),
                )
                tile.clicked.connect(lambda idx=index: self._open_media(idx))
                row.addWidget(tile)
            row.addStretch(1)
            rows.addLayout(row)
        body.addWidget(host)

    def _toggle_button(self, text, slot):
        button = QPushButton(text.upper())
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(self._ghost_style())
        button.clicked.connect(slot)
        return button

    def _render_screenshots(self):
        _clear_layout(self.shots_body)
        store = (self._steam_payload or {}).get("store") or {}
        store_shots = store.get("screenshots") or []
        user_shots = (self._user_media or {}).get("screenshots") or []

        developer = []
        for shot in store_shots:
            full = shot.get("full") or shot.get("thumb") or ""
            thumb = shot.get("thumb") or full
            if not full:
                continue
            developer.append({
                "kind": "image",
                "title": L.t("media.screenshot_number",
                             number=len(developer) + 1),
                "url": full, "thumb_url": thumb, "source": full,
            })

        mine = []
        for path in user_shots:
            mine.append({
                "kind": "image",
                "title": L.t("media.screenshot_number", number=len(mine) + 1),
                "path": path, "thumb_path": path, "source": path,
            })

        self._shot_items = developer + mine
        if not self._shot_items:
            self.shots_body.addWidget(
                self._placeholder(L.t("game.no_screenshots")))
            return

        if developer:
            self.shots_body.addWidget(
                self._media_heading(L.t("game.developer_media")))
            self._add_image_grid(self.shots_body, developer, 0)

        if mine:
            self.shots_body.addWidget(self._media_heading(
                f"{L.t('game.user_screenshots')}  ·  {len(mine)}"))
            visible = mine if self._show_all_shots else mine[:9]
            self._add_image_grid(self.shots_body, visible, len(developer))
            if len(mine) > 9:
                self.shots_body.addWidget(self._toggle_button(
                    L.t("game.show_less") if self._show_all_shots
                    else L.t("game.show_all", count=len(mine)),
                    self._toggle_shots,
                ))

    def _toggle_shots(self):
        self._show_all_shots = not self._show_all_shots
        self._render_screenshots()

    def _render_videos(self, movies):
        _clear_layout(self.videos_body)
        user_clips = (self._user_media or {}).get("videos") or []

        developer = []
        for movie in movies:
            sources = [
                url for url in (movie.get("hls"), movie.get("mp4"),
                                movie.get("webm"), movie.get("dash"))
                if url
            ]
            developer.append({
                "kind": "video",
                "title": movie.get("name") or L.t("media.video"),
                "sources": sources,
                "thumb_url": movie.get("thumb", ""),
                "url": sources[0] if sources else "",
            })

        mine = []
        for clip in user_clips:
            mine.append({
                "kind": "video",
                "title": clip.get("label") or clip.get("name")
                or L.t("media.video"),
                "sources": [],
                "clip": clip,
                "thumb_path": clip.get("thumb", ""),
                "path": clip.get("path", ""),
            })

        self._video_items = developer + mine
        if not self._video_items:
            self.videos_body.addWidget(self._placeholder(L.t("game.no_videos")))
            return

        if developer:
            self.videos_body.addWidget(
                self._media_heading(L.t("game.developer_media")))
            self._add_video_grid(self.videos_body, developer, 0)

        if mine:
            self.videos_body.addWidget(self._media_heading(
                f"{L.t('game.user_clips')}  ·  {len(mine)}"))
            visible = mine if self._show_all_videos else mine[:4]
            self._add_video_grid(self.videos_body, visible, len(developer))
            if len(mine) > 4:
                self.videos_body.addWidget(self._toggle_button(
                    L.t("game.show_less") if self._show_all_videos
                    else L.t("game.show_all", count=len(mine)),
                    self._toggle_videos,
                ))

    def _toggle_videos(self):
        self._show_all_videos = not self._show_all_videos
        self._render_videos(
            ((self._steam_payload or {}).get("store") or {}).get("movies") or [])

    def _open_media(self, index):
        items = list(self._shot_items) + list(self._video_items)
        if not items:
            return
        if self._viewer is None:
            self._viewer = MediaViewer()
        self._viewer.show_items(
            items, index, self.meta.get("name", self.key))

    # ------------------------------------------------------------------
    #  Public refresh hooks
    # ------------------------------------------------------------------
    def set_favorite(self, value):
        self._favorite = bool(value)
        self._render_favorite()

    def update_meta(self, meta, is_favorite=None):
        self.meta = dict(meta or {})
        self.hero.set_title(self.meta.get("name", self.key))
        self.hero.meta.setText(self._hero_meta())
        if is_favorite is not None:
            self.set_favorite(is_favorite)
        self._update_stats()

    def update_stats(self, play_time=None, launch_count=None, last_played=None):
        play_times = self.stats.setdefault("play_times", {})
        launch_counts = self.stats.setdefault("launch_counts", {})
        last_played_map = self.stats.setdefault("last_played", {})
        if play_time is not None:
            play_times[self.key] = play_time
        if launch_count is not None:
            launch_counts[self.key] = launch_count
        if last_played is not None:
            last_played_map[self.key] = last_played
        self._update_stats()
