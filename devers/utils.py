"""Small shared helpers: JSON storage, formatting, icons and pixmaps."""

import json
import logging
import os
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPen, QPixmap

from .paths import APP_ICON, ICON_DIR

log = logging.getLogger("Devers")

_icon_cache = {}
_size_cache = {}
_size_lock = threading.Lock()


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
    """Atomic JSON write: a crash can never leave a half-written config."""
    try:
        folder = os.path.dirname(path) or "."
        os.makedirs(folder, exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        log.error(f"Не удалось сохранить {path}: {e}")


def human_size(bytes_val):
    for unit in ["B", "KB", "MB", "GB"]:
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


def clock_time(seconds):
    """00:14:05 — used for the live session counter."""
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def dir_size(path):
    """Iterative, scandir-based folder size (noticeably faster than os.walk)."""
    total = 0
    stack = [str(path)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def dir_size_cached(path, ttl=20.0):
    """Folder size with a short TTL so status bars never block the UI."""
    key = str(path)
    now = time.time()
    with _size_lock:
        cached = _size_cache.get(key)
        if cached and now - cached[0] < ttl:
            return cached[1]
    size = dir_size(path)
    with _size_lock:
        _size_cache[key] = (now, size)
    return size


def prettify_name(stem: str) -> str:
    import re
    name = re.sub(r"[._]+", " ", stem)
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name or stem


def invert_pixmap(pixmap):
    """Fast monochrome inversion that preserves the original alpha mask."""
    if pixmap.isNull():
        return pixmap
    source = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    inverted = QImage(source.size(), QImage.Format.Format_ARGB32)
    inverted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(inverted)
    painter.drawImage(0, 0, source)
    painter.setCompositionMode(
        QPainter.CompositionMode.CompositionMode_Difference)
    painter.fillRect(inverted.rect(), QColor(255, 255, 255))
    painter.setCompositionMode(
        QPainter.CompositionMode.CompositionMode_DestinationIn)
    painter.drawImage(0, 0, source)
    painter.end()
    return QPixmap.fromImage(inverted)


def tint_pixmap(pixmap, color):
    """Paints every visible pixel in *color*, keeping the alpha mask."""
    if pixmap.isNull():
        return pixmap
    img = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    painter.setCompositionMode(
        QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(img.rect(), color)
    painter.end()
    return QPixmap.fromImage(img)


def clear_icon_cache():
    _icon_cache.clear()


def get_icon(name, size=22):
    key = ("icon", name, int(size))
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached
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
    _icon_cache[key] = icon
    return icon


def get_icon_tinted(name, size, color):
    key = ("tint", name, int(size), color.name())
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached
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
    _icon_cache[key] = icon
    return icon


def ensure_check_icon() -> str:
    """Monochrome check mark used by styled checkboxes."""
    path = ICON_DIR / "check.png"
    if path.exists():
        return path.as_posix()
    pm = QPixmap(12, 12)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(0, 0, 0), 2.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline([QPointF(2.5, 6.2), QPointF(5.0, 8.8), QPointF(9.6, 3.2)])
    painter.end()
    try:
        pm.save(str(path))
    except Exception as e:
        log.warning(f"Не удалось сохранить check.png: {e}")
    return path.as_posix()


def ensure_chevron_icon() -> str:
    """Small white chevron for combo boxes."""
    path = ICON_DIR / "chevron.png"
    if path.exists():
        return path.as_posix()
    pm = QPixmap(10, 6)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(255, 255, 255), 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawPolyline([QPointF(1, 1.5), QPointF(5, 5), QPointF(9, 1.5)])
    painter.end()
    try:
        pm.save(str(path))
    except Exception as e:
        log.warning(f"Не удалось сохранить chevron.png: {e}")
    return path.as_posix()


def ensure_close_icon() -> str:
    """Neutral close glyph used by game tabs."""
    path = ICON_DIR / "close.png"
    if path.exists():
        return path.as_posix()
    pm = QPixmap(12, 12)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(150, 150, 150), 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(QPointF(3.2, 3.2), QPointF(8.8, 8.8))
    painter.drawLine(QPointF(8.8, 3.2), QPointF(3.2, 8.8))
    painter.end()
    try:
        pm.save(str(path))
    except Exception as e:
        log.warning(f"Не удалось сохранить close.png: {e}")
    return path.as_posix()


def ensure_web_icon() -> str:
    """Sharp monochrome globe used by the in-app browser navigation item."""
    path = ICON_DIR / "web.png"
    if path.exists():
        return path.as_posix()
    size = 64
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(255, 255, 255), 3.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawEllipse(QRectF(9, 9, 46, 46))
    painter.drawLine(QPointF(9, 32), QPointF(55, 32))
    painter.drawEllipse(QRectF(22, 9, 20, 46))
    painter.drawLine(QPointF(14, 19), QPointF(50, 19))
    painter.drawLine(QPointF(14, 45), QPointF(50, 45))
    painter.end()
    try:
        pm.save(str(path))
    except Exception as e:
        log.warning(f"Не удалось сохранить web.png: {e}")
    return path.as_posix()


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
