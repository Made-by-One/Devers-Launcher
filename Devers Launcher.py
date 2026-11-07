"""Devers Launcher — thin entry point.

The application itself lives in the ``devers`` package:

    devers/paths.py      paths, constants, defaults
    devers/i18n.py       localization
    devers/theme.py      monochrome design system + animations
    devers/utils.py      JSON, formatting, icons
    devers/covers.py     cover cache
    devers/games.py      archive scanning, extraction
    devers/steam.py      Steam discovery
    devers/updates.py    update checks/downloads
    devers/widgets/      cards, sidebar
    devers/pages/        home, library, studio
    devers/dialogs/      settings, about, Steam import, game info
    devers/window.py     main window
    devers/app.py        startup

Run with ``python "Devers Launcher.py"`` or build this file with PyInstaller.
"""

import sys
from pathlib import Path

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from devers.app import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())
