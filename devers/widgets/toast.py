"""Lightweight monochrome toast notifications."""

from PyQt6.QtCore import (QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer,
                          pyqtProperty, pyqtSignal)
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout,
                             QLabel, QWidget)

from ..theme import ANIM, LINE, SURFACE_2, WHITE

KIND_ICONS = {
    "info": "✦",
    "success": "✓",
    "warning": "!",
    "error": "×",
}


class Toast(QFrame):
    """A single sharp notification card with a shrinking progress line."""

    closed = pyqtSignal(object)

    def __init__(self, host, message, kind="info", duration=2800):
        super().__init__(host)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._duration = max(900, int(duration))
        self._progress = 1.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(13, 10, 15, 11)
        layout.setSpacing(10)

        icon = QLabel(KIND_ICONS.get(kind, KIND_ICONS["info"]))
        icon.setObjectName("ToastIcon")
        icon.setFixedWidth(14)
        icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(icon)

        text = QLabel(str(message))
        text.setObjectName("ToastText")
        text.setWordWrap(True)
        text.setMaximumWidth(320)
        layout.addWidget(text, stretch=1)

        self.adjustSize()
        self.setFixedWidth(min(380, max(230, self.sizeHint().width())))

        self._fade = QGraphicsOpacityEffect(self)
        self._fade.setOpacity(0.0)
        self.setGraphicsEffect(self._fade)

        self._fade_anim = QPropertyAnimation(self._fade, b"opacity", self)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._progress_anim = QPropertyAnimation(self, b"progress", self)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.Linear)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_toast)

    # -- animated progress -------------------------------------------------
    def _get_progress(self):
        return self._progress

    def _set_progress(self, value):
        self._progress = float(value)
        self.update()

    progress = pyqtProperty(float, fget=_get_progress, fset=_set_progress)

    def start(self, x, y):
        self.move(x, y)
        self.show()
        self.raise_()
        if ANIM.enabled():
            self._fade_anim.stop()
            self._fade_anim.setDuration(ANIM.duration(180))
            self._fade_anim.setStartValue(0.0)
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.start()
        else:
            self._fade.setOpacity(1.0)
        self._timer.start(self._duration)
        self._progress_anim.stop()
        self._progress_anim.setDuration(self._duration)
        self._progress_anim.setStartValue(1.0)
        self._progress_anim.setEndValue(0.0)
        self._progress_anim.start()

    def hide_toast(self):
        if not self.isVisible():
            return
        self._timer.stop()
        self._progress_anim.stop()
        if not ANIM.enabled():
            self._finish()
            return
        self._fade_anim.stop()
        self._fade_anim.setDuration(ANIM.duration(160))
        self._fade_anim.setStartValue(self._fade.opacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self._finish)
        self._fade_anim.start()

    def _finish(self):
        try:
            self._fade_anim.finished.disconnect(self._finish)
        except Exception:
            pass
        self.closed.emit(self)
        self.hide()
        self.deleteLater()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        # left accent
        painter.fillRect(QRectF(0, 0, 2, self.height()), QColor(WHITE))
        # countdown line
        width = max(0.0, self.width() * self._progress)
        if width > 0:
            painter.fillRect(QRectF(0, self.height() - 2, width, 2), QColor(WHITE))
        painter.end()


class ToastManager(QWidget):
    """Overlay host that stacks toasts in the bottom-right corner."""

    MAX_VISIBLE = 3

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent;")
        self._toasts = []
        self.setGeometry(parent.rect())

    def show_toast(self, message, kind="info", duration=2800):
        if not message:
            return
        # drop already-closed toasts
        self._toasts = [t for t in self._toasts if t.isVisible()]
        while len(self._toasts) >= self.MAX_VISIBLE:
            oldest = self._toasts.pop(0)
            oldest.hide_toast()
        toast = Toast(self, message, kind=kind, duration=duration)
        toast.closed.connect(self._forget)
        self._toasts.append(toast)
        self._reposition()
        toast.start(*self._target_position(len(self._toasts) - 1))
        self.raise_()

    def _forget(self, toast):
        if toast in self._toasts:
            self._toasts.remove(toast)
        self._reposition()

    def _target_position(self, index):
        margin = 22
        y = self.height() - 48
        for i in range(index + 1):
            toast = self._toasts[i] if i < len(self._toasts) else None
            h = toast.height() if toast is not None else 44
            y -= h + 8
        return self.width() - margin - (self._toasts[index].width()
                                        if index < len(self._toasts) else 240), y

    def _reposition(self):
        for i, toast in enumerate(self._toasts):
            if not toast.isVisible():
                continue
            x, y = self._target_position(i)
            toast.move(x, y)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()
