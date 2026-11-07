"""Update checking, downloading and the related dialogs."""

import json
import logging
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel,
                             QProgressBar, QPushButton, QScrollArea,
                             QVBoxLayout, QWidget)

from .i18n import L
from .paths import (GITHUB_RELEASES_API, GITHUB_RELEASES_PAGE, ICON_DIR,
                    UPDATES_DIR, USER_AGENT, VERSION)
from .theme import (ANIM, BLACK, LINE, LINE_STRONG, SURFACE, SURFACE_2,
                    SURFACE_3, TEXT_DIM, TEXT_MUTED, WHITE, dialog_stylesheet,
                    fade_in_widget)
from .utils import human_size

log = logging.getLogger("Devers")


def _open_link(url):
    """Routes release links to the in-app browser when it is available."""
    from .web import open_url
    open_url(url)


def parse_version(value: str) -> tuple:
    numbers = re.findall(r"\d+", str(value or ""))
    return tuple(int(n) for n in numbers[:4]) if numbers else (0,)


def is_newer_version(remote: str, current: str) -> bool:
    def normalized(v):
        parts = list(parse_version(v))
        while len(parts) < 4:
            parts.append(0)
        return tuple(parts)
    return normalized(remote) > normalized(current)


def fetch_latest_release() -> dict:
    req = urllib.request.Request(
        GITHUB_RELEASES_API,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Unexpected GitHub response")
    return data


def pick_update_asset(assets):
    """Picks the best release asset for the current platform."""
    if not assets:
        return None
    if os.name == "nt":
        preferred = (".zip", ".exe", ".msi")
    elif sys.platform == "darwin":
        preferred = (".dmg", ".zip")
    else:
        preferred = (".appimage", ".tar.gz", ".zip")

    best = None
    for asset in assets:
        name = str(asset.get("name", "")).lower()
        for rank, ext in enumerate(preferred):
            if name.endswith(ext):
                score = (len(preferred) - rank) * 10
                if os.name == "nt" and "windows" in name:
                    score += 5
                if best is None or score > best[0]:
                    best = (score, asset)
                break
    return best[1] if best else None


class UpdateCheckThread(QThread):
    checked = pyqtSignal(dict, str)

    def run(self):
        try:
            release = fetch_latest_release()
            self.checked.emit(release, "")
        except urllib.error.HTTPError as e:
            message = f"GitHub API {e.code}"
            if e.code == 403:
                message = "GitHub API rate limit (403)"
            self.checked.emit({}, message)
        except Exception as e:
            log.warning(f"Не удалось проверить обновления: {e}")
            self.checked.emit({}, str(e))


class UpdateDownloadThread(QThread):
    progress = pyqtSignal(int)
    downloaded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, asset, expected_version):
        super().__init__()
        self.asset = asset
        self.expected_version = expected_version

    def run(self):
        try:
            UPDATES_DIR.mkdir(parents=True, exist_ok=True)
            name = self.asset.get("name") or f"Devers-Launcher-{self.expected_version}.zip"
            safe_name = re.sub(r"[^\w.\- ]+", "_", name)
            target = UPDATES_DIR / safe_name
            partial = target.with_name(target.name + ".part")
            req = urllib.request.Request(
                self.asset["browser_download_url"],
                headers={"User-Agent": USER_AGENT},
            )
            total = int(self.asset.get("size", 0) or 0)
            received = 0
            with urllib.request.urlopen(req, timeout=30) as resp, open(partial, "wb") as f:
                total = int(resp.headers.get("Content-Length") or total or 0)
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
                    if total > 0:
                        self.progress.emit(min(100, int(received * 100 / total)))
                    else:
                        self.progress.emit(-1)
            if total > 0 and received < total:
                raise IOError(f"Incomplete download ({received}/{total} bytes)")
            os.replace(partial, target)
            self.progress.emit(100)
            self.downloaded.emit(str(target))
        except Exception as e:
            log.exception("Ошибка загрузки обновления")
            self.failed.emit(str(e))


