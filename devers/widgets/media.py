"""Standalone media viewer: screenshots with zoom/pan and a video player.

The viewer is a separate top-level window so the launcher stays usable while
media is open.  It intentionally keeps the same monochrome chrome as the rest
of the app; only the media itself is in colour.
"""

import os
import webbrowser

from PyQt6.QtCore import (QPoint, QPointF, QRectF, QSize, Qt, QThreadPool,
                          QTimer, QUrl, pyqtSignal)
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QSizeGrip, QSizePolicy,
                             QSlider, QStackedWidget, QVBoxLayout, QWidget)

from ..covers import CoverLoader
from ..i18n import L
from ..paths import open_path
from ..steam_info import ensure_clip_playlist
from ..theme import (BLACK, LINE, LINE_STRONG, SURFACE, SURFACE_2, SURFACE_3,
                     TEXT, TEXT_DIM, TEXT_FAINT, TEXT_MUTED, WHITE)

try:  # QtMultimedia ships with PyQt6, but keep the viewer usable without it.
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    MULTIMEDIA_AVAILABLE = True
except Exception:  # pragma: no cover - optional backend
    QAudioOutput = None
    QMediaPlayer = None
    QVideoWidget = None
    MULTIMEDIA_AVAILABLE = False


# ---------------------------------------------------------------------------
#  Small building blocks
# ---------------------------------------------------------------------------
class WindowDragBar(QFrame):
    """Top bar that also drags a frameless window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = (event.globalPosition().toPoint()
                          - self.window().frameGeometry().topLeft())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            if window.isMaximized():
                window.showNormal()
            else:
                window.showMaximized()
            return
        super().mouseDoubleClickEvent(event)


class ImageCanvas(QWidget):
    """Fits an image to the window, with wheel zoom, drag pan and double-click."""

    MIN_ZOOM = 1.0
    MAX_ZOOM = 8.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = QImage()
        self._status = ""
        self._zoom = 1.0
        self._offset = QPointF(0.0, 0.0)
        self._drag_from = None
        self._drag_offset = QPointF(0.0, 0.0)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setStyleSheet(f"background-color: {BLACK};")

    # -- state -----------------------------------------------------------
    def set_loading(self):
        self._image = QImage()
        self._status = L.t("media.loading")
        self._zoom = 1.0
        self._offset = QPointF(0.0, 0.0)
        self.update()

    def set_error(self):
        self._image = QImage()
        self._status = L.t("media.error")
        self.update()

    def set_image(self, image):
        self._image = image if image is not None else QImage()
        self._status = "" if not self._image.isNull() else L.t("media.error")
        self._zoom = 1.0
        self._offset = QPointF(0.0, 0.0)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.update()

    def reset_view(self):
        self._zoom = 1.0
        self._offset = QPointF(0.0, 0.0)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.update()

    # -- geometry --------------------------------------------------------
    def _fit_scale(self):
        if self._image.isNull():
            return 1.0
        iw, ih = self._image.width(), self._image.height()
        if iw <= 0 or ih <= 0:
            return 1.0
        return min(self.width() / iw, self.height() / ih)

    def _scale(self):
        return self._fit_scale() * self._zoom

    def _origin(self):
        scale = self._scale()
        iw = self._image.width() * scale
        ih = self._image.height() * scale
        return QPointF((self.width() - iw) / 2 + self._offset.x(),
                       (self.height() - ih) / 2 + self._offset.y())

    def _clamp_offset(self):
        if self._image.isNull():
            self._offset = QPointF(0.0, 0.0)
            return
        scale = self._scale()
        iw = self._image.width() * scale
        ih = self._image.height() * scale
        max_x = max(0.0, (iw - self.width()) / 2 + 40)
        max_y = max(0.0, (ih - self.height()) / 2 + 40)
        self._offset.setX(max(-max_x, min(max_x, self._offset.x())))
        self._offset.setY(max(-max_y, min(max_y, self._offset.y())))

    # -- painting --------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(BLACK))

        if self._image.isNull():
            painter.setPen(QColor(TEXT_MUTED))
            font = QFont()
            font.setPointSize(10)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             self._status or "")
            painter.end()
            return

        scale = self._scale()
        origin = self._origin()
        target = QRectF(origin.x(), origin.y(),
                        self._image.width() * scale,
                        self._image.height() * scale)
        painter.drawImage(target, self._image)
        painter.setPen(QPen(QColor(LINE), 1))
        painter.drawRect(target.adjusted(0, 0, -1, -1))
        painter.end()

    # -- interaction -----------------------------------------------------
    def wheelEvent(self, event):
        if self._image.isNull():
            return
        delta = event.angleDelta().y()
        if not delta:
            return
        old_scale = self._scale()
        if old_scale <= 0:
            return
        factor = 1.18 if delta > 0 else 1 / 1.18
        new_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self._zoom * factor))
        if abs(new_zoom - self._zoom) < 0.001:
            return

        pos = event.position()
        origin = self._origin()
        image_point = QPointF((pos.x() - origin.x()) / old_scale,
                              (pos.y() - origin.y()) / old_scale)
        self._zoom = new_zoom
        new_scale = self._scale()
        new_origin = QPointF(pos.x() - image_point.x() * new_scale,
                             pos.y() - image_point.y() * new_scale)
        iw = self._image.width() * new_scale
        ih = self._image.height() * new_scale
        self._offset = QPointF(
            new_origin.x() - (self.width() - iw) / 2,
            new_origin.y() - (self.height() - ih) / 2,
        )
        if self._zoom <= self.MIN_ZOOM + 0.001:
            self._offset = QPointF(0.0, 0.0)
        self._clamp_offset()
        self.setCursor(Qt.CursorShape.OpenHandCursor
                       if self._zoom <= self.MIN_ZOOM else Qt.CursorShape.ClosedHandCursor)
        self.update()

    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and not self._image.isNull() and self._zoom > self.MIN_ZOOM):
            self._drag_from = event.position()
            self._drag_offset = QPointF(self._offset)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_from is not None:
            delta = event.position() - self._drag_from
            self._offset = QPointF(self._drag_offset.x() + delta.x(),
                                   self._drag_offset.y() + delta.y())
            self._clamp_offset()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_from is not None:
            self._drag_from = None
            self.setCursor(Qt.CursorShape.OpenHandCursor
                           if self._zoom <= self.MIN_ZOOM else Qt.CursorShape.ClosedHandCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._image.isNull():
            return
        if self._zoom > self.MIN_ZOOM + 0.001:
            self.reset_view()
        else:
            self._zoom = 2.0
            self._offset = QPointF(0.0, 0.0)
            self._clamp_offset()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._clamp_offset()


class ThumbButton(QWidget):
    """Small filmstrip cell; paints a cover and a play glyph for videos."""

    clicked = pyqtSignal(int)

    def __init__(self, index, item, parent=None):
        super().__init__(parent)
        self._index = index
        self._item = item or {}
        self._pixmap = QPixmap()
        self._video = self._item.get("kind") == "video"
        self._active = False
        self._hover = False
        self.setFixedSize(76, 44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self._item.get("title", ""))
        source = (self._item.get("thumb_path") or self._item.get("thumb_url")
                  or self._item.get("path") or self._item.get("url") or "")
        if source:
            loader = CoverLoader(
                f"media-thumb:{index}:{source}",
                self._item.get("thumb_path", ""),
                self._item.get("thumb_url", ""),
            )
            loader.signals.loaded.connect(self._on_loaded)
            QThreadPool.globalInstance().start(loader)

    def set_active(self, active):
        self._active = bool(active)
        self.update()

    def _on_loaded(self, _key, image):
        if not image.isNull():
            self._pixmap = QPixmap.fromImage(image)
            self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.fillRect(rect, QColor(SURFACE_3))
        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                rect.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            if scaled.width() > rect.width() or scaled.height() > rect.height():
                scaled = scaled.copy(
                    max(0, (scaled.width() - rect.width()) // 2),
                    max(0, (scaled.height() - rect.height()) // 2),
                    rect.width(), rect.height())
            painter.drawPixmap(rect.topLeft(), scaled)
        if self._video:
            cx, cy = rect.center().x(), rect.center().y()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 190))
            painter.drawEllipse(QPointF(cx, cy), 11, 11)
            painter.setPen(QPen(QColor(WHITE), 1.2))
            painter.drawPolygon([
                QPointF(cx - 3, cy - 5), QPointF(cx + 6, cy),
                QPointF(cx - 3, cy + 5),
            ])
            painter.setBrush(Qt.BrushStyle.NoBrush)
        color = WHITE if (self._active or self._hover) else LINE
        painter.setPen(QPen(QColor(color), 1))
        painter.drawRect(rect)
        if self._active:
            painter.fillRect(rect.left(), rect.bottom() - 2, rect.width(), 2,
                             QColor(WHITE))
        painter.end()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._index)
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
#  Viewer window
# ---------------------------------------------------------------------------
class MediaViewer(QWidget):
    """Non-modal window that shows a mixed screenshot/video gallery."""

    closed = pyqtSignal()
    STRIP_LIMIT = 80

    def __init__(self, parent=None):
        flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        super().__init__(parent, flags)
        self.setWindowTitle(L.t("media.title"))
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumSize(760, 520)
        self.resize(1180, 760)
        self.setStyleSheet(self._stylesheet())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._items = []
        self._index = 0
        self._loaded_index = -1
        self._game_title = ""
        self._image_key = ""
        self._strip_buttons = []
        self._strip_start = 0
        self._player = None
        self._audio = None
        self._video_widget = None
        self._video_sources = []
        self._video_source_index = 0
        self._muted = False
        self._fullscreen = False

        self._build_ui()

    # -- construction ----------------------------------------------------
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        bar = WindowDragBar()
        bar.setObjectName("MediaBar")
        bar.setFixedHeight(46)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 8, 10, 8)
        bl.setSpacing(10)

        self.kind = QLabel("")
        self.kind.setObjectName("Micro")
        self.kind.setMinimumWidth(92)
        self.kind.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        bl.addWidget(self.kind)

        self.title = QLabel("")
        self.title.setStyleSheet(
            f"color: {WHITE}; font-size: 12px; font-weight: 700;"
            "background: transparent;")
        self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        bl.addWidget(self.title, stretch=1)

        self.counter = QLabel("")
        self.counter.setObjectName("Micro")
        self.counter.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        bl.addWidget(self.counter)

        self.external_btn = self._tool("↗", L.t("media.open"))
        self.external_btn.clicked.connect(self._open_external)
        bl.addWidget(self.external_btn)

        self.close_btn = self._tool("×", L.t("media.close"))
        self.close_btn.clicked.connect(self.close)
        bl.addWidget(self.close_btn)
        outer.addWidget(bar)

        media_host = QWidget()
        self.media_host = media_host
        media_host.setStyleSheet(f"background-color: {BLACK};")
        grid = QGridLayout(media_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: transparent; border: none;")
        grid.addWidget(self.stack, 0, 0)

        self.canvas = ImageCanvas()
        self.stack.addWidget(self.canvas)

        self.video_page = QWidget()
        self.video_page.setStyleSheet(f"background-color: {BLACK};")
        vl = QVBoxLayout(self.video_page)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        self.video_host = QWidget()
        self.video_host.setStyleSheet(f"background-color: {BLACK};")
        self.video_host_layout = QVBoxLayout(self.video_host)
        self.video_host_layout.setContentsMargins(0, 0, 0, 0)
        self.video_host_layout.setSpacing(0)
        self.video_error_page = QWidget()
        self.video_error_page.setStyleSheet("background: transparent;")
        el = QVBoxLayout(self.video_error_page)
        el.setContentsMargins(28, 24, 28, 24)
        el.setSpacing(10)
        el.addStretch(1)
        self.video_error_icon = QLabel("▶")
        self.video_error_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_error_icon.setStyleSheet(
            f"color: {TEXT_FAINT}; font-size: 32px; background: transparent;")
        el.addWidget(self.video_error_icon)
        self.video_message = QLabel("")
        self.video_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_message.setWordWrap(True)
        self.video_message.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        el.addWidget(self.video_message)
        self.video_external_btn = QPushButton(L.t("media.open"))
        self.video_external_btn.setObjectName("Ghost")
        self.video_external_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.video_external_btn.setFixedHeight(32)
        self.video_external_btn.setVisible(False)
        self.video_external_btn.clicked.connect(self._open_external)
        el.addWidget(self.video_external_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        el.addStretch(1)
        self.video_error_page.setVisible(False)
        self.video_host_layout.addWidget(self.video_error_page, stretch=1)
        vl.addWidget(self.video_host, stretch=1)

        self.video_controls = QFrame()
        self.video_controls.setObjectName("MediaControls")
        self.video_controls.setFixedHeight(42)
        cl = QHBoxLayout(self.video_controls)
        cl.setContentsMargins(10, 6, 12, 6)
        cl.setSpacing(10)
        self.video_play_btn = self._tool("▶", L.t("media.play"))
        self.video_play_btn.clicked.connect(self._toggle_play)
        cl.addWidget(self.video_play_btn)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderMoved.connect(self._seek)
        cl.addWidget(self.seek, stretch=1)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("Micro")
        cl.addWidget(self.time_label)
        self.mute_btn = self._tool("♪", L.t("media.mute"))
        self.mute_btn.clicked.connect(self._toggle_mute)
        cl.addWidget(self.mute_btn)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.setFixedWidth(80)
        self.volume.valueChanged.connect(self._set_volume)
        cl.addWidget(self.volume)
        vl.addWidget(self.video_controls)
        self.stack.addWidget(self.video_page)

        self.prev_btn = self._nav("‹", L.t("media.prev"), media_host)
        self.prev_btn.clicked.connect(lambda: self._step(-1))
        self.next_btn = self._nav("›", L.t("media.next"), media_host)
        self.next_btn.clicked.connect(lambda: self._step(1))
        outer.addWidget(media_host, stretch=1)

        self.strip = QFrame()
        self.strip.setObjectName("MediaStrip")
        self.strip.setFixedHeight(58)
        sl = QHBoxLayout(self.strip)
        sl.setContentsMargins(10, 7, 10, 7)
        sl.setSpacing(0)
        self.strip_scroll = QScrollArea()
        self.strip_scroll.setWidgetResizable(True)
        self.strip_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.strip_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.strip_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.strip_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }")
        self.strip_host = QWidget()
        self.strip_host.setStyleSheet("background: transparent;")
        self.strip_layout = QHBoxLayout(self.strip_host)
        self.strip_layout.setContentsMargins(0, 0, 0, 0)
        self.strip_layout.setSpacing(6)
        self.strip_layout.addStretch(1)
        self.strip_scroll.setWidget(self.strip_host)
        sl.addWidget(self.strip_scroll)
        grip = QSizeGrip(self)
        grip.setFixedSize(16, 16)
        sl.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        outer.addWidget(self.strip)

    def _tool(self, text, tooltip):
        btn = QPushButton(text)
        btn.setObjectName("MediaTool")
        btn.setFixedSize(30, 30)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tooltip)
        return btn

    def _nav(self, text, tooltip, parent):
        btn = QPushButton(text, parent)
        btn.setObjectName("MediaNav")
        btn.setFixedSize(34, 64)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tooltip)
        btn.setStyleSheet(
            f"QPushButton#MediaNav {{ background-color: rgba(0,0,0,150);"
            f" color: {TEXT_DIM}; border: 1px solid {LINE};"
            " font-size: 20px; padding: 0; }"
            f"QPushButton#MediaNav:hover {{ color: {WHITE};"
            f" border-color: {WHITE}; background-color: rgba(0,0,0,205); }}"
            f"QPushButton#MediaNav:disabled {{ color: {TEXT_FAINT};"
            f" border-color: {LINE}; background-color: rgba(0,0,0,90); }}")
        return btn

    @staticmethod
    def _stylesheet():
        return f"""
            QWidget {{ color: {TEXT}; background-color: {BLACK};
                font-family: 'Segoe UI Variable Display', 'Segoe UI', Arial; }}
            QFrame#MediaBar {{ background-color: {SURFACE}; border-bottom: 1px solid {LINE}; }}
            QFrame#MediaStrip {{ background-color: {SURFACE}; border-top: 1px solid {LINE}; }}
            QFrame#MediaControls {{ background-color: {SURFACE}; border-top: 1px solid {LINE}; }}
            QLabel#Micro {{ color: {TEXT_MUTED}; font-size: 9px; font-weight: 700;
                letter-spacing: 2px; background: transparent; }}
            QPushButton#MediaTool {{
                background-color: transparent; color: {TEXT_DIM};
                border: 1px solid {LINE}; padding: 0; font-size: 14px;
            }}
            QPushButton#MediaTool:hover {{ color: {WHITE}; border-color: {WHITE}; }}
            QPushButton#Ghost {{
                background-color: transparent; color: {TEXT_DIM};
                border: 1px solid {LINE}; padding: 0 16px;
                font-size: 10px; font-weight: 700; letter-spacing: 1px;
            }}
            QPushButton#Ghost:hover {{ color: {WHITE}; border-color: {WHITE}; }}
            QSlider::groove:horizontal {{ background: {SURFACE_3}; height: 3px; }}
            QSlider::sub-page:horizontal {{ background: {WHITE}; }}
            QSlider::handle:horizontal {{
                background: {WHITE}; width: 9px; margin: -3px 0;
            }}
            QSlider::groove:horizontal:disabled {{ background: {LINE}; }}
            QSlider::sub-page:horizontal:disabled {{ background: {LINE}; }}
            QSlider::handle:horizontal:disabled {{ background: {TEXT_FAINT}; }}
        """

    # -- public API ------------------------------------------------------
    def show_items(self, items, index=0, game_title=""):
        self._items = list(items or [])
        self._game_title = game_title or ""
        self._loaded_index = -1
        self._index = max(0, min(len(self._items) - 1, int(index))) \
            if self._items else 0
        self._build_strip(self._index)
        self._show_index(index)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def shutdown(self):
        self._stop_video()
        self.close()
        self.deleteLater()

    # -- filmstrip -------------------------------------------------------
    def _strip_window(self, center):
        total = len(self._items)
        if total <= self.STRIP_LIMIT:
            return 0, total
        start = max(0, min(center - self.STRIP_LIMIT // 2,
                           total - self.STRIP_LIMIT))
        return start, start + self.STRIP_LIMIT

    def _build_strip(self, center=None):
        for btn in self._strip_buttons:
            btn.setParent(None)
            btn.deleteLater()
        self._strip_buttons = []
        center = self._index if center is None else center
        start, end = self._strip_window(center)
        self._strip_start = start
        for index in range(start, end):
            btn = ThumbButton(index, self._items[index])
            btn.clicked.connect(self._show_index)
            self.strip_layout.insertWidget(len(self._strip_buttons), btn)
            self._strip_buttons.append(btn)
        self.strip.setVisible(len(self._items) > 1)
        QTimer.singleShot(0, self._scroll_strip_to_active)

    def _scroll_strip_to_active(self):
        for btn in self._strip_buttons:
            if btn._index == self._index:
                self.strip_scroll.ensureWidgetVisible(btn, 40, 0)
                break

    def _mark_strip(self):
        for btn in self._strip_buttons:
            btn.set_active(btn._index == self._index)

    # -- navigation ------------------------------------------------------
    def _step(self, delta):
        if not self._items:
            return
        self._show_index(self._index + delta)

    def _show_index(self, index):
        if not self._items:
            return
        index = max(0, min(len(self._items) - 1, int(index)))
        same = (index == self._index and self.stack.currentWidget() is not None
                and getattr(self, "_loaded_index", -1) == index)
        self._index = index
        item = self._items[index]
        kind = item.get("kind", "image")
        if kind == "video":
            self.kind.setText(L.t("media.video").upper())
            heading = item.get("title") or self._game_title
        else:
            self.kind.setText(
                L.t("media.screenshot_number", number=index + 1).upper())
            heading = self._game_title or item.get("title") or ""
        self.title.setText(self._elide(heading))
        self.title.setToolTip(heading)
        self.counter.setText(L.t("media.counter", current=index + 1,
                                 total=len(self._items)))
        self.prev_btn.setEnabled(index > 0)
        self.next_btn.setEnabled(index < len(self._items) - 1)
        self.prev_btn.setVisible(index > 0)
        self.next_btn.setVisible(index < len(self._items) - 1)
        if not (self._strip_start <= index
                < self._strip_start + len(self._strip_buttons)):
            self._build_strip(index)
        self._mark_strip()
        self._update_external(item)
        if same:
            return
        self._loaded_index = index
        self._stop_video()
        if kind == "video":
            self.stack.setCurrentWidget(self.video_page)
            self._load_video(item)
        else:
            self.stack.setCurrentWidget(self.canvas)
            self._load_image(item)

    def _elide(self, text):
        fm = QFontMetrics(self.title.font())
        return fm.elidedText(str(text or ""), Qt.TextElideMode.ElideRight,
                             max(200, self.width() - 360))

    def _load_image(self, item):
        source = item.get("path") or item.get("url") or ""
        self.canvas.set_loading()
        if not source:
            self.canvas.set_error()
            return
        key = f"media:{self._index}:{source}"
        self._image_key = key
        loader = CoverLoader(
            key,
            item.get("path", ""),
            item.get("url", ""),
            max_side=0,
            memory_key=source,
        )
        loader.signals.loaded.connect(self._on_image)
        QThreadPool.globalInstance().start(loader)

    def _on_image(self, key, image):
        if key != self._image_key:
            return
        if image.isNull():
            self.canvas.set_error()
        else:
            self.canvas.set_image(image)

    @staticmethod
    def _external_target(item):
        target = item.get("path") or item.get("url") or ""
        if not target:
            sources = [s for s in (item.get("sources") or []) if s]
            target = sources[0] if sources else ""
        return target

    def _update_external(self, item):
        self.external_btn.setEnabled(bool(self._external_target(item)))

    def _open_external(self):
        if not self._items:
            return
        item = self._items[self._index]
        target = self._external_target(item)
        if not target:
            return
        if os.path.exists(target):
            open_path(target)
        else:
            webbrowser.open(target)

    # -- video -----------------------------------------------------------
    def _ensure_player(self):
        if not MULTIMEDIA_AVAILABLE:
            return False
        if self._player is not None:
            return True
        try:
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
            self._video_widget = QVideoWidget(self.video_host)
            self._video_widget.setStyleSheet(f"background-color: {BLACK};")
            self._video_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.video_host_layout.addWidget(self._video_widget, stretch=1)
            self._player.setVideoOutput(self._video_widget)
            self._player.playbackStateChanged.connect(self._on_playback_state)
            self._player.positionChanged.connect(self._on_position)
            self._player.durationChanged.connect(self._on_duration)
            self._player.errorOccurred.connect(self._on_video_error)
            self._player.mediaStatusChanged.connect(self._on_media_status)
            self._audio.setVolume(self.volume.value() / 100)
            return True
        except Exception:
            self._player = None
            self._video_widget = None
            return False

    def _load_video(self, item):
        sources = [s for s in (item.get("sources") or [])
                   if s] or ([item.get("url")] if item.get("url") else [])
        if item.get("clip"):
            # Steam recordings are DASH/HEVC; expose them as local HLS.
            playlist = ensure_clip_playlist(item["clip"])
            if playlist:
                sources = [playlist]
        self._video_sources = sources
        self._video_source_index = 0
        self.video_message.setVisible(False)
        self.video_external_btn.setVisible(False)
        self.video_error_page.setVisible(False)
        if not self._video_sources:
            self._show_video_error()
            return
        if not self._ensure_player():
            self._show_video_error(L.t("media.video_unavailable"))
            return
        self._video_widget.setVisible(True)
        self._play_current_source()

    def _play_current_source(self):
        if self._player is None or not self._video_sources:
            return
        source = self._video_sources[self._video_source_index]
        url = QUrl.fromLocalFile(source) if os.path.exists(source) else QUrl(source)
        self._player.setSource(url)
        self._player.play()

    def _on_video_error(self, _error, _message):
        if self._video_source_index + 1 < len(self._video_sources):
            self._video_source_index += 1
            self._play_current_source()
            return
        self._show_video_error()

    def _show_video_error(self, text=None):
        if self._video_widget is not None:
            self._video_widget.setVisible(False)
        self.video_message.setText(text or L.t("media.video_error"))
        self.video_message.setVisible(True)
        item = self._items[self._index] if self._items else {}
        self.video_external_btn.setVisible(
            bool(self._external_target(item)))
        self.video_error_page.setVisible(True)
        self.video_play_btn.setEnabled(False)

    def _stop_video(self):
        if self._player is not None:
            try:
                self._player.stop()
                self._player.setSource(QUrl())
            except Exception:
                pass
        self.video_play_btn.setEnabled(True)
        self.seek.setRange(0, 0)
        self.time_label.setText("00:00 / 00:00")

    def _toggle_play(self):
        if self._player is None:
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_playback_state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.video_play_btn.setText("❚❚" if playing else "▶")
        self.video_play_btn.setToolTip(
            L.t("media.pause") if playing else L.t("media.play"))

    def _on_position(self, value):
        if not self.seek.isSliderDown():
            self.seek.setValue(int(value))
        self.time_label.setText(
            f"{self._clock(value)} / {self._clock(self.seek.maximum())}")

    def _on_duration(self, value):
        self.seek.setRange(0, max(0, int(value)))
        self.time_label.setText(
            f"00:00 / {self._clock(value)}")

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.video_play_btn.setText("▶")

    @staticmethod
    def _clock(ms):
        seconds = max(0, int(ms // 1000))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _seek(self, value):
        if self._player is not None:
            self._player.setPosition(int(value))

    def _toggle_mute(self):
        if self._audio is None:
            return
        self._muted = not self._muted
        self._audio.setMuted(self._muted)
        self.mute_btn.setText("✕" if self._muted else "♪")
        self.mute_btn.setToolTip(
            L.t("media.unmute") if self._muted else L.t("media.mute"))

    def _set_volume(self, value):
        if self._audio is not None:
            self._audio.setVolume(max(0.0, min(1.0, value / 100)))

    # -- window behaviour ------------------------------------------------
    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self._fullscreen:
                self._toggle_fullscreen()
            else:
                self.close()
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self._step(-1)
            return
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self._step(1)
            return
        if key == Qt.Key.Key_Home:
            self._show_index(0)
            return
        if key == Qt.Key.Key_End:
            self._show_index(len(self._items) - 1)
            return
        if key in (Qt.Key.Key_F, Qt.Key.Key_F11):
            self._toggle_fullscreen()
            return
        if key == Qt.Key.Key_Space and self.stack.currentWidget() is self.video_page:
            self._toggle_play()
            return
        if key == Qt.Key.Key_O:
            self._open_external()
            return
        super().keyPressEvent(event)

    def _toggle_fullscreen(self):
        self._fullscreen = not self._fullscreen
        if self._fullscreen:
            self.showFullScreen()
        else:
            self.showNormal()

    def closeEvent(self, event):
        self._stop_video()
        self.closed.emit()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._position_nav)
        if self._items:
            self.title.setText(self._elide(self.title.toolTip()))

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._position_nav)

    def _position_nav(self):
        host = getattr(self, "media_host", None)
        if host is None or not hasattr(self, "prev_btn"):
            return
        height = host.height()
        top = max(0, (height - self.prev_btn.height()) // 2)
        self.prev_btn.move(12, top)
        self.next_btn.move(
            max(12, host.width() - self.next_btn.width() - 12), top)
        self.prev_btn.raise_()
        self.next_btn.raise_()
