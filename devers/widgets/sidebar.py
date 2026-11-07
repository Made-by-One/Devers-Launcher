"""Sharp monochrome navigation rail with a sliding active marker."""

from PyQt6.QtCore import (QEasingCurve, QParallelAnimationGroup, QPropertyAnimation,
                          QRectF, QSize, Qt, QTimer, pyqtProperty, pyqtSignal)
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

from ..i18n import L
from ..paths import VERSION
from ..theme import (ANIM, BLACK, LINE, SIDEBAR_COLLAPSED, SIDEBAR_EXPANDED,
                     SURFACE, TEXT_MUTED, WHITE)
from ..utils import ensure_web_icon, get_icon, get_icon_tinted


class NavRail(QWidget):
    """Holds the page buttons and paints the sliding white marker behind them.

    The marker is drawn in ``paintEvent`` (before children), so buttons stay on
    top of it and their labels remain readable while it travels.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.active_key = None
        self._indicator_y = 0.0
        self._indicator_h = 40
        self._animation = None
        self.buttons = {}

        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(2)

    # -- animated float property -------------------------------------------
    def _get_indicator_y(self):
        return self._indicator_y

    def _set_indicator_y(self, value):
        self._indicator_y = float(value)
        self.update()

    indicatorY = pyqtProperty(float, fget=_get_indicator_y, fset=_set_indicator_y)

    def add_button(self, key, button):
        self.buttons[key] = button
        self.box.addWidget(button)

    def target_y(self):
        button = self.buttons.get(self.active_key)
        return float(button.y()) if button is not None else 0.0

    def place(self, animate=True):
        """Moves the marker to the active button, optionally animating."""
        button = self.buttons.get(self.active_key)
        if button is None:
            return
        self._indicator_h = button.height()
        target = float(button.y())
        duration = ANIM.duration(260) if animate else 0
        if duration <= 0 or abs(target - self._indicator_y) < 0.5:
            self._indicator_y = target
            self.update()
            return

        anim = QPropertyAnimation(self, b"indicatorY", self)
        anim.setDuration(duration)
        anim.setStartValue(self._indicator_y)
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._animation = anim

    def paintEvent(self, event):
        if self.active_key is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(
            QRectF(0, self._indicator_y, self.width(), self._indicator_h),
            QColor(WHITE),
        )
        painter.end()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: self.place(animate=False))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()


class CollapsibleSidebar(QFrame):
    page_changed = pyqtSignal(str)
    command_requested = pyqtSignal()

    EXPANDED = SIDEBAR_EXPANDED
    COLLAPSED = SIDEBAR_COLLAPSED

    def __init__(self):
        super().__init__()
        try:
            ensure_web_icon()
        except Exception:
            pass
        self.setObjectName("Sidebar")
        self.is_collapsed = False
        self.setMinimumWidth(self.EXPANDED)
        self.setMaximumWidth(self.EXPANDED)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(14, 18, 14, 16)
        self.root.setSpacing(4)

        # --- brand row ------------------------------------------------------
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self.symbol_btn = QPushButton()
        self.symbol_btn.setObjectName("SymbolBtn")
        self.symbol_btn.setFixedSize(32, 32)
        self.symbol_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.symbol_btn.setToolTip(L.t("sidebar.collapse"))
        symbol_icon = get_icon_tinted("logo", 17, QColor(BLACK))
        if symbol_icon is not None:
            self.symbol_btn.setIcon(symbol_icon)
            self.symbol_btn.setIconSize(QSize(17, 17))
        self.symbol_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {WHITE}; color: {BLACK};
                border: none; padding: 0;
            }}
            QPushButton:hover {{ background-color: #D8D8D8; }}
        """)
        self.symbol_btn.clicked.connect(self.toggle)
        header.addWidget(self.symbol_btn)

        brand = QVBoxLayout()
        brand.setContentsMargins(0, 0, 0, 0)
        brand.setSpacing(0)
        self.logo = QLabel("DEVERS")
        self.logo.setObjectName("Logo")
        self.version_label = QLabel(f"LAUNCHER {VERSION}")
        self.version_label.setObjectName("Eyebrow")
        brand.addWidget(self.logo)
        brand.addWidget(self.version_label)
        header.addLayout(brand)
        header.addStretch()
        self.root.addLayout(header)
        self.root.addSpacing(22)

        # --- navigation -----------------------------------------------------
        self.nav_buttons = {}
        self.rail = NavRail()
        self.btn_home = self._make_nav("home", L.t("sidebar.home"), "home")
        self.btn_library = self._make_nav("library", L.t("sidebar.library"), "library")
        self.btn_fav = self._make_nav("star", L.t("sidebar.favorites"), "favorites")
        self.btn_studio = self._make_nav("logo", L.t("sidebar.studio"), "studio")
        self.btn_web = self._make_nav("web", L.t("sidebar.web"), "web")
        self.root.addWidget(self.rail)
        self.root.addStretch()

        self._divider()

        self.btn_command = self._make_nav(
            "search", L.t("sidebar.command"), "command", is_toggle=False)
        self.btn_command.setToolTip(L.t("command.hint_short"))
        self.btn_command.clicked.connect(self.command_requested)
        self.root.addWidget(self.btn_command)

        self.btn_about = self._make_nav("info", L.t("sidebar.about"), "about", is_toggle=False)
        self.btn_settings = self._make_nav("settings", L.t("sidebar.settings"), "settings", is_toggle=False)
        self.root.addWidget(self.btn_about)
        self.root.addWidget(self.btn_settings)

        self.root.addSpacing(10)
        self.footer = QLabel("MADE BY ONE")
        self.footer.setObjectName("Eyebrow")
        self.footer.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; letter-spacing: 2px; padding-left: 4px;")
        self.root.addWidget(self.footer)

        self.set_active("home", animate=False)

    def _divider(self):
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {LINE}; border: none;")
        self.root.addSpacing(8)
        self.root.addWidget(line)
        self.root.addSpacing(8)

    def _make_nav(self, icon_name, text, key, is_toggle=True):
        btn = QPushButton()
        btn.setObjectName("NavButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(text)
        btn.setFixedHeight(40)
        btn.setProperty("nav_icon_name", icon_name)
        btn.setProperty("nav_text", text.upper())
        if is_toggle:
            btn.setCheckable(True)
            btn.clicked.connect(lambda: self.switch(key))
        self.nav_buttons[key] = btn
        if is_toggle:
            self.rail.add_button(key, btn)
        else:
            self._render(btn, self.is_collapsed)
        return btn

    def _nav_icon(self, name, size):
        """Always returns a real icon: missing artwork falls back to the mark."""
        return get_icon(name, size) or get_icon("logo", size)

    def _render(self, btn, collapsed):
        icon_name = btn.property("nav_icon_name")
        text = btn.property("nav_text")
        active = btn.isChecked()

        if collapsed:
            icon = self._nav_icon(icon_name, 20)
            if icon is not None:
                btn.setIcon(icon)
                btn.setIconSize(QSize(20, 20))
                btn.setText("")
            btn.setStyleSheet(self._style(True, active))
        else:
            icon = self._nav_icon(icon_name, 16)
            if icon is not None:
                btn.setIcon(icon)
                btn.setIconSize(QSize(16, 16))
                btn.setText(f"   {text}")
            else:
                btn.setText(f"   {text}")
            btn.setStyleSheet(self._style(False, active))

    def _style(self, collapsed, active):
        padding = "0" if collapsed else "0 12px"
        align = "center" if collapsed else "left"
        bg = "transparent"
        fg = BLACK if active else "#8C8C8C"
        weight = "800" if active else "600"
        fs = "17px" if collapsed else "10px"
        hover_bg = "transparent" if active else SURFACE
        hover_fg = BLACK if active else WHITE
        return f"""
            QPushButton {{
                background-color: {bg}; color: {fg};
                border: none; padding: {padding};
                font-size: {fs}; font-weight: {weight};
                letter-spacing: 1px; text-align: {align};
            }}
            QPushButton:hover {{
                background-color: {hover_bg}; color: {hover_fg};
            }}
        """

    def set_active(self, key, animate=True):
        if key is None:
            # A game tab is open: no sidebar entry is highlighted.
            self.rail.active_key = None
            for btn in self.rail.buttons.values():
                if btn.isChecked():
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
                self._render(btn, self.is_collapsed)
            self.rail.update()
            return
        self.rail.active_key = key if key in self.rail.buttons else self.rail.active_key
        for k, btn in self.rail.buttons.items():
            want = (k == key)
            if btn.isChecked() != want:
                btn.blockSignals(True)
                btn.setChecked(want)
                btn.blockSignals(False)
            self._render(btn, self.is_collapsed)
        self.rail.place(animate=animate and ANIM.enabled())

    def switch(self, key):
        if self.rail.active_key == key:
            # Re-check: clicking the active checkable button toggles it off.
            self.set_active(key, animate=False)
            return
        self.set_active(key)
        self.page_changed.emit(key)

    def toggle(self):
        self.is_collapsed = not self.is_collapsed
        target = self.COLLAPSED if self.is_collapsed else self.EXPANDED
        duration = ANIM.duration(240)

        if duration <= 0:
            self.setMinimumWidth(target)
            self.setMaximumWidth(target)
        else:
            a1 = QPropertyAnimation(self, b"minimumWidth")
            a1.setDuration(duration)
            a1.setStartValue(self.width())
            a1.setEndValue(target)
            a1.setEasingCurve(QEasingCurve.Type.InOutCubic)
            a2 = QPropertyAnimation(self, b"maximumWidth")
            a2.setDuration(duration)
            a2.setStartValue(self.width())
            a2.setEndValue(target)
            a2.setEasingCurve(QEasingCurve.Type.InOutCubic)

            group = QParallelAnimationGroup()
            group.addAnimation(a1)
            group.addAnimation(a2)
            group.start()
            self._anim_group = group

        self.logo.setVisible(not self.is_collapsed)
        self.version_label.setVisible(not self.is_collapsed)
        self.footer.setVisible(not self.is_collapsed)
        for k, btn in self.nav_buttons.items():
            self._render(btn, self.is_collapsed)
        self.rail.place(animate=False)
