"""Studio page: the Made by One brand, projects and release shortcuts."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QPushButton, QVBoxLayout, QWidget)

from ..i18n import L
from ..paths import (GITHUB_PROFILE, GITHUB_RELEASES_PAGE, VERSION,
                     WEBSITE_URL)
from ..theme import (BLACK, LINE, SURFACE_2, TEXT_DIM, TEXT_MUTED, WHITE,
                     primary_button_style)
from ..widgets.page import Page


def _open_link(url):
    """Studio links open in the in-app browser, not a random external window."""
    from ..web import open_url
    open_url(url)

PROJECTS = (
    ("Devers Launcher", "Light game launcher for .dvp, .zip and .exe games.",
     "https://github.com/Made-by-One/Devers-Launcher"),
    ("Devers Packer", "Packer for .dvp game archives.",
     "https://github.com/Made-by-One/Devers-Packer"),
)


class BrandTile(QFrame):
    def __init__(self, caption, value):
        super().__init__()
        self.setObjectName("StatTile")
        self.setFixedHeight(76)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(1)
        self.value = QLabel(value)
        self.value.setStyleSheet("color: #FFFFFF; font-size: 20px; font-weight: 900; letter-spacing: 1px;")
        caption_label = QLabel(caption.upper())
        caption_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 700; letter-spacing: 2px;"
        )
        layout.addStretch()
        layout.addWidget(self.value)
        layout.addWidget(caption_label)


class Chip(QLabel):
    def __init__(self, text):
        super().__init__(text.upper())
        self.setStyleSheet(
            f"color: {TEXT_DIM}; border: 1px solid {LINE}; padding: 5px 9px;"
            "font-size: 9px; font-weight: 700; letter-spacing: 1px;"
        )


class ProjectRow(QFrame):
    def __init__(self, name, description, url):
        super().__init__()
        self.setStyleSheet(
            f"QFrame {{ background-color: {BLACK}; border: 1px solid {LINE}; }}"
            f"QFrame:hover {{ border-color: {WHITE}; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 10, 10)
        row.setSpacing(12)

        info = QVBoxLayout()
        info.setSpacing(2)
        title = QLabel(name.upper())
        title.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: 800; letter-spacing: 1px; border: none;")
        desc = QLabel(description)
        desc.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; border: none;")
        info.addWidget(title)
        info.addWidget(desc)
        row.addLayout(info, stretch=1)

        open_btn = QPushButton("↗")
        open_btn.setFixedSize(28, 28)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {WHITE}; "
            f"border: 1px solid {LINE}; font-size: 13px; padding: 0; }}"
            f"QPushButton:hover {{ background: {WHITE}; color: {BLACK}; border-color: {WHITE}; }}"
        )
        open_btn.clicked.connect(lambda _=False, u=url: _open_link(u))
        row.addWidget(open_btn)


class StudioPage(Page):
    def __init__(self):
        super().__init__()

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 26, 36, 22)
        root.setSpacing(14)

        # --- header ---------------------------------------------------------
        header = QHBoxLayout()
        header.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        eyebrow = QLabel(L.t("studio.eyebrow").upper())
        eyebrow.setObjectName("Eyebrow")
        title = QLabel(L.t("studio.title").upper())
        title.setObjectName("PageTitle")
        titles.addWidget(eyebrow)
        titles.addWidget(title)
        header.addLayout(titles)
        header.addStretch()

        github_btn = QPushButton(L.t("studio.github").upper() + "  ↗")
        github_btn.setObjectName("Ghost")
        github_btn.setFixedHeight(34)
        github_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        github_btn.clicked.connect(lambda: _open_link(GITHUB_PROFILE))
        site_btn = QPushButton(L.t("studio.open_site").upper() + "  ↗")
        site_btn.setStyleSheet(primary_button_style())
        site_btn.setFixedHeight(34)
        site_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        site_btn.clicked.connect(lambda: _open_link(WEBSITE_URL))
        header.addWidget(github_btn)
        header.addWidget(site_btn)
        root.addLayout(header)

        # --- brand block -----------------------------------------------------
        brand = QFrame()
        brand.setStyleSheet(f"QFrame {{ background-color: {SURFACE_2}; border: 1px solid {LINE}; }}")
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(22, 16, 22, 16)
        bl.setSpacing(18)

        word_box = QVBoxLayout()
        word_box.setSpacing(3)
        word = QLabel("MADE BY ONE")
        word.setObjectName("StudioWord")
        tagline = QLabel(L.t("studio.tagline"))
        tagline.setWordWrap(True)
        tagline.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; border: none;")
        word_box.addWidget(word)
        word_box.addWidget(tagline)
        bl.addLayout(word_box, stretch=1)

        self.tile_products = BrandTile(L.t("studio.products"), f"{len(PROJECTS):02d}")
        self.tile_release = BrandTile(L.t("studio.release"), f"v{VERSION}")
        self.tile_license = BrandTile(L.t("studio.license"), "MIT")
        for tile in (self.tile_products, self.tile_release, self.tile_license):
            tile.setFixedWidth(120)
            bl.addWidget(tile)
        root.addWidget(brand)

        # --- about + projects ------------------------------------------------
        body = QHBoxLayout()
        body.setSpacing(14)

        about = QFrame()
        about.setStyleSheet(f"QFrame#About {{ background-color: {BLACK}; border: 1px solid {LINE}; }}")
        about.setObjectName("About")
        al = QVBoxLayout(about)
        al.setContentsMargins(22, 18, 22, 18)
        al.setSpacing(10)

        about_eyebrow = QLabel(L.t("studio.about_eyebrow").upper())
        about_eyebrow.setObjectName("Eyebrow")
        al.addWidget(about_eyebrow)

        about_title = QLabel(L.t("studio.about_title"))
        about_title.setWordWrap(True)
        about_title.setStyleSheet(f"color: {WHITE}; font-size: 20px; font-weight: 900;")
        al.addWidget(about_title)

        about_text = QLabel(L.t("studio.about"))
        about_text.setWordWrap(True)
        about_text.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; line-height: 19px;")
        al.addWidget(about_text)

        chips = QGridLayout()
        chips.setHorizontalSpacing(6)
        chips.setVerticalSpacing(6)
        for i, key in enumerate(("studio.chip.opensource", "studio.chip.mit",
                                 "studio.chip.windows", "studio.chip.telemetry")):
            chips.addWidget(Chip(L.t(key)), i // 2, i % 2)
        chips.setColumnStretch(2, 1)
        al.addLayout(chips)

        al.addStretch()

        release_line = QFrame()
        release_line.setFixedHeight(1)
        release_line.setStyleSheet(f"background-color: {LINE}; border: none;")
        al.addWidget(release_line)

        release_caption = QLabel(
            f"{L.t('studio.latest_release').upper()}  ·  {L.t('studio.current').upper()}")
        release_caption.setObjectName("Eyebrow")
        al.addWidget(release_caption)

        release_row = QHBoxLayout()
        release_version = QLabel(f"v{VERSION}")
        release_version.setStyleSheet("color: #FFFFFF; font-size: 30px; font-weight: 900;")
        release_row.addWidget(release_version)
        release_row.addStretch()

        notes = QPushButton(L.t("studio.release_page").upper() + "  ↗")
        notes.setObjectName("Secondary")
        notes.setFixedHeight(32)
        notes.setCursor(Qt.CursorShape.PointingHandCursor)
        notes.clicked.connect(lambda: _open_link(GITHUB_RELEASES_PAGE))
        release_row.addWidget(notes)
        al.addLayout(release_row)
        body.addWidget(about, stretch=1)

        side = QWidget()
        side.setFixedWidth(340)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(8)

        projects_title = QLabel(L.t("studio.products_title").upper())
        projects_title.setObjectName("SectionTitle")
        sl.addWidget(projects_title)
        for name, desc, url in PROJECTS:
            sl.addWidget(ProjectRow(name, desc, url))

        sl.addSpacing(10)
        links_title = QLabel(L.t("studio.links").upper())
        links_title.setObjectName("SectionTitle")
        sl.addWidget(links_title)

        link_site = QPushButton(L.t("studio.site").upper() + "  ↗")
        link_site.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_DIM}; border: 1px solid {LINE};"
            "padding: 9px 12px; font-size: 10px; font-weight: 700; letter-spacing: 1px; text-align: left; }"
            f"QPushButton:hover {{ color: {WHITE}; border-color: {WHITE}; }}"
        )
        link_site.setCursor(Qt.CursorShape.PointingHandCursor)
        link_site.clicked.connect(lambda: _open_link(WEBSITE_URL))
        sl.addWidget(link_site)

        link_github = QPushButton("GITHUB  ↗")
        link_github.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_DIM}; border: 1px solid {LINE};"
            "padding: 9px 12px; font-size: 10px; font-weight: 700; letter-spacing: 1px; text-align: left; }"
            f"QPushButton:hover {{ color: {WHITE}; border-color: {WHITE}; }}"
        )
        link_github.setCursor(Qt.CursorShape.PointingHandCursor)
        link_github.clicked.connect(lambda: _open_link(GITHUB_PROFILE))
        sl.addWidget(link_github)

        sl.addStretch()
        body.addWidget(side, stretch=0)
        root.addLayout(body, stretch=1)
