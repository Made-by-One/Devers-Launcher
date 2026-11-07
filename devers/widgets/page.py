"""Shared page surface: black canvas with the faint technical grid."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QWidget

from ..theme import UI, draw_backdrop


class Page(QWidget):
    """Base class for every top-level page.

    The backdrop is painted once by the page itself; child scroll areas and
    layouts stay transparent so the grid shows through everywhere.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, event):
        painter = QPainter(self)
        draw_backdrop(painter, self.rect())
        painter.end()
        super().paintEvent(event)

    def repaint_backdrop(self):
        self.update()
