"""Launcher settings dialog."""

import os
import shutil
import sys

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                             QFileDialog, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QMessageBox, QPushButton, QScrollArea,
                             QVBoxLayout, QWidget)

from ..covers import clear_cover_cache, cover_cache_stats
from ..i18n import L
from ..paths import (CACHE_DIR, CONFIG_PATH, GAMES_DIR, WEBSITE_URL,
                     open_path)
from ..steam import find_steam_path
from ..theme import dialog_stylesheet
from ..updates import FadeInDialog
from ..utils import dir_size, get_icon, human_size, save_json


class SettingsDialog(FadeInDialog):
    settings_applied = pyqtSignal(dict)
    check_updates_requested = pyqtSignal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config.copy()
        self.setWindowTitle(L.t("settings.title"))
        self.setWindowIcon(QApplication.windowIcon())
        height = 820
        try:
            screen = QApplication.primaryScreen()
            if screen is not None:
                height = min(height, max(560, screen.availableGeometry().height() - 80))
        except Exception:
            pass
        self.resize(620, height)
        self.setStyleSheet(dialog_stylesheet())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(35, 30, 35, 20)
        layout.setSpacing(12)
        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        title = QLabel(L.t("settings.title").upper())
        title.setObjectName("DialogTitle")
        layout.addWidget(title)
        sub = QLabel(L.t("settings.subtitle"))
        sub.setObjectName("DialogSub")
        layout.addWidget(sub)
        layout.addSpacing(10)

        sec1 = QLabel(L.t("settings.section.storage"))
        sec1.setObjectName("SectionTitle")
        layout.addWidget(sec1)

        games_row = QHBoxLayout()
        self.games_input = QLineEdit(self.config.get("games_dir", str(GAMES_DIR)))
        self.games_input.setCursorPosition(0)
        games_row.addWidget(self.games_input)
        games_row.addWidget(self._browse_button(self._browse))
        row = QHBoxLayout()
        lbl = QLabel(L.t("settings.games_dir"))
        lbl.setFixedWidth(150)
        row.addWidget(lbl)
        row.addLayout(games_row)
        layout.addLayout(row)

        layout.addSpacing(10)
        sec2 = QLabel(L.t("settings.section.temp"))
        sec2.setObjectName("SectionTitle")
        layout.addWidget(sec2)

        self.temp_label = QLabel("")
        self.temp_label.setStyleSheet("color: #8A8A8A; font-size: 12px;")
        self.temp_label.setWordWrap(True)
        layout.addWidget(self.temp_label)
        self._update_temp()

        tr = QHBoxLayout()
        open_btn = QPushButton(L.t("settings.open_folder"))
        open_btn.setObjectName("Secondary")
        open_btn.clicked.connect(self._open_temp)
        clear_btn = QPushButton(L.t("settings.clear_now"))
        clear_btn.setObjectName("Danger")
        clear_btn.clicked.connect(self._clear_temp)
        tr.addWidget(open_btn)
        tr.addWidget(clear_btn)
        layout.addLayout(tr)

        self.auto_cleanup = QCheckBox(L.t("settings.auto_cleanup"))
        self.auto_cleanup.setChecked(self.config.get("auto_cleanup", True))
        layout.addWidget(self.auto_cleanup)

        layout.addSpacing(10)
        sec3 = QLabel(L.t("settings.section.interface"))
        sec3.setObjectName("SectionTitle")
        layout.addWidget(sec3)

        self.show_ext = QCheckBox(L.t("settings.show_ext"))
        self.show_ext.setChecked(self.config.get("show_extensions", False))
        layout.addWidget(self.show_ext)

        self.start_collapsed = QCheckBox(L.t("settings.start_collapsed"))
        self.start_collapsed.setChecked(self.config.get("sidebar_collapsed", False))
        layout.addWidget(self.start_collapsed)

        layout.addSpacing(10)
        sec_steam = QLabel(L.t("settings.section.steam"))
        sec_steam.setObjectName("SectionTitle")
        layout.addWidget(sec_steam)

        self.auto_steam = QCheckBox(L.t("settings.auto_steam"))
        self.auto_steam.setChecked(self.config.get("auto_steam_import", True))
        layout.addWidget(self.auto_steam)

        steam_row = QHBoxLayout()
        detected = find_steam_path(self.config.get("steam_path", ""))
        self.steam_input = QLineEdit(str(detected) if detected else self.config.get("steam_path", ""))
        self.steam_input.setPlaceholderText(L.t("settings.steam_missing"))
        self.steam_input.setCursorPosition(0)
        steam_row.addWidget(self.steam_input)
        steam_row.addWidget(self._browse_button(self._browse_steam))
        row_steam = QHBoxLayout()
        lbl_steam = QLabel(L.t("settings.steam_path"))
        lbl_steam.setFixedWidth(150)
        row_steam.addWidget(lbl_steam)
        row_steam.addLayout(steam_row)
        layout.addLayout(row_steam)

        layout.addSpacing(10)
        sec_updates = QLabel(L.t("settings.section.updates"))
        sec_updates.setObjectName("SectionTitle")
        layout.addWidget(sec_updates)

        self.check_updates = QCheckBox(L.t("settings.check_updates"))
        self.check_updates.setChecked(self.config.get("check_updates", True))
        layout.addWidget(self.check_updates)

        upd_row = QHBoxLayout()
        check_now = QPushButton(L.t("settings.check_now"))
        check_now.setObjectName("Secondary")
        check_now.clicked.connect(self._request_update_check)
        upd_row.addWidget(check_now)
        upd_row.addStretch()
        layout.addLayout(upd_row)

        layout.addSpacing(10)
        sec_cache = QLabel(L.t("settings.section.cache"))
        sec_cache.setObjectName("SectionTitle")
        layout.addWidget(sec_cache)

        self.covers_label = QLabel("")
        self.covers_label.setStyleSheet("color: #8A8A8A; font-size: 12px;")
        self.covers_label.setWordWrap(True)
        layout.addWidget(self.covers_label)
        self._update_covers()

        covers_row = QHBoxLayout()
        clear_covers = QPushButton(L.t("settings.clear_covers"))
        clear_covers.setObjectName("Danger")
        clear_covers.clicked.connect(self._clear_covers)
        covers_row.addWidget(clear_covers)
        covers_row.addStretch()
        layout.addLayout(covers_row)

        layout.addSpacing(10)
        sec_anim = QLabel(L.t("settings.section.animations"))
        sec_anim.setObjectName("SectionTitle")
        layout.addWidget(sec_anim)

        self.animations_cb = QCheckBox(L.t("settings.animations"))
        self.animations_cb.setChecked(self.config.get("animations", True))
        layout.addWidget(self.animations_cb)

        anim_style_row = QHBoxLayout()
        lbl_astyle = QLabel(L.t("settings.animation_style"))
        lbl_astyle.setFixedWidth(150)
        self.anim_style_combo = QComboBox()
        self.anim_style_combo.addItem(L.t("settings.animation_style.slide"), "slide")
        self.anim_style_combo.addItem(L.t("settings.animation_style.fade"), "fade")
        self._select_combo_value(self.anim_style_combo, self.config.get("animation_style", "slide"))
        anim_style_row.addWidget(lbl_astyle)
        anim_style_row.addWidget(self.anim_style_combo)
        layout.addLayout(anim_style_row)

        anim_speed_row = QHBoxLayout()
        lbl_aspeed = QLabel(L.t("settings.animation_speed"))
        lbl_aspeed.setFixedWidth(150)
        self.anim_speed_combo = QComboBox()
        self.anim_speed_combo.addItem(L.t("settings.animation_speed.fast"), "fast")
        self.anim_speed_combo.addItem(L.t("settings.animation_speed.normal"), "normal")
        self.anim_speed_combo.addItem(L.t("settings.animation_speed.smooth"), "smooth")
        self._select_combo_value(self.anim_speed_combo, self.config.get("animation_speed", "normal"))
        anim_speed_row.addWidget(lbl_aspeed)
        anim_speed_row.addWidget(self.anim_speed_combo)
        layout.addLayout(anim_speed_row)

        anim_hint = QLabel(L.t("settings.animations_hint"))
        anim_hint.setWordWrap(True)
        anim_hint.setStyleSheet("color: #6A6A6A; font-size: 11px;")
        layout.addWidget(anim_hint)

        self.animations_cb.toggled.connect(self._update_animation_controls)
        self._update_animation_controls(self.animations_cb.isChecked())

        layout.addSpacing(10)
        sec_design = QLabel(L.t("settings.section.design"))
        sec_design.setObjectName("SectionTitle")
        layout.addWidget(sec_design)

        self.hover_effects = QCheckBox(L.t("settings.hover_effects"))
        self.hover_effects.setChecked(self.config.get("hover_effects", True))
        layout.addWidget(self.hover_effects)

        self.grid_backdrop = QCheckBox(L.t("settings.grid_backdrop"))
        self.grid_backdrop.setChecked(self.config.get("grid_backdrop", True))
        layout.addWidget(self.grid_backdrop)

        self.compact_cards = QCheckBox(L.t("settings.compact_cards"))
        self.compact_cards.setChecked(self.config.get("compact_cards", False))
        layout.addWidget(self.compact_cards)

        design_hint = QLabel(L.t("settings.design_hint"))
        design_hint.setWordWrap(True)
        design_hint.setStyleSheet("color: #6A6A6A; font-size: 11px;")
        layout.addWidget(design_hint)

        layout.addSpacing(10)
        sec_web = QLabel(L.t("settings.section.web"))
        sec_web.setObjectName("SectionTitle")
        layout.addWidget(sec_web)

        self.web_in_app = QCheckBox(L.t("settings.web_in_app"))
        self.web_in_app.setChecked(self.config.get("web_in_app", True))
        layout.addWidget(self.web_in_app)

        self.web_cache = QCheckBox(L.t("settings.web_cache"))
        self.web_cache.setChecked(self.config.get("web_cache", True))
        layout.addWidget(self.web_cache)

        web_row = QHBoxLayout()
        lbl_web = QLabel(L.t("settings.web_home"))
        lbl_web.setFixedWidth(150)
        self.web_home_input = QLineEdit(
            str(self.config.get("web_home") or WEBSITE_URL))
        self.web_home_input.setCursorPosition(0)
        web_row.addWidget(lbl_web)
        web_row.addWidget(self.web_home_input)
        layout.addLayout(web_row)

        web_buttons = QHBoxLayout()
        clear_web = QPushButton(L.t("settings.clear_web_cache"))
        clear_web.setObjectName("Danger")
        clear_web.clicked.connect(self._clear_web_cache)
        web_buttons.addWidget(clear_web)
        web_buttons.addStretch()
        layout.addLayout(web_buttons)

        web_hint = QLabel(L.t("settings.web_hint"))
        web_hint.setWordWrap(True)
        web_hint.setStyleSheet("color: #6A6A6A; font-size: 11px;")
        layout.addWidget(web_hint)

        layout.addSpacing(10)
        sec4 = QLabel(L.t("settings.section.language"))
        sec4.setObjectName("SectionTitle")
        layout.addWidget(sec4)

        lang_row = QHBoxLayout()
        self.lang_combo = QComboBox()
        items = sorted(L.available.items(), key=lambda x: (x[0] != "en", x[1].lower()))
        for code, name in items:
            self.lang_combo.addItem(name, code)
        cur = self.config.get("language", "en")
        for i in range(self.lang_combo.count()):
            if self.lang_combo.itemData(i) == cur:
                self.lang_combo.setCurrentIndex(i)
                break
        lang_row.addWidget(self.lang_combo)
        row_lang = QHBoxLayout()
        lbl_lang = QLabel(L.t("settings.language"))
        lbl_lang.setFixedWidth(150)
        row_lang.addWidget(lbl_lang)
        row_lang.addLayout(lang_row)
        layout.addLayout(row_lang)

        layout.addStretch()

        btns = QHBoxLayout()
        btns.setContentsMargins(35, 10, 35, 20)
        reset = QPushButton(L.t("settings.reset"))
        reset.setObjectName("Secondary")
        reset.clicked.connect(self._reset)
        cancel = QPushButton(L.t("settings.cancel"))
        cancel.setObjectName("Secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton(L.t("settings.save"))
        save.clicked.connect(self._save)
        btns.addWidget(reset)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(save)
        outer.addLayout(btns)

    @staticmethod
    def _select_combo_value(combo, value):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _update_animation_controls(self, enabled):
        self.anim_style_combo.setEnabled(bool(enabled))
        self.anim_speed_combo.setEnabled(bool(enabled))

    def _browse_button(self, slot):
        btn = QPushButton("…")
        btn.setObjectName("Compact")
        btn.setFixedSize(44, 36)
        btn.setToolTip(L.t("settings.browse"))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        icon = get_icon("folder", 16)
        if icon:
            btn.setIcon(icon)
            btn.setIconSize(QSize(16, 16))
            btn.setText("")
        btn.clicked.connect(slot)
        return btn

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, L.t("settings.games_dir"))
        if d:
            self.games_input.setText(d)

    def _browse_steam(self):
        d = QFileDialog.getExistingDirectory(self, L.t("settings.steam_path"))
        if d:
            self.steam_input.setText(d)

    def _update_covers(self):
        count, size = cover_cache_stats()
        self.covers_label.setText(L.t("settings.covers_info", count=count, size=human_size(size)))

    def _clear_covers(self):
        try:
            clear_cover_cache()
            self._update_covers()
            QMessageBox.information(self, L.t("settings.section.cache"), L.t("settings.covers_cleared"))
        except Exception as e:
            QMessageBox.critical(self, L.t("settings.section.cache"),
                                 L.t("settings.temp_clear.error", error=str(e)))

    def _clear_web_cache(self):
        try:
            from ..web import clear_web_cache
            clear_web_cache()
            QMessageBox.information(self, L.t("settings.section.web"),
                                    L.t("settings.web_cache_cleared"))
        except Exception as e:
            QMessageBox.critical(self, L.t("settings.section.web"),
                                 L.t("settings.temp_clear.error", error=str(e)))

    def _request_update_check(self):
        self._save()
        self.check_updates_requested.emit()

    def _update_temp(self):
        t = self.config.get("temp_dir", str(CACHE_DIR))
        self.temp_label.setText(L.t("settings.temp_info", path=t, size=human_size(dir_size(t))))

    def _open_temp(self):
        t = self.config.get("temp_dir", str(CACHE_DIR))
        os.makedirs(t, exist_ok=True)
        open_path(t)

    def _clear_temp(self):
        t = self.config.get("temp_dir", str(CACHE_DIR))
        if not os.path.exists(t):
            QMessageBox.information(self, L.t("settings.clear_now"), L.t("settings.temp_missing"))
            return
        r = QMessageBox.question(self, L.t("settings.clear_now"),
                                 L.t("settings.temp_clear.confirm", size=human_size(dir_size(t))))
        if r == QMessageBox.StandardButton.Yes:
            try:
                shutil.rmtree(t, ignore_errors=True)
                os.makedirs(t, exist_ok=True)
                self._update_temp()
                QMessageBox.information(self, L.t("settings.clear_now"), L.t("settings.temp_clear.done"))
            except Exception as e:
                QMessageBox.critical(self, L.t("settings.clear_now"),
                                     L.t("settings.temp_clear.error", error=str(e)))

    def _reset(self):
        r = QMessageBox.question(self, L.t("settings.reset"), L.t("settings.reset.confirm"))
        if r == QMessageBox.StandardButton.Yes:
            self.games_input.setText(str(GAMES_DIR))
            self.auto_cleanup.setChecked(True)
            self.show_ext.setChecked(False)
            self.start_collapsed.setChecked(False)
            self.auto_steam.setChecked(True)
            self.check_updates.setChecked(True)
            self.animations_cb.setChecked(True)
            self._select_combo_value(self.anim_style_combo, "slide")
            self._select_combo_value(self.anim_speed_combo, "normal")
            self.hover_effects.setChecked(True)
            self.grid_backdrop.setChecked(True)
            self.compact_cards.setChecked(False)
            self.web_in_app.setChecked(True)
            self.web_cache.setChecked(True)
            self.web_home_input.setText(WEBSITE_URL)
            self.steam_input.setText(str(find_steam_path() or ""))
            for i in range(self.lang_combo.count()):
                if self.lang_combo.itemData(i) == "en":
                    self.lang_combo.setCurrentIndex(i)
                    break

    def _save(self):
        self.config["games_dir"] = self.games_input.text()
        self.config["auto_cleanup"] = self.auto_cleanup.isChecked()
        self.config["show_extensions"] = self.show_ext.isChecked()
        self.config["sidebar_collapsed"] = self.start_collapsed.isChecked()
        self.config["auto_steam_import"] = self.auto_steam.isChecked()
        self.config["steam_path"] = self.steam_input.text().strip()
        self.config["check_updates"] = self.check_updates.isChecked()
        self.config["animations"] = self.animations_cb.isChecked()
        self.config["animation_style"] = self.anim_style_combo.currentData() or "slide"
        self.config["animation_speed"] = self.anim_speed_combo.currentData() or "normal"
        self.config["hover_effects"] = self.hover_effects.isChecked()
        self.config["grid_backdrop"] = self.grid_backdrop.isChecked()
        self.config["compact_cards"] = self.compact_cards.isChecked()
        self.config["web_in_app"] = self.web_in_app.isChecked()
        self.config["web_cache"] = self.web_cache.isChecked()
        home = self.web_home_input.text().strip() or WEBSITE_URL
        if "://" not in home:
            home = "https://" + home
        self.config["web_home"] = home
        self.config["language"] = self.lang_combo.currentData()
        save_json(CONFIG_PATH, self.config)
        self.settings_applied.emit(self.config)
        self.accept()
