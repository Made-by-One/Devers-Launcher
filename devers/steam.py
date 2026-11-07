"""Steam library discovery and process snapshots used for play-time tracking."""

import logging
import os
import re
import subprocess
import sys
from pathlib import Path

from .paths import STEAM_CDN_HEADER

log = logging.getLogger("Devers")

STEAM_TOOL_NAMES = (
    "steamworks common redistributables",
    "steam linux runtime",
    "steamvr",
    "proton",
    "steam audio",
)


def find_steam_path(configured: str = ""):
    candidates = []
    if configured:
        candidates.append(os.path.expandvars(configured))

    if os.name == "nt":
        try:
            import winreg
            for root, sub in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            ):
                try:
                    with winreg.OpenKey(root, sub) as key:
                        for value in ("SteamPath", "InstallPath"):
                            try:
                                val, _ = winreg.QueryValueEx(key, value)
                                if val:
                                    candidates.append(val)
                            except OSError:
                                pass
                except OSError:
                    pass
        except ImportError:
            pass
        for env in ("ProgramFiles(x86)", "ProgramFiles"):
            base = os.environ.get(env)
            if base:
                candidates.append(os.path.join(base, "Steam"))
    elif sys.platform == "darwin":
        candidates.append(os.path.expanduser("~/Library/Application Support/Steam"))
    else:
        candidates.extend(os.path.expanduser(p) for p in (
            "~/.steam/steam", "~/.local/share/Steam",
            "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
        ))

    for candidate in candidates:
        try:
            p = Path(candidate)
            if p.is_dir():
                return p
        except OSError:
            continue
    return None


def steam_library_folders(steam_path: Path) -> list:
    folders = [steam_path]
    vdf = steam_path / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        try:
            text = vdf.read_text(encoding="utf-8", errors="ignore")
            for raw in re.findall(r'"path"\s+"([^"]+)"', text, flags=re.I):
                path = Path(raw.replace("\\\\", "\\"))
                if path.is_dir() and path not in folders:
                    folders.append(path)
        except Exception as e:
            log.warning(f"Не удалось прочитать libraryfolders.vdf: {e}")
    return folders


def _parse_steam_acf(path: Path) -> dict:
    data = {}
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return data
    for m in re.finditer(r'"([^"]+)"\s+"([^"]*)"', text):
        data[m.group(1)] = m.group(2)
    return data


def scan_steam_games(steam_path):
    """Returns a list of installed Steam games found in all library folders."""
    if not steam_path:
        return []
    games = []
    seen = set()
    appcache = steam_path / "appcache" / "librarycache"

    for library in steam_library_folders(steam_path):
        steamapps = library / "steamapps"
        if not steamapps.is_dir():
            continue
        try:
            manifests = sorted(steamapps.glob("appmanifest_*.acf"))
        except OSError:
            continue

        for acf in manifests:
            info = _parse_steam_acf(acf)
            appid = info.get("appid") or re.sub(r"\D", "", acf.stem)
            if not appid or appid in seen:
                continue
            name = info.get("name", "").strip()
            if not name or any(tool in name.lower() for tool in STEAM_TOOL_NAMES):
                continue
            installdir = info.get("installdir", "").strip()
            game_path = steamapps / "common" / installdir if installdir else Path("")
            if installdir and not game_path.is_dir():
                continue
            try:
                size = int(info.get("SizeOnDisk", "0") or 0)
            except ValueError:
                size = 0

            cover_local = ""
            cache_dirs = (appcache, library / "appcache" / "librarycache")
            for cache_root in cache_dirs:
                for candidate in (
                    cache_root / f"{appid}_header.jpg",
                    cache_root / f"{appid}_library_600x900.jpg",
                    cache_root / appid / "library_600x900.jpg",
                    cache_root / appid / "library_hero.jpg",
                    cache_root / appid / "header.jpg",
                ):
                    if candidate.exists():
                        cover_local = str(candidate)
                        break
                if cover_local:
                    break

            if not cover_local:
                for cache_root in cache_dirs:
                    cache_dir = cache_root / appid
                    if not cache_dir.is_dir():
                        continue
                    images = []
                    try:
                        for item in cache_dir.iterdir():
                            if item.is_file() and item.suffix.lower() in (".jpg", ".jpeg", ".png"):
                                try:
                                    images.append((item.stat().st_size, item))
                                except OSError:
                                    pass
                    except OSError:
                        pass
                    if images:
                        images.sort(reverse=True)
                        cover_local = str(images[0][1])
                        break

            seen.add(appid)
            games.append({
                "key": f"steam:{appid}",
                "appid": appid,
                "name": name,
                "path": str(game_path) if installdir else "",
                "size": size,
                "cover_path": cover_local,
                "cover_url": STEAM_CDN_HEADER.format(appid=appid),
                "library": str(library),
            })

    games.sort(key=lambda g: g["name"].lower())
    return games


