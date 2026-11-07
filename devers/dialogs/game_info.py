"""Game info dialog: everything known about one library entry."""

from PyQt6.QtCore import QSize, Qt, QThreadPool
from PyQt6.QtGui import QFontMetrics, QPixmap
from PyQt6.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QLabel,
                             QPushButton, QVBoxLayout, QWidget)

from ..covers import CoverLoader
from ..i18n import L
from ..theme import BLACK, LINE, SURFACE_2, TEXT_DIM, TEXT_MUTED, WHITE, dialog_stylesheet
from ..updates import FadeInDialog
from ..utils import human_size, human_time
from ..widgets.cards import BADGE_LABELS, CoverImage


class GameInfoDialog(FadeInDialog):
    """Returns the chosen action in ``self.action`` (play/open/rename/favorite)."""

    def __init__(self, meta, play_time=0, launch_count=0, is_favorite=False, parent=None):
        super().__init__(parent)
        self.meta = meta
        self.action = None
        self.setWindowTitle(L.t("gameinfo.title"))
        self.setWindowIcon(QApplication.windowIcon())
        self.setStyleSheet(dialog_stylesheet())
        self.setFixedWidth(520)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.cover = CoverImage()
        self.cover.setFixedHeight(210)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setStyleSheet(
            f"background-color: {SURFACE_2}; color: {TEXT_MUTED}; "
            "font-size: 10px; letter-spacing: 3px;"
        )
        self.cover.setText(BADGE_LABELS.get(str(meta.get("type", "")), "GAME"))
        root.addWidget(self.cover)

        if meta.get("cover_path") or meta.get("cover_url") or meta.get("cover_data"):
            data = None
            if meta.get("cover_data"):
                try:
                    data = bytes.fromhex(meta["cover_data"])
                except Exception:
                    data = None
            loader = CoverLoader(str(meta.get("path", "")),
                                 meta.get("cover_path", ""),
                                 meta.get("cover_url", ""), data)
            loader.signals.loaded.connect(self._on_cover)
            self._loader = loader
            QThreadPool.globalInstance().start(loader)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(30, 22, 30, 24)
        bl.setSpacing(12)

        eyebrow = QLabel(BADGE_LABELS.get(str(meta.get("type", "")), "GAME"))
        eyebrow.setObjectName("Eyebrow")
        bl.addWidget(eyebrow)

        name = QLabel(meta.get("name", ""))
        name.setWordWrap(True)
        name.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: 900;")
        bl.addWidget(name)

        stats = QGridLayout()
        stats.setHorizontalSpacing(24)
        stats.setVerticalSpacing(10)
        stats.setContentsMargins(0, 6, 0, 0)
        values = [
            (L.t("gameinfo.playtime"), human_time(play_time) if play_time else L.t("gameinfo.none")),
            (L.t("gameinfo.launches"), str(launch_count or L.t("gameinfo.none"))),
            (L.t("gameinfo.size"), human_size(meta.get("size", 0))),
            (L.t("gameinfo.type"), BADGE_LABELS.get(str(meta.get("type", "")), "—")),
        ]
        for i, (label, value) in enumerate(values):
            cell = QWidget()
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(2)
            cap = QLabel(label.upper())
            cap.setObjectName("Eyebrow")
            val = QLabel(value)
            val.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: 700;")
            cl.addWidget(cap)
            cl.addWidget(val)
            stats.addWidget(cell, i // 2, i % 2)
        bl.addLayout(stats)

        path = meta.get("path", "")
        if path:
            path_label = QLabel()
            fm = QFontMetrics(path_label.font())
            path_label.setText(fm.elidedText(path, Qt.TextElideMode.ElideMiddle, 440))
            path_label.setToolTip(path)
            path_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
            bl.addWidget(path_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        icon_style = (
            "QPushButton { background: transparent; color: #FFFFFF; "
            f"border: 1px solid {LINE}; font-size: 16px; padding: 0; }}"
            "QPushButton:hover { background: #FFFFFF; color: #000000; border-color: #FFFFFF; }"
        )
        fav = QPushButton("★" if is_favorite else "☆")
        fav.setFixedSize(38, 38)
        fav.setToolTip(L.t("card.unfavorite") if is_favorite else L.t("card.favorite"))
        fav.setStyleSheet(icon_style)
        fav.clicked.connect(lambda: self._finish("favorite"))
        open_btn = QPushButton("↗")
        open_btn.setFixedSize(38, 38)
        open_btn.setToolTip(L.t("menu.open_folder"))
        open_btn.setStyleSheet(icon_style)
        open_btn.clicked.connect(lambda: self._finish("open"))
        rename = QPushButton(L.t("menu.rename").upper())
        rename.setObjectName("Secondary")
        rename.setFixedHeight(38)
        rename.clicked.connect(lambda: self._finish("rename"))
        play = QPushButton(L.t("menu.play").upper())
        play.setFixedHeight(38)
        play.setMinimumWidth(110)
        play.clicked.connect(lambda: self._finish("play"))
        buttons.addWidget(fav)
        buttons.addWidget(open_btn)
        buttons.addWidget(rename)
        buttons.addStretch()
        buttons.addWidget(play)
        bl.addSpacing(4)
        bl.addLayout(buttons)

        root.addWidget(body)

    def showEvent(self, event):
        super().showEvent(event)
        self.adjustSize()

    def _on_cover(self, key, image):
        if image.isNull():
            return
        self.cover.set_cover_pixmap(QPixmap.fromImage(image))
        self.cover.setText("")

    def _finish(self, action):
        self.action = action
        self.accept()
