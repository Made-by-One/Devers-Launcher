"""Steam library import dialog."""

import logging

from PyQt6.QtCore import QThread, QThreadPool, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QApplication, QCheckBox, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QScrollArea, QVBoxLayout,
                             QWidget)

from ..covers import CoverLoader
from ..i18n import L
from ..steam import scan_steam_games
from ..theme import dialog_stylesheet
from ..updates import FadeInDialog
from ..utils import human_size

log = logging.getLogger("Devers")


class SteamScanThread(QThread):
    scanned = pyqtSignal(list, str)

    def __init__(self, steam_path):
        super().__init__()
        self.steam_path = steam_path

    def run(self):
        try:
            games = scan_steam_games(self.steam_path)
            self.scanned.emit(games, "")
        except Exception as e:
            log.exception("Ошибка сканирования Steam")
            self.scanned.emit([], str(e))


class SteamImportDialog(FadeInDialog):
    """Lists installed Steam games and lets the user add them to the library."""

    def __init__(self, steam_path, existing_keys, parent=None):
        super().__init__(parent)
        self.steam_path = steam_path
        self.existing_keys = set(existing_keys)
        self.games = []
        self.rows = []
        self.cover_loaders = []
        self.scanner = None

        self.selected_keys = set()
        self.setWindowTitle(L.t("steam.title"))
        self.setWindowIcon(QApplication.windowIcon())
        self.resize(700, 660)
        self.setStyleSheet(dialog_stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 25, 30, 25)
        root.setSpacing(12)

        title = QLabel(L.t("steam.title").upper())
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        sub = QLabel(L.t("steam.subtitle"))
        sub.setObjectName("DialogSub")
        root.addWidget(sub)

        self.path_label = QLabel(L.t("steam.path", path=str(steam_path) if steam_path
                                     else L.t("settings.steam_missing")))
        self.path_label.setStyleSheet("color: #5C5C5C; font-size: 11px;")
        root.addWidget(self.path_label)

        hint = QLabel(L.t("steam.selection_hint"))
        hint.setStyleSheet("color: #6A6A6A; font-size: 11px;")
        root.addWidget(hint)

        self.search = QLineEdit()
        self.search.setPlaceholderText(L.t("steam.search_placeholder"))
        self.search.textChanged.connect(self._populate)
        root.addWidget(self.search)

        self.status = QLabel(L.t("steam.scanning"))
        self.status.setStyleSheet("color: #8A8A8A; font-size: 11px;")
        root.addWidget(self.status)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.host = QWidget()
        self.list_layout = QVBoxLayout(self.host)
        self.list_layout.setContentsMargins(2, 2, 2, 2)
        self.list_layout.setSpacing(4)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.host)
        root.addWidget(self.scroll, stretch=1)

        tools = QHBoxLayout()
        self.sel_all = QPushButton(L.t("steam.select_all"))
        self.sel_all.setObjectName("Secondary")
        self.sel_none = QPushButton(L.t("steam.select_none"))
        self.sel_none.setObjectName("Secondary")
        self.sel_all.clicked.connect(lambda: self._set_all(True))
        self.sel_none.clicked.connect(lambda: self._set_all(False))
        tools.addWidget(self.sel_all)
        tools.addWidget(self.sel_none)
        tools.addStretch()
        root.addLayout(tools)

        buttons = QHBoxLayout()
        cancel = QPushButton(L.t("settings.cancel"))
        cancel.setObjectName("Secondary")
        cancel.clicked.connect(self.reject)
        self.add_btn = QPushButton(L.t("steam.apply_selection", count=0))
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self._accept_selection)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(self.add_btn)
        root.addLayout(buttons)

        self._start_scan()

    def _start_scan(self):
        if not self.steam_path:
            self.status.setText(L.t("steam.not_found"))
            return
        self.scanner = SteamScanThread(self.steam_path)
        self.scanner.scanned.connect(self._on_scanned)
        self.scanner.start()

    def _on_scanned(self, games, error):
        if error:
            self.status.setText(L.t("update.check_failed", error=error))
            return
        self.games = games
        if not games:
            self.status.setText(L.t("steam.empty"))
            return
        self.status.setText(L.t("steam.found", count=len(games)))
        self._populate()

    def _populate(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.rows.clear()

        query = self.search.text().strip().lower()
        for game in self.games:
            if query and query not in game["name"].lower():
                continue
            already = game["key"] in self.existing_keys
            row = QWidget()
            row.setStyleSheet("QWidget { background: transparent; }")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(6, 4, 6, 4)
            rl.setSpacing(10)

            cb = QCheckBox()
            cb.setChecked(already)
            cb.setToolTip(L.t("steam.selection_hint"))
            cb.stateChanged.connect(self._update_count)

            thumb = QLabel()
            thumb.setFixedSize(92, 43)
            thumb.setStyleSheet("background-color: #121212; color: #5C5C5C; font-size: 10px;")
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setText("STEAM" if not (game.get("cover_path") or game.get("cover_url")) else "")
            if game.get("cover_path") or game.get("cover_url"):
                loader = CoverLoader(game["key"], game.get("cover_path", ""), game.get("cover_url", ""))
                loader.signals.loaded.connect(lambda key, img, lbl=thumb: self._set_thumb(lbl, img))
                self.cover_loaders.append(loader)
                QThreadPool.globalInstance().start(loader)

            info = QVBoxLayout()
            info.setSpacing(2)
            name = QLabel(game["name"])
            name.setWordWrap(True)
            name.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: 600;")
            meta = QLabel(human_size(game.get("size", 0)))
            meta.setStyleSheet("color: #6A6A6A; font-size: 10px;")
            if already:
                meta.setText(f"{human_size(game.get('size', 0))}  •  {L.t('steam.already_added')}")
            info.addWidget(name)
            info.addWidget(meta)

            rl.addWidget(cb)
            rl.addWidget(thumb)
            rl.addLayout(info, stretch=1)
            self.list_layout.addWidget(row)
            self.rows.append((game, cb))

        self._update_count()

    def _set_thumb(self, label, image):
        if image.isNull():
            return
        pm = QPixmap.fromImage(image).scaled(
            92, 43, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation)
        label.setPixmap(pm)

    def _set_all(self, checked):
        for _, cb in self.rows:
            cb.setChecked(checked)

    def _selected(self):
        return [game for game, cb in self.rows if cb.isChecked()]

    def _update_count(self):
        count = len(self._selected())
        self.add_btn.setText(L.t("steam.apply_selection", count=count))
        self.add_btn.setEnabled(bool(self.rows))

    def _accept_selection(self):
        self.selected_games = self._selected()
        self.selected_keys = {game["key"] for game in self.selected_games}
        self.accept()

    def closeEvent(self, event):
        if self.scanner and self.scanner.isRunning():
            self.scanner.wait(1500)
        super().closeEvent(event)
