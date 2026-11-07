"""Design system: strictly monochrome, sharp-cornered, high-contrast.

Every colour used by the chrome comes from this module, so the whole app stays
inside a black/white palette.  Game covers are content and keep their colours.

The module also exposes a tiny runtime ``UI`` switch board (grid backdrop,
hover effects, compact cards) that the settings dialog can flip live.
"""

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QTimer, Qt
from PyQt6.QtGui import (QColor, QLinearGradient, QPainter, QPen,
                         QRadialGradient)
from PyQt6.QtWidgets import QGraphicsOpacityEffect

# --- palette ---------------------------------------------------------------
BLACK = "#000000"
SURFACE = "#050505"
SURFACE_2 = "#0A0A0A"
SURFACE_3 = "#101010"
SURFACE_4 = "#161616"
LINE = "#1A1A1A"
LINE_SOFT = "#101010"
LINE_STRONG = "#2C2C2C"
WHITE = "#FFFFFF"
TEXT = "#F4F4F4"
TEXT_DIM = "#A6A6A6"
TEXT_MUTED = "#666666"
TEXT_FAINT = "#3C3C3C"

GRID = "#0B0B0B"
GRID_STRONG = "#111111"
GRID_ACCENT = "#181818"

# --- metrics ---------------------------------------------------------------
CARD_RADIUS = 0
SIDEBAR_EXPANDED = 220
SIDEBAR_COLLAPSED = 64
CONTENT_MARGIN = 34

FONT_STACK = "'Segoe UI Variable Display', 'Segoe UI', Inter, 'Helvetica Neue', Arial"
MONO_STACK = "'Cascadia Mono', 'Consolas', 'SF Mono', 'Courier New', monospace"


def qcolor(value: str) -> QColor:
    return QColor(value)


# --- runtime UI preferences ------------------------------------------------
class UISettings:
    """Small set of live design switches (kept separate from AnimationManager)."""

    def __init__(self):
        self.hover_effects = True
        self.grid_backdrop = True
        self.compact_cards = False

    def configure(self, config):
        config = config or {}
        self.hover_effects = bool(config.get("hover_effects", True))
        self.grid_backdrop = bool(config.get("grid_backdrop", True))
        self.compact_cards = bool(config.get("compact_cards", False))


UI = UISettings()


