"""Game library page with search, filters, sorting and a card grid."""

from PyQt6.QtCore import QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QPixmap
from PyQt6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QLineEdit, QMenu, QPushButton,
                             QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from ..i18n import L
from ..paths import ICON_DIR
from ..theme import (ANIM, BLACK, LINE, LINE_STRONG, SURFACE_3, TEXT,
                     TEXT_DIM, TEXT_MUTED, TEXT_FAINT, UI, WHITE,
                     fade_in_widget, menu_stylesheet, primary_button_style)
from ..utils import get_icon
from ..widgets.cards import (CARD_HEIGHT, CARD_WIDTH, COMPACT_CARD_HEIGHT,
                             COMPACT_CARD_WIDTH, GameCard, SkeletonCard)
from ..widgets.page import Page

TOOL_STYLE = f"""
    QPushButton {{
        background-color: {BLACK}; color: {TEXT};
        border: 1px solid {LINE}; padding: 8px 14px;
        font-size: 10px; font-weight: 700; letter-spacing: 1px;
    }}
    QPushButton:hover {{ border-color: {WHITE}; color: {WHITE}; }}
    QPushButton:pressed {{ background-color: {SURFACE_3}; }}
"""


class LibraryPage(Page):
    play_requested = pyqtSignal(str)
    context_requested = pyqtSignal(str, QPoint)
    favorite_toggled = pyqtSignal(str)
    details_requested = pyqtSignal(str)
    add_requested = pyqtSignal()
    folder_requested = pyqtSignal()
    steam_requested = pyqtSignal()

    def __init__(self, config, favorites_getter, play_times_getter,
                 launch_counts_getter, page_title, show_tools=True):
        super().__init__()
        self.config = config
        self.favorites_getter = favorites_getter
        self.play_times_getter = play_times_getter
        self.launch_counts_getter = launch_counts_getter
        self.current_manifests = {}
        self.card_widgets = {}
        self._skeletons = []
        self.filter_mode = "all"
        self._layout_order = []
        self._layout_sig = None
        self._relayout_timer = QTimer(self)
        self._relayout_timer.setSingleShot(True)
        self._relayout_timer.setInterval(50)
        self._relayout_timer.timeout.connect(self._apply_layout)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(
            lambda: self.render(self.current_manifests))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 26, 36, 22)
        layout.setSpacing(12)

        # --- title row ------------------------------------------------------
        header = QHBoxLayout()
        header.setSpacing(12)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        eyebrow = QLabel(L.t("home.eyebrow").upper())
        eyebrow.setObjectName("Eyebrow")
        title = QLabel(page_title.upper())
        title.setObjectName("PageTitle")
        titles.addWidget(eyebrow)
        titles.addWidget(title)
        header.addLayout(titles)

        self.status = QLabel("")
        self.status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; letter-spacing: 1px;")
        header.addWidget(self.status, alignment=Qt.AlignmentFlag.AlignBottom)
        header.addStretch()

        self.refresh_btn = QPushButton()
        self.refresh_btn.setFixedSize(36, 36)
        self.refresh_btn.setToolTip(L.t("library.refresh"))
        refresh_icon = get_icon("refresh", 16)
        if refresh_icon:
            self.refresh_btn.setIcon(refresh_icon)
            self.refresh_btn.setIconSize(QSize(16, 16))
        else:
            self.refresh_btn.setText("↻")
        self.refresh_btn.setStyleSheet(TOOL_STYLE)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)

        # --- toolbar --------------------------------------------------------
        toolbar_row = QHBoxLayout()
        toolbar_row.setSpacing(8)

        self.add_btn = QPushButton("+  " + L.t("library.add_game").upper())
        self.add_btn.setStyleSheet(primary_button_style())
        self.add_btn.setFixedHeight(34)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setToolTip(L.t("dialog.add.filter"))
        self.add_btn.clicked.connect(self.add_requested)
        self.add_btn.setVisible(show_tools)
        toolbar_row.addWidget(self.add_btn)

        self.more_btn = QPushButton("⋯")
        self.more_btn.setStyleSheet(TOOL_STYLE)
        self.more_btn.setFixedSize(38, 34)
        self.more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more_btn.setToolTip(L.t("library.more"))
        more_menu = QMenu(self.more_btn)
        more_menu.setStyleSheet(menu_stylesheet())
        add_folder = QAction(L.t("library.add_folder"), self)
        add_folder.triggered.connect(self.folder_requested)
        add_steam = QAction(L.t("library.steam"), self)
        add_steam.triggered.connect(self.steam_requested)
        more_menu.addAction(add_folder)
        more_menu.addAction(add_steam)
        self.more_btn.setMenu(more_menu)
        self.more_btn.setVisible(show_tools)
        toolbar_row.addWidget(self.more_btn)

        toolbar_row.addStretch()

        self.filter_buttons = {}
        for mode, key in (("all", "library.filter.all"),
                          ("steam", "library.filter.steam"),
                          ("local", "library.filter.local")):
            btn = QPushButton(L.t(key).upper())
            btn.setCheckable(True)
            btn.setFixedHeight(34)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, m=mode: self.set_filter(m))
            btn.setStyleSheet(self._filter_style(mode == self.filter_mode))
            self.filter_buttons[mode] = btn
            toolbar_row.addWidget(btn)

        self.search = QLineEdit()
        self.search.setPlaceholderText(L.t("library.search_placeholder"))
        self.search.setFixedWidth(210)
        self.search.setStyleSheet(f"""
            QLineEdit {{
                background-color: transparent; color: {WHITE};
                border: none; border-bottom: 1px solid {LINE};
                padding: 8px 4px 8px 22px; font-size: 11px;
            }}
            QLineEdit:hover {{ border-bottom-color: {LINE_STRONG}; }}
            QLineEdit:focus {{ border-bottom-color: {WHITE}; }}
        """)
        search_icon = get_icon("search", 15)
        if search_icon:
            self.search.addAction(search_icon, QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self._schedule_search)
        toolbar_row.addWidget(self.search)

        self.sort_combo = QComboBox()
        self.sort_combo.addItem(L.t("library.sort.name"))
        self.sort_combo.addItem(L.t("library.sort.size"))
        self.sort_combo.addItem(L.t("library.sort.date"))
        self.sort_combo.addItem(L.t("library.sort.time"))
        self.sort_combo.addItem(L.t("library.sort.favorites"))
        self.sort_combo.setMinimumWidth(150)
        self.sort_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {BLACK}; color: {TEXT};
                border: 1px solid {LINE}; padding: 8px 12px; font-size: 11px;
            }}
            QComboBox:hover {{ border-color: {WHITE}; }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background-color: {SURFACE_3}; color: {WHITE};
                border: 1px solid {LINE_STRONG};
                selection-background-color: {WHITE}; selection-color: {BLACK};
                outline: none;
            }}
        """)
        self.sort_combo.currentIndexChanged.connect(lambda: self.render(self.current_manifests))
        toolbar_row.addWidget(self.sort_combo)
        layout.addLayout(toolbar_row)

        # --- grid -----------------------------------------------------------
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.grid_host = QWidget()
        self.grid_host.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(14)
        self.grid.setContentsMargins(0, 4, 0, 4)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.scroll.setWidget(self.grid_host)
        layout.addWidget(self.scroll, stretch=1)

        # --- empty state ----------------------------------------------------
        self.empty_host = QWidget()
        self.empty_host.setStyleSheet("background: transparent;")
        el = QVBoxLayout(self.empty_host)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(14)
        el.addStretch(1)

        self.empty_logo = QLabel()
        self.empty_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_path = ICON_DIR / "logo.png"
        if logo_path.exists():
            pm = QPixmap(str(logo_path))
            if not pm.isNull():
                self.empty_logo.setPixmap(pm.scaled(
                    56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
        if self.empty_logo.pixmap().isNull():
            self.empty_logo.setText("✦")
            self.empty_logo.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 40px;")
        el.addWidget(self.empty_logo, alignment=Qt.AlignmentFlag.AlignCenter)

        self._empty_message = L.t("library.empty")
        self.empty_label = QLabel(self._empty_message)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; line-height: 20px;")
        el.addWidget(self.empty_label, alignment=Qt.AlignmentFlag.AlignCenter)
        el.addStretch(1)

        self.empty_host.setVisible(False)
        layout.addWidget(self.empty_host, stretch=1)

    # -- filters ---------------------------------------------------------
    def _filter_style(self, active):
        color = WHITE if active else TEXT_MUTED
        weight = "800" if active else "600"
        underline = WHITE if active else "transparent"
        return f"""
            QPushButton {{
                background-color: transparent; color: {color};
                border: none; border-bottom: 2px solid {underline};
                padding: 8px 11px; font-size: 10px; font-weight: {weight};
                letter-spacing: 1px;
            }}
            QPushButton:hover {{ color: {WHITE}; }}
        """

    def set_filter(self, mode):
        self.filter_mode = mode
        for key, btn in self.filter_buttons.items():
            btn.setChecked(key == mode)
            btn.setStyleSheet(self._filter_style(key == mode))
        self.render(self.current_manifests)

    # -- rendering -------------------------------------------------------
    def _base_card_width(self):
        return COMPACT_CARD_WIDTH if UI.compact_cards else CARD_WIDTH

    def _clear_skeletons(self):
        for skeleton in self._skeletons:
            try:
                self.grid.removeWidget(skeleton)
                skeleton.hide()
                skeleton.deleteLater()
            except Exception:
                pass
        self._skeletons.clear()

    def _clear_cards(self):
        self._clear_skeletons()
        for card in list(self.card_widgets.values()):
            try:
                self.grid.removeWidget(card)
                card.hide()
                card.deleteLater()
            except Exception:
                pass
        self.card_widgets.clear()
        self._layout_order = []
        self._layout_sig = None
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

    def apply_design(self):
        """Rebuild cards after design settings changed (hover/grid/compact)."""
        self._clear_cards()
        self.repaint_backdrop()
        self.update()

    def _schedule_search(self):
        try:
            delay = int(self.config.get("search_debounce", 170) or 170)
        except (TypeError, ValueError):
            delay = 170
        self._search_timer.start(max(0, min(600, delay)))

    def show_skeleton(self):
        self._clear_cards()
        cols = self._columns()
        spacing = self.grid.spacing()
        margins = self.grid.contentsMargins()
        available = max(320, self.scroll.viewport().width() - margins.left() - margins.right())
        card_width = max(170, (available - spacing * (cols - 1)) // cols)
        height = COMPACT_CARD_HEIGHT if UI.compact_cards else CARD_HEIGHT
        for i in range(min(8, cols * 2)):
            r, c = divmod(i, cols)
            skeleton = SkeletonCard(compact=UI.compact_cards)
            skeleton.setFixedSize(card_width, height)
            self.grid.addWidget(skeleton, r, c)
            self._skeletons.append(skeleton)

    def _columns(self):
        w = self.scroll.viewport().width() if hasattr(self, "scroll") else 800
        cols = max(1, (w - 20) // (self._base_card_width() + 14))
        return min(cols, 6)

    def render(self, manifests):
        self.current_manifests = manifests
        self._clear_skeletons()

        if not manifests:
            self._clear_cards()
            self.empty_label.setText(self._empty_message)
            self.empty_host.setVisible(True)
            self.scroll.setVisible(False)
            self.status.setText("")
            return

        self.empty_host.setVisible(False)
        self.scroll.setVisible(True)

        query = self.search.text().strip().lower()
        favorites = set(self.favorites_getter())
        play_times = self.play_times_getter()
        launch_counts = self.launch_counts_getter()

        items = []
        for key, meta in manifests.items():
            name = meta.get("name", key)
            if query and query not in name.lower():
                continue
            is_steam = meta.get("type") == "steam"
            if self.filter_mode == "steam" and not is_steam:
                continue
            if self.filter_mode == "local" and is_steam:
                continue
            items.append((key, meta))

        mode = self.sort_combo.currentIndex()
        if mode == 0:
            items.sort(key=lambda x: x[1].get("name", "").lower())
        elif mode == 1:
            items.sort(key=lambda x: x[1].get("size", 0), reverse=True)
        elif mode == 2:
            items.sort(key=lambda x: x[1].get("mtime", 0), reverse=True)
        elif mode == 3:
            items.sort(key=lambda x: play_times.get(x[0], 0), reverse=True)
        elif mode == 4:
            items.sort(key=lambda x: (x[0] not in favorites, x[1].get("name", "").lower()))

        show_ext = self.config.get("show_extensions", False)
        wanted = {key for key, _ in items}

        # Recycle cards that are still visible; only build what is new.
        for key in list(self.card_widgets):
            if key not in wanted:
                card = self.card_widgets.pop(key)
                self.grid.removeWidget(card)
                card.hide()
                card.deleteLater()

        new_cards = []
        self._layout_order = []
        for key, meta in items:
            card = self.card_widgets.get(key)
            if card is None:
                card = GameCard(key, meta, is_favorite=key in favorites,
                                show_ext=show_ext,
                                play_time=play_times.get(key, 0),
                                launch_count=launch_counts.get(key, 0),
                                compact=UI.compact_cards)
                card.play_requested.connect(self.play_requested)
                card.context_menu_requested.connect(self.context_requested)
                card.favorite_toggled.connect(self.favorite_toggled)
                card.details_requested.connect(self.details_requested)
                self.card_widgets[key] = card
                new_cards.append(card)
            else:
                card.update_meta(meta, show_ext)
                card.set_favorite(key in favorites)
                card.update_stats(play_time=play_times.get(key, 0),
                                  launch_count=launch_counts.get(key, 0))
            self._layout_order.append(key)

        self._layout_sig = None
        self._apply_layout()

        if ANIM.enabled():
            for i, card in enumerate(new_cards[:24]):
                fade_in_widget(card, 280, delay=min(240, i * 24), start=0.0)

        self.status.setText(L.t("library.found", count=len(items)))

    def _apply_layout(self):
        """(Re)position existing cards for the current viewport width."""
        if not self._layout_order:
            return
        cols = self._columns()
        spacing = self.grid.spacing()
        margins = self.grid.contentsMargins()
        available = max(320, self.scroll.viewport().width() - margins.left() - margins.right())
        card_width = max(170, (available - spacing * (cols - 1)) // cols)

        sig = (cols, card_width, len(self._layout_order))
        if sig == self._layout_sig:
            return
        self._layout_sig = sig

        for i, key in enumerate(self._layout_order):
            r, c = divmod(i, cols)
            card = self.card_widgets.get(key)
            if card is None:
                continue
            card.set_card_width(card_width)
            self.grid.addWidget(card, r, c)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        # The grid may have been built while the page was hidden: reflow now
        # so the first visible frame already has the right column count.
        self._layout_sig = None
        self._apply_layout()
        self._relayout_timer.start()

    def set_empty_message(self, text):
        self._empty_message = text
        self.empty_label.setText(text)

    def set_card_progress(self, key, visible, value=0):
        card = self.card_widgets.get(key)
        if card:
            card.progress.setVisible(visible)
            if visible:
                card.set_progress_value(value)

    def update_card_stats(self, key, play_time=None, launch_count=None):
        card = self.card_widgets.get(key)
        if card:
            card.update_stats(play_time=play_time, launch_count=launch_count)

    def set_card_running(self, key):
        """Marks the one card that belongs to the live session."""
        for card_key, card in self.card_widgets.items():
            try:
                card.set_running(card_key == key)
            except Exception:
                pass