class FadeInDialog(QDialog):
    """Dialog that fades in smoothly when opened (respects animation settings)."""

    def showEvent(self, event):
        super().showEvent(event)
        fade_in_widget(self, 190)


def dialog_logo_label(size=52):
    """Returns the app logo (or a fallback mark) as a QLabel."""
    label = QLabel()
    label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    logo_path = ICON_DIR / "logo.png"
    if logo_path.exists():
        pm = QPixmap(str(logo_path))
        if not pm.isNull():
            label.setPixmap(pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
            return label
    label.setText("✦")
    label.setStyleSheet(f"color: {WHITE}; font-size: {int(size * 0.7)}px; font-weight: 900;")
    return label


class UpdateCheckDialog(FadeInDialog):
    """Small non-modal dialog shown while the launcher checks GitHub."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(L.t("update.check_title"))
        self.setWindowIcon(QApplication.windowIcon())
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setModal(False)
        self.setFixedSize(420, 190)
        self.setStyleSheet(dialog_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(14)
        header.addWidget(dialog_logo_label(44))

        text_box = QVBoxLayout()
        text_box.setSpacing(4)
        title = QLabel(L.t("update.check_title"))
        title.setObjectName("DialogTitle")
        hint = QLabel(L.t("update.checking_hint"))
        hint.setObjectName("DialogSub")
        hint.setWordWrap(True)
        text_box.addWidget(title)
        text_box.addWidget(hint)
        header.addLayout(text_box, stretch=1)
        layout.addLayout(header)

        layout.addStretch()

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(10)
        layout.addWidget(self.progress)


def _notes_plain_text(raw: str) -> str:
    """Turns release markdown into readable plain text for the notes panel."""
    text = raw or ""
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"[*_`>]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or "—"


class UpdateInfoDialog(FadeInDialog):
    """Styled message dialog for update checks (up to date, errors)."""

    def __init__(self, title, message, detail="", primary_text=None, retry=False,
                 secondary_text=None, page_url="", parent=None):
        super().__init__(parent)
        self.retry_requested = False
        self.setWindowTitle(title)
        self.setWindowIcon(QApplication.windowIcon())
        self.setStyleSheet(dialog_stylesheet())
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(14)
        header.addWidget(dialog_logo_label(48), alignment=Qt.AlignmentFlag.AlignTop)

        text_box = QVBoxLayout()
        text_box.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("DialogTitle")
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 13px;")
        text_box.addWidget(title_label)
        text_box.addWidget(message_label)
        if detail:
            detail_label = QLabel(detail)
            detail_label.setWordWrap(True)
            detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            detail_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            text_box.addWidget(detail_label)
        header.addLayout(text_box, stretch=1)
        layout.addLayout(header)

        buttons = QHBoxLayout()
        buttons.addStretch()
        if page_url:
            page = QPushButton(L.t("update.page"))
            page.setObjectName("Secondary")
            page.clicked.connect(lambda: _open_link(page_url))
            buttons.addWidget(page)
        if secondary_text:
            close_btn = QPushButton(secondary_text)
            close_btn.setObjectName("Secondary")
            close_btn.clicked.connect(self.reject)
            buttons.addWidget(close_btn)
        primary = QPushButton(primary_text or L.t("update.close"))
        primary.clicked.connect(self._primary)
        buttons.addWidget(primary)
        layout.addLayout(buttons)

    def _primary(self):
        self.retry_requested = True
        self.accept()


class UpdateDialog(FadeInDialog):
    """Shows release notes and downloads the new build."""

    install_requested = pyqtSignal(str)

    def __init__(self, release, asset, parent=None):
        super().__init__(parent)
        self.release = release
        self.asset = asset
        self.downloader = None
        self.downloaded_path = ""

        version = str(release.get("tag_name") or release.get("name") or "?")
        self.setWindowTitle(L.t("update.title"))
        self.setWindowIcon(QApplication.windowIcon())
        self.setStyleSheet(dialog_stylesheet())
        self.resize(600, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(14)
        header.addWidget(dialog_logo_label(52), alignment=Qt.AlignmentFlag.AlignTop)

        head_text = QVBoxLayout()
        head_text.setSpacing(4)
        title = QLabel(L.t("update.title"))
        title.setObjectName("DialogTitle")
        found = QLabel(L.t("update.found", version=version, current=VERSION))
        found.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        found.setWordWrap(True)
        head_text.addWidget(title)
        head_text.addWidget(found)
        header.addLayout(head_text, stretch=1)
        layout.addLayout(header)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        current_chip = QLabel(f"v{VERSION}")
        current_chip.setStyleSheet(f"color: {TEXT_DIM}; background-color: {SURFACE_2}; "
                                   f"border: 1px solid {LINE}; padding: 4px 12px; font-size: 11px;")
        arrow = QLabel("→")
        arrow.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px;")
        new_chip = QLabel(version if version.lower().startswith("v") else f"v{version}")
        new_chip.setStyleSheet(f"color: {BLACK}; background-color: {WHITE}; "
                               "padding: 4px 12px; font-size: 11px; font-weight: bold;")
        chips.addWidget(current_chip)
        chips.addWidget(arrow)
        chips.addWidget(new_chip)
        chips.addStretch()
        if asset:
            asset_label = QLabel(L.t("update.asset", name=asset.get("name", ""),
                                      size=human_size(asset.get("size", 0))))
            asset_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            chips.addWidget(asset_label)
        layout.addLayout(chips)

        notes_title = QLabel(L.t("update.notes"))
        notes_title.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; letter-spacing: 1px;")
        layout.addWidget(notes_title)

        body = QLabel(_notes_plain_text(str(release.get("body") or "")))
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        body.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px; background-color: {SURFACE_2}; "
                           f"border: 1px solid {LINE}; padding: 14px;")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_host = QWidget()
        sh = QVBoxLayout(scroll_host)
        sh.setContentsMargins(0, 0, 0, 0)
        sh.addWidget(body)
        sh.addStretch()
        scroll.setWidget(scroll_host)
        layout.addWidget(scroll, stretch=1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(12)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.status = QLabel("")
        self.status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        page = QPushButton(L.t("update.page"))
        page.setObjectName("Secondary")
        page.clicked.connect(
            lambda: _open_link(release.get("html_url") or GITHUB_RELEASES_PAGE))
        later = QPushButton(L.t("update.later"))
        later.setObjectName("Secondary")
        later.clicked.connect(self.reject)
        self.download_btn = QPushButton(L.t("update.download"))
        self.download_btn.setEnabled(asset is not None)
        self.download_btn.clicked.connect(self._start_download)
        buttons.addWidget(page)
        buttons.addStretch()
        buttons.addWidget(later)
        buttons.addWidget(self.download_btn)
        layout.addLayout(buttons)

        if asset is None:
            self.status.setText(L.t("update.no_asset"))
        elif not getattr(sys, "frozen", False):
            self.status.setText(L.t("update.source_hint"))

    def _start_download(self):
        if not self.asset or self.downloader:
            return
        self.download_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.status.setText(L.t("update.downloading", percent=0))
        self.downloader = UpdateDownloadThread(self.asset, self.release.get("tag_name", VERSION))
        self.downloader.progress.connect(self._on_progress)
        self.downloader.downloaded.connect(self._on_downloaded)
        self.downloader.failed.connect(self._on_failed)
        self.downloader.start()

    def _on_progress(self, value):
        if value < 0:
            self.progress.setRange(0, 0)
            self.status.setText(L.t("update.downloading", percent="..."))
            return
        self.progress.setRange(0, 100)
        self.progress.setValue(value)
        self.status.setText(L.t("update.downloading", percent=value))

    def _on_downloaded(self, path):
        self.downloaded_path = path
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status.setText(L.t("update.ready"))
        self.install_requested.emit(path)
        self.accept()

    def _on_failed(self, error):
        self.progress.setVisible(False)
        self.download_btn.setEnabled(True)
        self.status.setText(L.t("update.download_error", error=error))

    def closeEvent(self, event):
        if self.downloader and self.downloader.isRunning():
            self.downloader.wait(1500)
        super().closeEvent(event)
