"""Sharp command palette (Ctrl+K): jump anywhere, launch anything."""

from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QDialog, QFrame, QGraphicsOpacityEffect,
                             QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QVBoxLayout, QWidget)

from ..i18n import L
from ..theme import (ANIM, LINE, SURFACE_3, TEXT_MUTED, WHITE,
                     app_stylesheet)
from ..utils import get_icon


class CommandRow(QWidget):
    """Two-line result row used inside the palette list."""

    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        category = QLabel(str(action.get("category", "")).upper())
        category.setFixedWidth(78)
        category.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 8px; font-weight: 800; "
            "letter-spacing: 2px; background: transparent;")
        layout.addWidget(category, alignment=Qt.AlignmentFlag.AlignVCenter)

        text = QVBoxLayout()
        text.setSpacing(1)
        title = QLabel(str(action.get("title", "")))
        title.setStyleSheet(
            "color: #FFFFFF; font-size: 12px; font-weight: 700; "
            "background: transparent;")
        subtitle = QLabel(str(action.get("subtitle", "")))
        subtitle.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; background: transparent;")
        text.addWidget(title)
        if action.get("subtitle"):
            text.addWidget(subtitle)
        layout.addLayout(text, stretch=1)

        hint = QLabel("↵")
        hint.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
        layout.addWidget(hint, alignment=Qt.AlignmentFlag.AlignVCenter)


class CommandPalette(QDialog):
    """Full-window dimmed overlay with a focused search panel."""

    def __init__(self, parent, actions):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog |
                            Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self._actions = list(actions)
        self._parent_window = parent.window() if parent else None
        self.setStyleSheet(app_stylesheet())

        self.panel = QFrame(self)
        self.panel.setObjectName("CommandPanel")
        self.panel.setFixedSize(700, 510)

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 14, 18, 12)
        header_layout.setSpacing(9)

        top = QHBoxLayout()
        top.setSpacing(8)
        brand = QLabel("DEVERS  //  COMMAND")
        brand.setStyleSheet(
            "color: #FFFFFF; font-size: 9px; font-weight: 800; "
            "letter-spacing: 3px; background: transparent;")
        top.addWidget(brand)
        top.addStretch()
        esc = QLabel("ESC")
        esc.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 8px; font-weight: 800; "
            "letter-spacing: 2px; background: transparent;")
        top.addWidget(esc)
        header_layout.addLayout(top)

        self.search = QLineEdit()
        self.search.setPlaceholderText(L.t("command.placeholder"))
        self.search.setStyleSheet(
            f"QLineEdit {{ background-color: #000000; color: {WHITE};"
            f" border: 1px solid {LINE}; padding: 11px 13px;"
            " font-size: 13px; letter-spacing: 0; }}"
            "QLineEdit:focus { border: 1px solid #FFFFFF; }")
        icon = get_icon("search", 16)
        if icon is not None:
            self.search.addAction(icon, QLineEdit.ActionPosition.LeadingPosition)
        header_layout.addWidget(self.search)
        panel_layout.addWidget(header)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {LINE}; border: none;")
        panel_layout.addWidget(line)

        self.list = QListWidget()
        self.list.setObjectName("CommandList")
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setVerticalScrollMode(
            QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setSpacing(0)
        self.list.itemActivated.connect(self._activate_item)
        self.list.itemClicked.connect(self._activate_item)
        panel_layout.addWidget(self.list, stretch=1)

        footer = QLabel(L.t("command.hint"))
        footer.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 8px; font-weight: 700; "
            "letter-spacing: 1px; background: transparent;")
        footer.setContentsMargins(18, 8, 18, 11)
        panel_layout.addWidget(footer)

        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._activate_current)

        self._fade = QGraphicsOpacityEffect(self)
        self._fade.setOpacity(0.0)
        self.setGraphicsEffect(self._fade)
        self._fade_anim = QPropertyAnimation(self._fade, b"opacity", self)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # -- geometry / painting ----------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if self._parent_window is not None:
            self.setGeometry(self._parent_window.geometry())
        self._center_panel()
        self._filter(self.search.text())
        self.search.setFocus()
        self.search.selectAll()
        if ANIM.enabled():
            self._fade_anim.stop()
            self._fade_anim.setDuration(ANIM.duration(160))
            self._fade_anim.setStartValue(0.0)
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.start()
        else:
            self._fade.setOpacity(1.0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._center_panel()

    def _center_panel(self):
        x = max(0, (self.width() - self.panel.width()) // 2)
        y = max(0, (self.height() - self.panel.height()) // 2 - 20)
        self.panel.move(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 198))
        painter.end()

    def mousePressEvent(self, event):
        if not self.panel.geometry().contains(event.pos()):
            self.reject()
            return
        super().mousePressEvent(event)

    # -- filtering ---------------------------------------------------------
    def _filter(self, query):
        query = str(query or "").strip().lower()
        scored = []
        for index, action in enumerate(self._actions):
            title = str(action.get("title", "")).lower()
            subtitle = str(action.get("subtitle", "")).lower()
            category = str(action.get("category", "")).lower()
            if not query:
                score = 1
            elif title.startswith(query):
                score = 400
            elif query in title:
                score = 260
            elif query in subtitle:
                score = 140
            elif query in category:
                score = 60
            else:
                score = 0
            if score:
                scored.append((score, index, action))
        scored.sort(key=lambda item: (-item[0], item[1]))

        self.list.clear()
        for _, _, action in scored[:80]:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, action)
            item.setSizeHint(QSize(0, 58 if action.get("subtitle") else 46))
            self.list.addItem(item)
            self.list.setItemWidget(item, CommandRow(action))

        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            item = QListWidgetItem(L.t("command.empty"))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setSizeHint(QSize(0, 56))
            self.list.addItem(item)

    def _activate_current(self):
        item = self.list.currentItem()
        if item is not None:
            self._activate_item(item)

    def _activate_item(self, item):
        action = item.data(Qt.ItemDataRole.UserRole)
        if not action:
            return
        callback = action.get("callback")
        self.accept()
        if callback:
            QTimer.singleShot(0, callback)

    # -- keyboard ----------------------------------------------------------
    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.reject()
            return
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            count = self.list.count()
            if count:
                row = self.list.currentRow()
                step = 1 if key == Qt.Key.Key_Down else -1
                self.list.setCurrentRow((row + step) % count)
                self.list.scrollToItem(self.list.currentItem())
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._activate_current()
            return
        super().keyPressEvent(event)
