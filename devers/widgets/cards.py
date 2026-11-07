"""Sharp game cards, cover images and loading skeletons."""

import os

from PyQt6.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt,
                          QThreadPool, QTimer, pyqtSignal)
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                             QProgressBar, QPushButton, QSizePolicy, QVBoxLayout,
                             QWidget)

from ..covers import CoverLoader
from ..i18n import L
from ..theme import (ANIM, BLACK, LINE, LINE_STRONG, SURFACE_2, SURFACE_3,
                     TEXT_DIM, TEXT_MUTED, UI, WHITE, draw_scanline)
from ..utils import human_size, human_time

CARD_WIDTH = 240
CARD_HEIGHT = 268
COVER_HEIGHT = 168

COMPACT_CARD_WIDTH = 198
COMPACT_CARD_HEIGHT = 218
COMPACT_COVER_HEIGHT = 128

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
    """Monochrome badge: white hairline on a translucent black plate."""
    return ("background-color: rgba(0, 0, 0, 215); color: #FFFFFF; "
            "border: 1px solid rgba(255, 255, 255, 110);")


class CoverImage(QLabel):
    """Scales a source pixmap to cover the label with hard (square) edges."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source_pixmap = None

    def set_cover_pixmap(self, pixmap):
        self._source_pixmap = pixmap
        self._repaint()

    def clear_cover(self):
        self._source_pixmap = None
        self.clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._repaint()

    def _repaint(self):
        if self._source_pixmap is None or self._source_pixmap.isNull():
            return
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        scaled = self._source_pixmap.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        if scaled.width() > w or scaled.height() > h:
            x = (scaled.width() - w) // 2
            y = (scaled.height() - h) // 2
            scaled = scaled.copy(x, y, w, h)
        super().setPixmap(scaled)


class GameCard(QFrame):
    play_requested = pyqtSignal(str)
    context_menu_requested = pyqtSignal(str, QPoint)
    favorite_toggled = pyqtSignal(str)
    details_requested = pyqtSignal(str)

    def __init__(self, key, meta, is_favorite=False, show_ext=False, play_time=0,
                 launch_count=0, width=CARD_WIDTH, compact=False):
        super().__init__()
        self.key = key
        self.meta = meta
        self._play_time = play_time
        self._launch_count = launch_count
        self._card_width = max(180, int(width))
        self._compact = bool(compact)
        self._cover_height = COMPACT_COVER_HEIGHT if compact else COVER_HEIGHT
        self._card_height = COMPACT_CARD_HEIGHT if compact else CARD_HEIGHT
        self._show_ext = bool(show_ext)
        self._favorite = bool(is_favorite)
        self._hover = False
        self.setObjectName("GameCard")
        self.setFixedSize(self._card_width, self._card_height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.cover = CoverImage()
        self.cover.setFixedHeight(self._cover_height)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setStyleSheet(
            f"background-color: {SURFACE_3}; color: {TEXT_MUTED}; font-size: 10px;"
            "letter-spacing: 2px;"
        )
        self.cover.setText(L.t("card.no_cover"))

        if meta.get("error"):
            self.cover.setText(L.t("card.error"))
            self.cover.setStyleSheet(
                f"background-color: {SURFACE_3}; color: {WHITE}; font-size: 10px;"
                "letter-spacing: 2px;"
            )
        elif meta.get("cover_path") or meta.get("cover_url") or meta.get("cover_data"):
            QThreadPool.globalInstance().start(self._make_cover_loader(meta))

        self.badge = QLabel(self.cover)
        self.badge.setText(BADGE_LABELS.get(str(meta.get("type", "")), ""))
        self.badge.setStyleSheet(
            badge_style(str(meta.get("type", "")))
            + "padding: 3px 8px; font-size: 9px; font-weight: bold; letter-spacing: 2px;"
        )
        self.badge.setVisible(bool(self.badge.text()))
        self.badge.adjustSize()
        self.badge.move(10, 10)
        if self.badge.isVisible():
            self.badge.raise_()

        self.running_badge = QLabel("●", self.cover)
        self.running_badge.setStyleSheet(
            "color: #FFFFFF; background-color: rgba(0, 0, 0, 205);"
            "border: 1px solid rgba(255, 255, 255, 120);"
            "padding: 2px 6px; font-size: 9px;")
        self.running_badge.setToolTip(L.t("home.now_playing"))
        self.running_badge.setVisible(False)
        self._position_running_badge()

        self.play_overlay = QPushButton(self.cover)
        self.play_overlay.setFixedSize(52, 52)
        self.play_overlay.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_overlay.setToolTip(L.t("menu.play"))
        self.play_overlay.setText("▶")
        self.play_overlay.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(0, 0, 0, 210);
                border: 1px solid {WHITE};
                color: {WHITE}; font-size: 16px; padding: 0;
            }}
            QPushButton:hover {{ background-color: {WHITE}; color: {BLACK}; }}
        """)
        self.play_overlay.clicked.connect(lambda: self.play_requested.emit(self.key))
        self._overlay_effect = QGraphicsOpacityEffect(self.play_overlay)
        self._overlay_effect.setOpacity(0.0)
        self.play_overlay.setGraphicsEffect(self._overlay_effect)
        self.play_overlay.setVisible(False)
        self._overlay_anim = QPropertyAnimation(self._overlay_effect, b"opacity", self)
        self._overlay_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        outer.addWidget(self.cover)

        info_wrap = QWidget()
        info_wrap.setStyleSheet(f"background-color: {BLACK};")
        info = QVBoxLayout(info_wrap)
        info.setContentsMargins(14, 11, 14, 11)
        info.setSpacing(6)

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
            f"color: {WHITE}; font-size: 13px; font-weight: bold; background: transparent;"
        )
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        top_row.addWidget(self.name_label)

        self.fav_btn = QPushButton()
        self.fav_btn.setFixedSize(24, 24)
        self.fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fav_btn.setToolTip(L.t("card.favorite") if not is_favorite else L.t("card.unfavorite"))
        self._setup_fav_button(is_favorite)
        self.fav_btn.clicked.connect(lambda: self.favorite_toggled.emit(self.key))
        top_row.addWidget(self.fav_btn)

        info.addStretch(1)
        info.addLayout(top_row)

        self.stats_label = QLabel(self._stats_text())
        self.stats_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;")
        info.addWidget(self.stats_label)
        info.addStretch(1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        self.progress.setFixedHeight(4)
        self._progress_anim = QPropertyAnimation(self.progress, b"value", self)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {SURFACE_3}; border: none;
                text-align: center; color: transparent;
            }}
            QProgressBar::chunk {{ background-color: {WHITE}; }}
        """)
        info.addWidget(self.progress)

        outer.addWidget(info_wrap)

    def _setup_fav_button(self, is_favorite):
        self._favorite = bool(is_favorite)
        self.fav_btn.setText("★" if is_favorite else "☆")
        self.fav_btn.setToolTip(
            L.t("card.unfavorite") if is_favorite else L.t("card.favorite"))
        color = WHITE if is_favorite else "#5E5E5E"
        self.fav_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; color: {color};
                border: none; font-size: 15px; padding: 0;
            }}
            QPushButton:hover {{ color: {WHITE}; }}
        """)

    def set_favorite(self, value):
        if bool(value) == self._favorite:
            return
        self._setup_fav_button(value)

    def update_meta(self, meta, show_ext=None):
        """Refreshes an existing card without rebuilding its widgets."""
        self.meta = meta
        if show_ext is not None:
            self._show_ext = bool(show_ext)
        display_name = meta.get("name", "Unknown")
        if self._show_ext and meta.get("type") not in ("steam", "folder"):
            suffix = os.path.splitext(meta.get("path", ""))[1]
            if suffix:
                display_name = f"{display_name}{suffix}"
        if display_name != self._full_name:
            self._full_name = display_name
            self.name_label.setText(self._elided_name(display_name))
            self.name_label.setToolTip(display_name)
        badge_text = BADGE_LABELS.get(str(meta.get("type", "")), "")
        if self.badge.text() != badge_text:
            self.badge.setText(badge_text)
            self.badge.setVisible(bool(badge_text))
            if badge_text:
                self.badge.adjustSize()
                self.badge.raise_()
        self.stats_label.setText(self._stats_text())

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
        width = max(180, int(width))
        if width == self._card_width:
            return
        self._card_width = width
        self.setFixedWidth(width)
        self.name_label.setText(self._elided_name(self._full_name))
        self._center_overlay()
        self._position_running_badge()

    def set_running(self, running):
        self.running_badge.setVisible(bool(running))
        self._position_running_badge()

    def _position_running_badge(self):
        self.running_badge.adjustSize()
        self.running_badge.move(
            max(8, self.cover.width() - self.running_badge.width() - 10), 10)
        if self.running_badge.isVisible():
            self.running_badge.raise_()

    def _elided_name(self, text: str) -> str:
        try:
            fm = QFontMetrics(self.font())
        except Exception:
            return text
        return fm.elidedText(text, Qt.TextElideMode.ElideRight, self._card_width - 100)

    def _on_cover_loaded(self, key, image):
        if key != self.key or image.isNull():
            return
        self.cover.set_cover_pixmap(QPixmap.fromImage(image))
        self.cover.setText("")

    def set_progress_value(self, value):
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
            self._overlay_anim.setDuration(ANIM.duration(150))
            self._overlay_anim.setStartValue(self._overlay_effect.opacity())
            self._overlay_anim.setEndValue(1.0)
        else:
            self._overlay_anim.setDuration(ANIM.duration(120))
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
        self._hover = True
        if UI.hover_effects:
            self._center_overlay()
            self._set_overlay_visible(True)
            self.stats_label.setStyleSheet(
                f"color: {TEXT_DIM}; font-size: 10px; background: transparent;")
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._hover = False
        self._set_overlay_visible(False)
        self.stats_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; background: transparent;")
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        color = WHITE if (self._hover and UI.hover_effects) else LINE
        painter.setPen(QPen(QColor(color), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if self._hover and UI.hover_effects:
            # small corner accent: a quiet, technical hover cue
            painter.fillRect(QRect(0, 0, 3, 3), QColor(WHITE))
        painter.end()

    def _on_context(self, pos):
        self.context_menu_requested.emit(self.key, self.mapToGlobal(pos))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.details_requested.emit(self.key)
        super().mouseReleaseEvent(event)


class SkeletonCard(QFrame):
    """Placeholder shown while the library is scanned.

    Painted in one go (no child widgets) and animated with a single moving
    highlight, which keeps scanning cheap even with many placeholders.
    """

    def __init__(self, compact=False, parent=None):
        super().__init__(parent)
        self._compact = bool(compact)
        self._cover_height = COMPACT_COVER_HEIGHT if compact else COVER_HEIGHT
        width = COMPACT_CARD_WIDTH if compact else CARD_WIDTH
        height = COMPACT_CARD_HEIGHT if compact else CARD_HEIGHT
        self.setObjectName("SkeletonCard")
        self.setFixedSize(width, height)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(42)
        self._timer.timeout.connect(self._advance)

    def _advance(self):
        self._phase = (self._phase + 0.012) % 1.0
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if ANIM.enabled():
            self._timer.start()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(SURFACE_2))
        cover = QRect(0, 0, self.width(), self._cover_height)
        painter.fillRect(cover, QColor(SURFACE_3))
        if ANIM.enabled():
            draw_scanline(painter, cover, self._phase)
        y = self._cover_height + 16
        painter.fillRect(QRect(14, y, max(40, self.width() - 68), 12),
                         QColor(SURFACE_3))
        painter.fillRect(QRect(14, y + 22, max(30, self.width() // 2 - 20), 8),
                         QColor(SURFACE_2))
        painter.setPen(QPen(QColor(LINE), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()