def launch_steam_game(appid: str) -> None:
    url = f"steam://rungameid/{appid}"
    if os.name == "nt":
        os.startfile(url)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", url])
    else:
        subprocess.Popen(["xdg-open", url])


def snapshot_pids():
    """Return {pid: lowercased_name} of currently running processes (best-effort)."""
    procs = {}
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, timeout=8,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            for line in out.stdout.splitlines():
                parts = line.split(",")
                if len(parts) >= 2:
                    name = parts[0].strip('"').lower()
                    pid = parts[1].strip('"')
                    if pid.isdigit():
                        procs[int(pid)] = name
        else:
            out = subprocess.run(["ps", "-A", "-o", "pid=,comm="],
                                 capture_output=True, text=True)
            for line in out.stdout.splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2 and parts[0].strip().isdigit():
                    procs[int(parts[0])] = parts[1].strip().lower()
    except Exception:
        return {}
    return procs


# Processes that are not the game itself; they appear whenever Steam (or the
# OS) reacts to a launch and must not keep a play session "alive".
LAUNCH_NOISE = (
    "steam", "webhelper", "conhost", "cmd.exe", "explorer.exe",
    "searchindexer", "runtimebroker", "svchost", "dwm.exe", "taskhost",
)

# Executables that are never the game itself when scanning an install folder.
EXE_NOISE = (
    "unins", "uninstall", "vcredist", "vc_redist", "dxsetup", "dxwebsetup",
    "dotnet", "install", "setup", "crashhandler", "crashreport",
    "easyanticheat", "eac", "battleye", "beservice", "activation",
    "register", "config", "settings", "update", "helper", "benchmark",
    "editor", "server", "dedicated",
)

# Folders that only contain tools, redistributables or documentation.
EXE_SKIP_DIRS = (
    "_commonredist", "commonredist", "redist", "redistributables", "support",
    "tools", "tool", "editor", "docs", "documentation", "installers",
    "directx", "dotnet", "vcredist", "steamworks", "engine", "crashhandler",
    "easyanticheat", "battleye",
)


def game_exe_names(path, limit=32):
    """Best-effort list of executable names that belong to an installed game.

    Scans the first two folder levels, skipping redistributables and tools.
    The returned names are lower-case, e.g. ``["geometrydash.exe"]``.
    """
    path = str(path or "")
    if not path or not os.path.isdir(path):
        return []
    names = []
    seen = set()

    def add(entry):
        name = entry.name.lower()
        if not name.endswith(".exe") or name in seen:
            return
        if any(name.startswith(noise) for noise in EXE_NOISE):
            return
        seen.add(name)
        names.append(name)

    def scan(folder, depth):
        if depth > 2 or len(names) >= limit:
            return
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return
        for entry in entries:
            try:
                if entry.is_file(follow_symlinks=False):
                    add(entry)
                elif entry.is_dir(follow_symlinks=False) and depth < 2:
                    if entry.name.lower() in EXE_SKIP_DIRS:
                        continue
                    scan(entry.path, depth + 1)
            except OSError:
                continue
            if len(names) >= limit:
                return

    scan(path, 0)
    return names


def resolve_shortcut_target(path):
    """Resolves a Windows ``.lnk`` to its target executable (best effort)."""
    if os.name != "nt" or not path or not os.path.exists(path):
        return ""
    if not path.lower().endswith(".lnk"):
        return path
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{0}');"
        "$s.TargetPath"
    ).format(str(path).replace("'", "''"))
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        target = (out.stdout or "").strip()
        return target if target and os.path.exists(target) else ""
    except Exception:
        return ""


def pids_for_names(names, snapshot=None):
    """Returns process ids whose executable name is in *names*."""
    wanted = {str(n).lower() for n in (names or []) if n}
    if not wanted:
        return []
    procs = snapshot if snapshot is not None else snapshot_pids()
    return [pid for pid, name in procs.items() if name in wanted]


def terminate_pids(pids):
    """Force-closes the given process ids (and their children) on Windows."""
    pids = [str(pid) for pid in (pids or []) if str(pid).isdigit()]
    if not pids:
        return 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW
        args = ["taskkill", "/F", "/T"]
        for pid in pids:
            args.extend(["/PID", pid])
        try:
            subprocess.run(args, capture_output=True, timeout=10,
                           creationflags=flags)
            return len(pids)
        except Exception as e:
            log.warning(f"Не удалось закрыть процессы {pids}: {e}")
            return 0
    try:
        for pid in pids:
            os.kill(int(pid), 15)
        return len(pids)
    except Exception:
        return 0