# --- painting helpers ------------------------------------------------------
def draw_grid(painter: QPainter, rect, step: int = 56,
              color: str = GRID, strong: str = GRID_STRONG) -> None:
    """Draws the faint technical grid used behind every page."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    x, i = rect.left(), 0
    while x <= rect.right():
        painter.setPen(QPen(QColor(strong if i % 4 == 0 else color), 1))
        painter.drawLine(x, rect.top(), x, rect.bottom())
        x += step
        i += 1
    y, i = rect.top(), 0
    while y <= rect.bottom():
        painter.setPen(QPen(QColor(strong if i % 4 == 0 else color), 1))
        painter.drawLine(rect.left(), y, rect.right(), y)
        y += step
        i += 1
    painter.restore()


def draw_backdrop(painter: QPainter, rect) -> None:
    """Black canvas + grid + a barely visible light bloom in the top-left."""
    painter.fillRect(rect, QColor(BLACK))
    if UI.grid_backdrop:
        draw_grid(painter, rect)
    radius = max(rect.width(), rect.height()) * 0.95
    glow = QRadialGradient(rect.left() + rect.width() * 0.16,
                           rect.top(), radius)
    glow.setColorAt(0.0, QColor(255, 255, 255, 9))
    glow.setColorAt(0.45, QColor(255, 255, 255, 3))
    glow.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillRect(rect, glow)
    shade = QLinearGradient(0, rect.bottom() - 190, 0, rect.bottom())
    shade.setColorAt(0.0, QColor(0, 0, 0, 0))
    shade.setColorAt(1.0, QColor(0, 0, 0, 110))
    painter.fillRect(rect, shade)


def draw_corner_ticks(painter: QPainter, rect, color: str = TEXT_MUTED,
                      size: int = 10, width: int = 1) -> None:
    """Draws four sharp L-shaped ticks in the corners of *rect*."""
    pen = QPen(QColor(color))
    pen.setWidth(width)
    painter.setPen(pen)
    x1, y1, x2, y2 = rect.left(), rect.top(), rect.right(), rect.bottom()
    painter.drawLine(x1, y1, x1 + size, y1)
    painter.drawLine(x1, y1, x1, y1 + size)
    painter.drawLine(x2 - size, y1, x2, y1)
    painter.drawLine(x2, y1, x2, y1 + size)
    painter.drawLine(x1, y2 - size, x1, y2)
    painter.drawLine(x1, y2, x1 + size, y2)
    painter.drawLine(x2 - size, y2 - size, x2, y2 - size)
    painter.drawLine(x2, y2 - size, x2, y2)


def draw_scanline(painter: QPainter, rect, phase: float,
                  color: str = "#FFFFFF") -> None:
    """Moving highlight used by skeleton cards."""
    painter.save()
    painter.setClipRect(rect)
    band = max(40, rect.width() * 0.28)
    x = -band + (rect.width() + band * 2) * phase
    grad = QLinearGradient(x, 0, x + band, 0)
    base = QColor(color)
    transparent = QColor(color)
    transparent.setAlpha(0)
    base.setAlpha(18)
    grad.setColorAt(0.0, transparent)
    grad.setColorAt(0.5, base)
    grad.setColorAt(1.0, transparent)
    painter.fillRect(QRectF(x, rect.top(), band, rect.height()), grad)
    painter.restore()


# --- animations ------------------------------------------------------------
ANIMATION_SPEEDS = {"fast": 0.65, "normal": 1.0, "smooth": 1.5}
ANIMATION_STYLES = ("slide", "fade")


class AnimationManager:
    """Central switch for interface animations (enable / speed / style)."""

    def __init__(self):
        self.enabled_animations = True
        self.speed = "normal"
        self.style = "slide"

    def configure(self, config):
        self.enabled_animations = bool(config.get("animations", True))
        speed = str(config.get("animation_speed", "normal"))
        self.speed = speed if speed in ANIMATION_SPEEDS else "normal"
        style = str(config.get("animation_style", "slide"))
        self.style = style if style in ANIMATION_STYLES else "slide"

    def enabled(self) -> bool:
        return self.enabled_animations

    def duration(self, base_ms: int) -> int:
        if not self.enabled_animations:
            return 0
        return max(60, int(base_ms * ANIMATION_SPEEDS.get(self.speed, 1.0)))


ANIM = AnimationManager()


def fade_in_widget(widget, base_duration=200, delay=0, start=0.0):
    """Smoothly fades a widget in by animating its opacity effect."""
    if widget is None or not ANIM.enabled():
        return None
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(start)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(ANIM.duration(base_duration))
    anim.setStartValue(start)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def cleanup():
        try:
            if widget.graphicsEffect() is effect:
                widget.setGraphicsEffect(None)
        except Exception:
            pass

    anim.finished.connect(cleanup)
    widget._fade_animation = anim
    if delay > 0:
        QTimer.singleShot(delay, anim.start)
    else:
        anim.start()
    return anim


def fade_out_widget(widget, base_duration=160, on_done=None):
    """Fades a widget out, then optionally invokes *on_done*."""
    if widget is None:
        if on_done:
            on_done()
        return None
    if not ANIM.enabled():
        if on_done:
            on_done()
        return None
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(1.0)
        widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(ANIM.duration(base_duration))
    anim.setStartValue(effect.opacity())
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.Type.InCubic)
    if on_done:
        anim.finished.connect(on_done)
    anim.start()
    widget._fade_out_animation = anim
    return anim


# --- global stylesheets ----------------------------------------------------
def app_stylesheet() -> str:
    chevron = ""
    close_icon = ""
    try:
        from .utils import ensure_chevron_icon
        chevron = f'image: url("{ensure_chevron_icon()}");'
    except Exception:
        pass
    try:
        from .utils import ensure_close_icon
        close_icon = f'image: url("{ensure_close_icon()}");'
    except Exception:
        pass
    return f"""
        QMainWindow {{ background-color: {BLACK}; }}
        QWidget {{ color: {TEXT}; font-family: {FONT_STACK}; font-size: 13px; }}
        QWidget#Page {{ background: transparent; }}
        QToolTip {{
            background-color: {SURFACE_3}; color: {WHITE};
            border: 1px solid {LINE_STRONG}; padding: 6px 9px; font-size: 11px;
        }}

        QFrame#Sidebar {{ background-color: {SURFACE}; border-right: 1px solid {LINE}; }}
        QFrame#BottomBar {{ background-color: {SURFACE}; border-top: 1px solid {LINE}; }}
        QFrame#Hero {{ background-color: {SURFACE_2}; border: 1px solid {LINE}; }}
        QFrame#StatTile {{ background-color: transparent; border: none; }}
        QFrame#StudioCard {{ background-color: {SURFACE_2}; border: 1px solid {LINE}; }}
        QFrame#RecentTile {{ background-color: {BLACK}; border: 1px solid {LINE}; }}
        QFrame#RecentTile:hover {{ border: 1px solid {WHITE}; }}
        QFrame#Hairline {{ background-color: {LINE}; border: none; }}

        QLabel#Logo {{ color: {WHITE}; font-size: 17px; font-weight: 900; letter-spacing: 3px; }}
        QLabel#LogoMark {{ color: {WHITE}; font-size: 20px; font-weight: 900; }}
        QLabel#Eyebrow {{ color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 3px; }}
        QLabel#PageTitle {{ color: {WHITE}; font-size: 26px; font-weight: 900; letter-spacing: 1px; }}
        QLabel#SectionTitle {{ color: {WHITE}; font-size: 11px; font-weight: 800; letter-spacing: 3px; }}
        QLabel#Muted {{ color: {TEXT_MUTED}; font-size: 11px; }}
        QLabel#Dim {{ color: {TEXT_DIM}; font-size: 12px; }}
        QLabel#Micro {{ color: {TEXT_MUTED}; font-size: 9px; font-weight: 700; letter-spacing: 2px; }}
        QLabel#BigNumber {{ color: {WHITE}; font-size: 24px; font-weight: 900; letter-spacing: -1px; }}
        QLabel#StudioWord {{ color: {WHITE}; font-size: 26px; font-weight: 900; letter-spacing: 4px; }}

        QFrame#GameCard {{
            background-color: {SURFACE_2}; border: none;
        }}

        QTabBar#GameTabs {{
            background-color: {SURFACE};
            border-bottom: 1px solid {LINE};
        }}
        QTabBar#GameTabs::tab {{
            background-color: transparent; color: {TEXT_MUTED};
            border: none; border-right: 1px solid {LINE};
            padding: 0 14px; height: 34px;
            font-size: 10px; font-weight: 700; letter-spacing: 1px;
        }}
        QTabBar#GameTabs::tab:hover {{
            color: {WHITE}; background-color: {SURFACE_2};
        }}
        QTabBar#GameTabs::tab:selected {{
            color: {BLACK}; background-color: {WHITE};
        }}
        QTabBar#GameTabs::tab:selected:hover {{
            background-color: #E6E6E6;
        }}
        QTabBar#GameTabs[gameActive="false"]::tab:selected {{
            color: {TEXT_MUTED}; background-color: transparent;
        }}
        QTabBar#GameTabs[gameActive="false"]::tab:selected:hover {{
            color: {WHITE}; background-color: {SURFACE_2};
        }}
        QTabBar#GameTabs::close-button {{
            {close_icon}
            subcontrol-position: right;
            margin-left: 4px;
        }}
        QTabBar#GameTabs::scroller {{
            width: 44px;
        }}
        QTabBar#GameTabs QToolButton {{
            background-color: {SURFACE};
            border-left: 1px solid {LINE};
        }}
        QTabBar#GameTabs QToolButton:hover {{
            background-color: {SURFACE_2};
        }}

        QScrollArea {{ background: transparent; border: none; }}
        QScrollArea > QWidget > QWidget {{ background: transparent; }}
        QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {LINE_STRONG}; min-height: 40px; }}
        QScrollBar::handle:vertical:hover {{ background: {TEXT_MUTED}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QScrollBar:horizontal {{ background: transparent; height: 6px; margin: 0; }}
        QScrollBar::handle:horizontal {{ background: {LINE_STRONG}; min-width: 40px; }}
        QScrollBar::handle:horizontal:hover {{ background: {TEXT_MUTED}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

        QPushButton {{
            background-color: {SURFACE_2}; color: {TEXT};
            border: 1px solid {LINE_STRONG}; border-radius: 0px;
            padding: 9px 16px; font-size: 10px; font-weight: 700; letter-spacing: 1px;
        }}
        QPushButton:hover {{ border-color: {WHITE}; color: {WHITE}; }}
        QPushButton:pressed {{ background-color: {SURFACE_3}; }}
        QPushButton:focus {{ border-color: {WHITE}; }}
        QPushButton:disabled {{ color: {TEXT_FAINT}; border-color: {LINE}; }}
        QPushButton#Primary {{
            background-color: {WHITE}; color: {BLACK};
            border: 1px solid {WHITE}; font-weight: 800;
        }}
        QPushButton#Primary:hover {{ background-color: {BLACK}; color: {WHITE}; }}
        QPushButton#Ghost {{
            background-color: transparent; color: {TEXT_DIM};
            border: 1px solid {LINE};
        }}
        QPushButton#Ghost:hover {{ color: {WHITE}; border-color: {WHITE}; }}
        QPushButton#Danger {{
            background-color: transparent; color: {TEXT_DIM};
            border: 1px dashed {LINE_STRONG};
        }}
        QPushButton#Danger:hover {{ color: {WHITE}; border-color: {WHITE}; border-style: solid; }}
        QPushButton#WebTool {{
            background-color: transparent; color: {TEXT_DIM};
            border: 1px solid transparent; padding: 0;
            font-size: 16px; font-weight: 600; letter-spacing: 0;
        }}
        QPushButton#WebTool:hover {{ color: {WHITE}; border-color: {LINE_STRONG}; }}
        QPushButton#WebTool:disabled {{ color: {TEXT_FAINT}; }}

        QLineEdit {{
            background-color: {BLACK}; color: {WHITE};
            border: 1px solid {LINE}; padding: 8px 12px; font-size: 11px;
            selection-background-color: {WHITE}; selection-color: {BLACK};
        }}
        QLineEdit:hover {{ border-color: {LINE_STRONG}; }}
        QLineEdit:focus {{ border-color: {WHITE}; }}
        QLineEdit#WebUrl {{
            background-color: {SURFACE_2}; border: 1px solid {LINE};
            padding: 6px 12px; font-size: 11px;
        }}
        QLineEdit#WebUrl:focus {{ border-color: {WHITE}; background-color: {BLACK}; }}

        QComboBox {{
            background-color: {BLACK}; color: {TEXT};
            border: 1px solid {LINE}; padding: 8px 12px; font-size: 11px;
        }}
        QComboBox:hover {{ border-color: {WHITE}; }}
        QComboBox::drop-down {{ border: none; width: 22px; }}
        QComboBox::down-arrow {{ {chevron} width: 10px; height: 6px; }}
        QComboBox QAbstractItemView {{
            background-color: {SURFACE_3}; color: {WHITE};
            border: 1px solid {LINE_STRONG};
            selection-background-color: {WHITE}; selection-color: {BLACK};
            outline: none;
        }}

        QFrame#WebBar {{ background-color: {SURFACE}; border-bottom: 1px solid {LINE}; }}
        QProgressBar#WebProgress {{
            background-color: transparent; border: none; height: 2px;
            text-align: center; color: transparent;
        }}
        QProgressBar#WebProgress::chunk {{ background-color: {WHITE}; }}

        QFrame#Toast {{
            background-color: {SURFACE_2}; border: 1px solid {LINE_STRONG};
        }}
        QLabel#ToastText {{ color: {WHITE}; font-size: 11px; font-weight: 600; }}
        QLabel#ToastIcon {{ color: {WHITE}; font-size: 12px; font-weight: 900; }}

        QFrame#CommandPanel {{
            background-color: {SURFACE_2}; border: 1px solid {LINE_STRONG};
        }}
        QListWidget#CommandList {{
            background: transparent; border: none; outline: none;
        }}
        QListWidget#CommandList::item {{
            background: transparent; border: none;
            border-left: 2px solid transparent;
        }}
        QListWidget#CommandList::item:selected {{
            background-color: {SURFACE_3};
            border-left: 2px solid {WHITE};
        }}

        QMenu {{
            background-color: {SURFACE_2}; color: {WHITE};
            border: 1px solid {LINE_STRONG}; padding: 6px;
        }}
        QMenu::item {{ padding: 8px 26px; }}
        QMenu::item:selected {{ background-color: {WHITE}; color: {BLACK}; }}
        QMenu::separator {{ height: 1px; background: {LINE}; margin: 5px 8px; }}
    """


def dialog_stylesheet() -> str:
    check = ""
    chevron = ""
    try:
        from .utils import ensure_check_icon, ensure_chevron_icon
        check = f'image: url("{ensure_check_icon()}");'
        chevron = f'image: url("{ensure_chevron_icon()}");'
    except Exception:
        pass
    return f"""
        QDialog {{ background-color: {SURFACE}; }}
        QLabel {{ color: {TEXT_DIM}; font-size: 12px; }}
        QLabel#DialogTitle {{ color: {WHITE}; font-size: 22px; font-weight: 900; letter-spacing: 0px; }}
        QLabel#SectionTitle {{ color: {WHITE}; font-size: 11px; font-weight: 800; letter-spacing: 3px; }}
        QLabel#DialogSub {{ color: {TEXT_MUTED}; font-size: 11px; }}
        QLabel#Micro {{ color: {TEXT_MUTED}; font-size: 9px; font-weight: 700; letter-spacing: 2px; }}
        QLineEdit {{
            background-color: {BLACK}; color: {WHITE};
            border: 1px solid {LINE_STRONG}; border-radius: 0px;
            padding: 9px 12px; font-size: 12px;
            selection-background-color: {WHITE}; selection-color: {BLACK};
        }}
        QLineEdit:hover {{ border-color: {TEXT_MUTED}; }}
        QLineEdit:focus {{ border: 1px solid {WHITE}; }}
        QComboBox {{
            background-color: {BLACK}; color: {WHITE};
            border: 1px solid {LINE_STRONG}; border-radius: 0px;
            padding: 9px 12px; font-size: 12px;
        }}
        QComboBox:hover {{ border-color: {WHITE}; }}
        QComboBox::drop-down {{ border: none; width: 22px; }}
        QComboBox::down-arrow {{ {chevron} width: 10px; height: 6px; }}
        QComboBox QAbstractItemView {{
            background-color: {SURFACE_3}; color: {WHITE};
            border: 1px solid {LINE_STRONG}; selection-background-color: {WHITE};
            selection-color: {BLACK}; outline: none;
        }}
        QCheckBox {{ color: {TEXT_DIM}; font-size: 12px; spacing: 10px; }}
        QCheckBox::indicator {{
            width: 16px; height: 16px; background-color: {BLACK};
            border: 1px solid {LINE_STRONG};
        }}
        QCheckBox::indicator:hover {{ border-color: {WHITE}; }}
        QCheckBox::indicator:checked {{
            background-color: {WHITE}; border: 1px solid {WHITE}; {check}
        }}
        QPushButton {{
            background-color: {WHITE}; color: {BLACK}; padding: 10px 22px;
            border: 1px solid {WHITE}; border-radius: 0px;
            font-weight: 800; font-size: 10px; letter-spacing: 1px;
        }}
        QPushButton:hover {{ background-color: {BLACK}; color: {WHITE}; }}
        QPushButton:focus {{ border-color: {WHITE}; }}
        QPushButton:disabled {{ background-color: {SURFACE_3}; color: {TEXT_FAINT}; border-color: {LINE}; }}
        QPushButton#Secondary {{
            background-color: transparent; color: {TEXT};
            border: 1px solid {LINE_STRONG};
        }}
        QPushButton#Secondary:hover {{ border-color: {WHITE}; color: {WHITE}; }}
        QPushButton#Compact {{ padding: 0; font-size: 15px; }}
        QPushButton#Danger {{
            background-color: transparent; color: {WHITE};
            border: 1px dashed {LINE_STRONG};
        }}
        QPushButton#Danger:hover {{ border-color: {WHITE}; border-style: solid; }}
        QScrollArea {{ background: transparent; border: none; }}
        QScrollArea > QWidget > QWidget {{ background: transparent; }}
        QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {LINE_STRONG}; min-height: 40px; }}
        QScrollBar::handle:vertical:hover {{ background: {TEXT_MUTED}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QProgressBar {{
            background-color: {SURFACE_3}; border: none; height: 10px;
            text-align: center; color: transparent;
        }}
        QProgressBar::chunk {{ background-color: {WHITE}; }}
        QToolTip {{
            background-color: {SURFACE_3}; color: {WHITE};
            border: 1px solid {LINE_STRONG}; padding: 6px 9px; font-size: 11px;
        }}
        QFrame#WebBar {{ background-color: {SURFACE}; border-bottom: 1px solid {LINE}; }}
        QLineEdit#WebUrl {{
            background-color: {SURFACE_2}; border: 1px solid {LINE};
            padding: 6px 12px; font-size: 11px;
        }}
        QLineEdit#WebUrl:focus {{ border-color: {WHITE}; background-color: {BLACK}; }}
        QPushButton#WebTool {{
            background-color: transparent; color: {TEXT_DIM};
            border: 1px solid transparent; padding: 0;
            font-size: 16px; font-weight: 600; letter-spacing: 0;
        }}
        QPushButton#WebTool:hover {{ color: {WHITE}; border-color: {LINE_STRONG}; }}
        QPushButton#WebTool:disabled {{ color: {TEXT_FAINT}; }}
        QProgressBar#WebProgress {{
            background-color: transparent; border: none; height: 2px;
            text-align: center; color: transparent;
        }}
        QProgressBar#WebProgress::chunk {{ background-color: {WHITE}; }}
        QFrame#CommandPanel {{
            background-color: {SURFACE_2}; border: 1px solid {LINE_STRONG};
        }}
        QListWidget#CommandList {{ background: transparent; border: none; outline: none; }}
        QListWidget#CommandList::item {{ background: transparent; border: none; }}
        QListWidget#CommandList::item:selected {{ background-color: {WHITE}; }}
    """


def primary_button_style() -> str:
    """Inline style for the main action button."""
    return f"""
        QPushButton {{
            background-color: {WHITE}; color: {BLACK};
            border: 1px solid {WHITE};
            padding: 9px 16px; font-size: 10px;
            font-weight: 800; letter-spacing: 1px;
        }}
        QPushButton:hover {{ background-color: {BLACK}; color: {WHITE}; }}
        QPushButton:pressed {{ background-color: {SURFACE_3}; color: {WHITE}; }}
        QPushButton:focus {{ border-color: {WHITE}; }}
        QPushButton:disabled {{
            background-color: {SURFACE_3}; color: {TEXT_MUTED};
            border-color: {LINE};
        }}
    """


def secondary_button_style() -> str:
    return f"""
        QPushButton {{
            background-color: transparent; color: {TEXT_DIM};
            border: 1px solid {LINE_STRONG};
            padding: 9px 16px; font-size: 10px;
            font-weight: 700; letter-spacing: 1px;
        }}
        QPushButton:hover {{ color: {WHITE}; border-color: {WHITE}; }}
        QPushButton:pressed {{ background-color: {SURFACE_3}; }}
        QPushButton:focus {{ border-color: {WHITE}; }}
    """


def tool_button_style() -> str:
    return f"""
        QPushButton {{
            background-color: {BLACK}; color: {TEXT};
            border: 1px solid {LINE}; padding: 8px 13px;
            font-size: 10px; font-weight: 700; letter-spacing: 1px;
        }}
        QPushButton:hover {{ border-color: {WHITE}; color: {WHITE}; }}
        QPushButton:pressed {{ background-color: {SURFACE_3}; }}
        QPushButton:focus {{ border-color: {WHITE}; }}
    """


def icon_button_style() -> str:
    return f"""
        QPushButton {{
            background-color: transparent; color: {WHITE};
            border: 1px solid {LINE}; padding: 0;
            font-size: 15px; font-weight: 700; letter-spacing: 0;
        }}
        QPushButton:hover {{ background-color: {WHITE}; color: {BLACK}; border-color: {WHITE}; }}
        QPushButton:pressed {{ background-color: {TEXT_DIM}; }}
        QPushButton:focus {{ border-color: {WHITE}; }}
    """


def chip_style(active: bool = False) -> str:
    bg = WHITE if active else "transparent"
    fg = BLACK if active else TEXT_DIM
    border = WHITE if active else LINE
    return f"""
        QPushButton {{
            background-color: {bg}; color: {fg};
            border: 1px solid {border}; padding: 7px 12px;
            font-size: 9px; font-weight: 800; letter-spacing: 1px;
        }}
        QPushButton:hover {{
            color: {BLACK if active else WHITE};
            border-color: {WHITE};
        }}
    """


def menu_stylesheet() -> str:
    return f"""
        QMenu {{
            background-color: {SURFACE_2}; color: {WHITE};
            border: 1px solid {LINE_STRONG}; padding: 6px;
        }}
        QMenu::item {{ padding: 8px 26px; }}
        QMenu::item:selected {{ background-color: {WHITE}; color: {BLACK}; }}
        QMenu::separator {{ height: 1px; background: {LINE}; margin: 5px 8px; }}
    """
