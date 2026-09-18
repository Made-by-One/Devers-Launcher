# ✦ Devers Launcher

A modern, minimal game launcher for `.dvp` files — created by [Devers Packer](https://github.com/Made-by-One/Devers-Packer).

![Platform](https://img.shields.io/badge/platform-Windows-white)
[![Release](https://img.shields.io/badge/release-v1.0-white)](https://github.com/Made-by-One/Devers-Launcher/releases)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)
[![Made by](https://img.shields.io/badge/Made%20by%20One%20Studio-black)](#)


---

## 🚀 Quick start

1. Download **Devers Launcher** from [Releases](https://github.com/Made-by-One/Devers-Launcher/releases).
2. Run `Devers Launcher.exe` — the `games/` folder is created automatically next to it.
3. Place `.dvp` files into `games/` (or drag & drop them onto the window).
4. Press ▶ on a card — the game is extracted to temp and launched.
5. When the game closes, temp files are cleaned up automatically.

---

## ⚙️ Settings

Accessible from the sidebar:

- **Games folder** — where `.dvp` files live
- **Temp files folder** — where games are extracted; with a "Clear now" button
- **Auto-cleanup** — remove temp files after game closes
- **Show file extensions** — display `.exe` / `.dvp` in card info
- **Start with collapsed sidebar**
- **Language** — pick from the list of available translations

All settings are stored in `devers_config.json`.

---


- ⌨️ **Shortcuts:**
  - `Ctrl+F` — focus search
  - `Ctrl+R` — refresh library
  - `Esc` — return to Home
  - `Ctrl+Q` — quit
  
---

## 🌐 Localization

All UI strings live in `localization/*.json`. English is the base; missing keys fall back to `en.json` automatically.

Currently supported:
- 🇬🇧 English (`en.json`)

**Add your language:**

1. Copy `localization/en.json` to `localization/<code>.json` (e.g. `de.json`).
2. Change `_name` to the native language name (`"Deutsch"`).
3. Change `_code` to the language code (`"de"`).
4. Translate any keys you want — untranslated ones fall back to English.
5. Restart the app — the language will appear in Settings.

---

## 🧱 Two ways to use

### Option 1 — Ready-to-use `.exe` (recommended)

Download the latest `Devers Launcher.exe` from [Releases](https://github.com/Made-by-One/Devers-Launcher/releases) and run it. No Python installation required.

### Option 2 — Run from source (Windows only)

Requirements:
- **Windows 10 / 11**
- **Python 3.10+** — https://www.python.org/downloads/ (check "Add Python to PATH" during installation)

Steps:

```bat
git clone https://github.com/Made-by-One/Devers-Launcher.git
cd Devers-Launcher
pip install -r requirements.txt
python main.py
```

### `requirements.txt`

```
PyQt6>=6.6.0
```

---

## 📂 Project structure

```
Devers-Launcher/
├── LICENSE
├── README.md
├── requirements.txt
├── main.py
├── app.ico
├── devers_gif.gif
├── icons/
│   ├── home.png
│   ├── library.png
│   ├── star.png
│   ├── star_filled.png
│   ├── info.png
│   ├── settings.png
│   ├── tray.png
│   ├── logo.png
│   ├── search.png
│   ├── refresh.png
│   ├── play.png
│   ├── folder.png
│   ├── edit.png
│   └── trash.png
└── localization/
    └── en.json
```

---

## 🔗 Related

- [Devers Packer](https://github.com/Made-by-One/Devers-Packer) — packs game folders into `.dvp` files

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

Made with ✦ by **Made by One Studio**
