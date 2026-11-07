"""About dialog."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout)

from ..i18n import L
from ..paths import ICON_DIR, WEBSITE_URL
from ..theme import dialog_stylesheet
from ..updates import FadeInDialog


class AboutDialog(FadeInDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(L.t("about.title"))
        self.setWindowIcon(QApplication.windowIcon())
        self.resize(470, 440)
        self.setStyleSheet(dialog_stylesheet())
        self.check_requested = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 35, 40, 30)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        logo_path = ICON_DIR / "logo.png"
        if logo_path.exists():
            sym = QLabel()
            sym.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pm = QPixmap(str(logo_path))
            if not pm.isNull():
                sym.setPixmap(pm.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))
            layout.addWidget(sym)
        else:
            sym = QLabel("✦")
            sym.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sym.setStyleSheet("color: #FFFFFF; font-size: 44px; font-weight: 900;")
            layout.addWidget(sym)

        title = QLabel(L.t("app.title").upper())
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #FFFFFF; font-size: 22px; font-weight: 900; letter-spacing: 2px;")
        layout.addWidget(title)

        ver = QLabel(L.t("about.version"))
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet("color: #6A6A6A; font-size: 10px; letter-spacing: 5px;")
        layout.addWidget(ver)

        layout.addSpacing(10)

        desc = QLabel(L.t("about.description"))
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #8A8A8A; font-size: 12px; line-height: 20px;")
        layout.addWidget(desc)

        layout.addStretch()

        site = QPushButton(L.t("studio.open_site"))
        site.setObjectName("Secondary")
        site.clicked.connect(self._open_site)
        layout.addWidget(site, alignment=Qt.AlignmentFlag.AlignCenter)

        check = QPushButton(L.t("about.check_updates"))
        check.setObjectName("Secondary")
        check.clicked.connect(self._request_check)
        layout.addWidget(check, alignment=Qt.AlignmentFlag.AlignCenter)

        buttons = QHBoxLayout()
        ok = QPushButton(L.t("about.close"))
        ok.clicked.connect(self.accept)
        buttons.addStretch()
        buttons.addWidget(ok)
        buttons.addStretch()
        layout.addLayout(buttons)

    def _open_site(self):
        from ..web import open_url
        open_url(WEBSITE_URL, parent=self)

    def _request_check(self):
        self.check_requested = True
        self.accept()
