"""Application entry point."""

import logging
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from .i18n import L, ensure_default_localization
from .paths import (CONFIG_PATH, DEFAULT_CONFIG, GAMES_DIR, CACHE_DIR, VERSION,
                    ensure_dirs, migrate_legacy, setup_logging)
from .utils import build_app_icon, load_json, save_json

log = logging.getLogger("Devers")


def main(argv=None) -> int:
    ensure_dirs()
    migrate_legacy()
    ensure_dirs()
    setup_logging()
    ensure_default_localization()

    # QtWebEngine needs shared OpenGL contexts, and it must be imported before
    # QApplication exists.  Both calls are harmless when WebEngine is missing.
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    try:
        from PyQt6 import QtWebEngineWidgets  # noqa: F401
    except Exception:
        log.info("QtWebEngine недоступен — ссылки откроются в системном браузере")

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Devers Launcher")
    app.setApplicationVersion(VERSION)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")

    cfg = load_json(CONFIG_PATH, DEFAULT_CONFIG)

    needs_save = False
    if not cfg.get("games_dir") or cfg["games_dir"] in ("games", "games/", ".\\games"):
        cfg["games_dir"] = str(GAMES_DIR)
        needs_save = True
    if not cfg.get("temp_dir") or "DeversGames" in str(cfg["temp_dir"]):
        cfg["temp_dir"] = str(CACHE_DIR)
        needs_save = True
    if needs_save:
        save_json(CONFIG_PATH, cfg)

    L.load_available()
    L.set_language(cfg.get("language", "en"))

    from .theme import UI
    UI.configure(cfg)

    app.setWindowIcon(build_app_icon())

    # Imported late so the localization manager already knows the language.
    from .window import LauncherWindow

    window = LauncherWindow()
    window.show()
    log.info(f"Devers Launcher v{VERSION} запущен")
    return app.exec()
