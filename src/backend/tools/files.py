"""
Herramientas de archivos confinadas a raíces autorizadas, información del
sistema y páginas de Configuración de Windows.

Todas las rutas se resuelven (incluidos enlaces simbólicos) y deben quedar
dentro de JARVIS_FILE_WRITE_ROOTS (o el Escritorio por defecto). Los archivos
de credenciales nunca se listan ni se manipulan. Las operaciones que modifican
archivos son opt-in (JARVIS_FILE_TOOLS_ENABLED) y la política de herramientas
exige confirmación explícita para mover, renombrar, eliminar y organizar.
"""

from __future__ import annotations

import fnmatch
import os
import platform
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil
from core.service_container import services
from langchain_core.tools import tool

from tools.system import _allowed_file_write_roots

IS_WINDOWS = sys.platform == "win32"

MAX_LIST_ENTRIES = 200
MAX_SEARCH_RESULTS = 50
MAX_SEARCH_VISITED = 20000
MAX_SEARCH_SECONDS = 8.0

# Never listed, copied, moved or deleted by JARVIS tools.
_PROTECTED_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
    "credentials*.json",
    "client_secret*.json",
    ".spotify_cache*",
    ".cache-*",
    ".git-credentials",
    ".netrc",
)
_PROTECTED_DIRS = frozenset({".git", ".ssh", ".aws", ".gnupg"})

ORGANIZE_CATEGORIES = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".heic", ".tif", ".tiff"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".md", ".xls", ".xlsx", ".csv", ".ppt", ".pptx"},
    "Audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"},
    "Video": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Installers": {".exe", ".msi", ".msix"},
    "Code": {".py", ".js", ".ts", ".html", ".css", ".json", ".java", ".c", ".cpp", ".cs", ".go", ".rs", ".ipynb"},
}

# Windows Settings pages reachable through ms-settings: URIs.
WINDOWS_SETTINGS_PAGES = {
    "display": "ms-settings:display",
    "sound": "ms-settings:sound",
    "bluetooth": "ms-settings:bluetooth",
    "wifi": "ms-settings:network-wifi",
    "network": "ms-settings:network",
    "battery": "ms-settings:batterysaver",
    "power": "ms-settings:powersleep",
    "apps": "ms-settings:appsfeatures",
    "default_apps": "ms-settings:defaultapps",
    "notifications": "ms-settings:notifications",
    "privacy": "ms-settings:privacy",
    "microphone": "ms-settings:privacy-microphone",
    "camera": "ms-settings:privacy-webcam",
    "windows_update": "ms-settings:windowsupdate",
    "about": "ms-settings:about",
    "storage": "ms-settings:storagesense",
    "language": "ms-settings:regionlanguage",
    "speech": "ms-settings:speech",
    "personalization": "ms-settings:personalization",
}


def _flag(name: str) -> bool:
    return str(os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def file_tools_enabled() -> bool:
    """Mutating file tools are opt-in, like the other system tools."""
    return _flag("JARVIS_FILE_TOOLS_ENABLED") or _flag("JARVIS_SYSTEM_TOOLS_ENABLED")


def _disabled_message() -> str:
    return "File tools are disabled. Set JARVIS_FILE_TOOLS_ENABLED=true to enable them."


def is_protected_path(path: Path) -> bool:
    name = path.name.lower()
    if name == ".env.example":
        return False
    if any(fnmatch.fnmatch(name, pattern) for pattern in _PROTECTED_PATTERNS):
        return True
    return any(part.lower() in _PROTECTED_DIRS for part in path.parts)


def resolve_in_roots(raw_path: str, *, allow_root: bool = True) -> Path | None:
    """Resolve a user path inside the authorized roots, or return None.

    Relative paths are anchored to the first root. Symlinks and ".." are
    resolved before the containment check, so traversal cannot escape.
    """
    roots = _allowed_file_write_roots()
    requested = str(raw_path or "").strip().strip('"')
    if "\x00" in requested:
        return None
    candidate = Path(requested).expanduser() if requested else roots[0]
    if not candidate.is_absolute():
        candidate = roots[0] / candidate
    try:
        candidate = candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        return None
    for root in roots:
        if candidate == root:
            return candidate if allow_root else None
        if root in candidate.parents:
            return candidate
    return None


def _display(path: Path) -> str:
    for root in _allowed_file_write_roots():
        if path == root or root in path.parents:
            rel = path.relative_to(root)
            return f"{root.name}/{rel.as_posix()}" if str(rel) != "." else root.name
    return path.name


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _log_error(event: str, exc: Exception) -> None:
    services.log_event(event, error=type(exc).__name__)


def _resolve_target(raw_path: str, *, must_exist: bool, allow_root: bool = False) -> tuple[Path | None, str]:
    path = resolve_in_roots(raw_path, allow_root=allow_root)
    if path is None:
        return None, "That path is outside the folders JARVIS is allowed to use."
    if is_protected_path(path):
        return None, "That file is protected (credentials or secrets) and cannot be used by JARVIS."
    if must_exist and not path.exists():
        return None, f"Not found: {_display(path)}"
    return path, ""


def _move_to_recycle_bin(path: Path) -> bool:
    """Send a file or folder to the Windows Recycle Bin. Returns True on success."""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    fo_delete = 0x0003
    flags = 0x0040 | 0x0010 | 0x0004 | 0x0400  # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
    op = SHFILEOPSTRUCTW(None, fo_delete, str(path) + "\0\0", None, flags, False, None, None)
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    return result == 0 and not op.fAnyOperationsAborted and not path.exists()


# ─────────────────────────────────────────
# Read-only
# ─────────────────────────────────────────
@tool
def listar_carpeta(carpeta: str = "") -> str:
    """List files and folders inside an authorized folder (Desktop or JARVIS_FILE_WRITE_ROOTS).
    Use for 'what is in my Desktop', 'show files in Projects', 'Desktop la enna files irukku'."""
    path, error = _resolve_target(carpeta, must_exist=True, allow_root=True)
    if path is None:
        return error
    if not path.is_dir():
        return f"Not a folder: {_display(path)}"
    try:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as exc:
        _log_error("file_list_error", exc)
        return "Could not read that folder."
    visible = [entry for entry in entries if not is_protected_path(entry)]
    if not visible:
        return f"{_display(path)} is empty."
    lines = []
    for entry in visible[:MAX_LIST_ENTRIES]:
        if entry.is_dir():
            lines.append(f"[DIR]  {entry.name}")
        else:
            try:
                size = _human_size(entry.stat().st_size)
            except OSError:
                size = "?"
            lines.append(f"[FILE] {entry.name} ({size})")
    more = len(visible) - MAX_LIST_ENTRIES
    suffix = f"\n... and {more} more" if more > 0 else ""
    return f"{_display(path)} ({len(visible)} items):\n" + "\n".join(lines) + suffix


@tool
def buscar_archivos(patron: str, carpeta: str = "") -> str:
    """Search authorized folders for files whose name matches a pattern or contains a word
    (e.g. '*.pdf', 'invoice', 'report*.docx'). Returns at most 50 matches."""
    query = str(patron or "").strip()
    if not query:
        return "Give me a file name or pattern to search for."
    path, error = _resolve_target(carpeta, must_exist=True, allow_root=True)
    if path is None:
        return error
    if not path.is_dir():
        return f"Not a folder: {_display(path)}"
    glob = query if any(ch in query for ch in "*?[") else f"*{query}*"
    glob = glob.lower()
    matches: list[Path] = []
    visited = 0
    deadline = time.monotonic() + MAX_SEARCH_SECONDS
    truncated = False
    for current, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if d.lower() not in _PROTECTED_DIRS and not d.startswith(".")]
        for name in files:
            visited += 1
            if fnmatch.fnmatch(name.lower(), glob):
                candidate = Path(current) / name
                if not is_protected_path(candidate):
                    matches.append(candidate)
            if len(matches) >= MAX_SEARCH_RESULTS or visited >= MAX_SEARCH_VISITED or time.monotonic() > deadline:
                truncated = True
                break
        if truncated:
            break
    if not matches:
        return f"No files matching '{query}' in {_display(path)}."
    lines = "\n".join(f"- {_display(match)}" for match in matches)
    note = "\n(Search stopped early; narrow the folder or pattern for more.)" if truncated else ""
    return f"Found {len(matches)} file(s):\n{lines}{note}"


@tool
def informacion_sistema() -> str:
    """Report CPU, memory, disk, battery and uptime for this computer."""
    lines = [f"OS: {platform.system()} {platform.release()} ({platform.machine()})"]
    try:
        lines.append(f"CPU: {psutil.cpu_percent(interval=0.3):.0f}% used, {psutil.cpu_count(logical=True)} logical cores")
        mem = psutil.virtual_memory()
        lines.append(f"Memory: {mem.percent:.0f}% used ({_human_size(mem.used)} of {_human_size(mem.total)})")
        disk = psutil.disk_usage(os.path.abspath(os.sep))
        lines.append(f"System disk: {disk.percent:.0f}% used ({_human_size(disk.free)} free)")
        uptime_h = (time.time() - psutil.boot_time()) / 3600
        lines.append(f"Uptime: {uptime_h:.1f} hours")
    except Exception as exc:
        _log_error("system_info_error", exc)
        lines.append("Some resource sensors are unavailable.")
    try:
        battery = psutil.sensors_battery()
    except Exception:
        battery = None
    if battery is None:
        lines.append("Battery: not available on this device.")
    else:
        state = "charging" if battery.power_plugged else "on battery"
        lines.append(f"Battery: {battery.percent:.0f}% ({state})")
    return "\n".join(lines)


@tool
def abrir_configuracion_windows(pagina: str) -> str:
    """Open a Windows Settings page. Valid pages: display, sound, bluetooth, wifi, network, battery,
    power, apps, default_apps, notifications, privacy, microphone, camera, windows_update, about,
    storage, language, speech, personalization."""
    key = str(pagina or "").strip().lower().replace(" ", "_").replace("-", "_")
    uri = WINDOWS_SETTINGS_PAGES.get(key)
    if uri is None:
        return "Unknown settings page. Options: " + ", ".join(sorted(WINDOWS_SETTINGS_PAGES))
    if not IS_WINDOWS:
        return "Windows Settings pages are only available on Windows."
    try:
        os.startfile(uri)  # type: ignore[attr-defined]  # noqa: S606
    except OSError as exc:
        _log_error("settings_open_error", exc)
        return "Windows could not open that Settings page."
    return f"Opened Windows Settings: {key}."


# ─────────────────────────────────────────
# Mutating (opt-in, policy-guarded)
# ─────────────────────────────────────────
@tool
def crear_carpeta(ruta: str) -> str:
    """Create a new folder inside an authorized folder."""
    if not file_tools_enabled():
        return _disabled_message()
    path, error = _resolve_target(ruta, must_exist=False)
    if path is None:
        return error
    if path.exists():
        return f"Already exists: {_display(path)}"
    try:
        path.mkdir(parents=True)
    except OSError as exc:
        _log_error("folder_create_error", exc)
        return "Could not create that folder."
    return f"Created folder {_display(path)}."


@tool
def copiar_archivo(origen: str, destino: str) -> str:
    """Copy a file or folder to another location inside the authorized folders. Never overwrites."""
    if not file_tools_enabled():
        return _disabled_message()
    src, error = _resolve_target(origen, must_exist=True)
    if src is None:
        return error
    dst, error = _resolve_target(destino, must_exist=False, allow_root=True)
    if dst is None:
        return error
    if dst.is_dir():
        dst = dst / src.name
        if is_protected_path(dst) or resolve_in_roots(str(dst)) is None:
            return "That destination is not allowed."
    if dst.exists():
        return f"Destination already exists: {_display(dst)}. Choose another name."
    try:
        if src.is_dir():
            if src in dst.parents:
                return "Cannot copy a folder into itself."
            shutil.copytree(src, dst, symlinks=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    except OSError as exc:
        _log_error("file_copy_error", exc)
        return "The copy failed."
    return f"Copied {_display(src)} to {_display(dst)}."


def _move(src_raw: str, dst_raw: str, *, rename_only: bool) -> str:
    src, error = _resolve_target(src_raw, must_exist=True)
    if src is None:
        return error
    if rename_only:
        new_name = str(dst_raw or "").strip()
        if not new_name or any(sep in new_name for sep in ("/", "\\")) or new_name in {".", ".."}:
            return "Give only the new name, without folders."
        dst_raw = str(src.parent / new_name)
    dst, error = _resolve_target(dst_raw, must_exist=False, allow_root=True)
    if dst is None:
        return error
    if dst.is_dir() and not rename_only:
        dst = dst / src.name
        if is_protected_path(dst) or resolve_in_roots(str(dst)) is None:
            return "That destination is not allowed."
    if dst.exists():
        return f"Destination already exists: {_display(dst)}. Nothing was changed."
    if src.is_dir() and src in dst.parents:
        return "Cannot move a folder into itself."
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    except OSError as exc:
        _log_error("file_move_error", exc)
        return "The move failed. Nothing was changed."
    verb = "Renamed" if rename_only else "Moved"
    return f"{verb} {_display(src)} to {_display(dst)}."


@tool
def mover_archivo(origen: str, destino: str) -> str:
    """Move a file or folder to another authorized folder. Never overwrites. Requires confirmation."""
    if not file_tools_enabled():
        return _disabled_message()
    return _move(origen, destino, rename_only=False)


@tool
def renombrar_archivo(ruta: str, nuevo_nombre: str) -> str:
    """Rename a file or folder in place (new name only, no folders). Requires confirmation."""
    if not file_tools_enabled():
        return _disabled_message()
    return _move(ruta, nuevo_nombre, rename_only=True)


@tool
def eliminar_archivo(ruta: str) -> str:
    """Delete a file or folder inside the authorized folders. On Windows it goes to the Recycle Bin.
    Always requires explicit user confirmation."""
    if not file_tools_enabled():
        return _disabled_message()
    path, error = _resolve_target(ruta, must_exist=True)
    if path is None:
        return error
    label = _display(path)
    try:
        if IS_WINDOWS:
            if _move_to_recycle_bin(path):
                return f"Moved {label} to the Recycle Bin."
            return f"Windows did not delete {label}."
        if path.is_dir():
            if any(path.iterdir()):
                return f"{label} is not empty. Delete its contents first."
            path.rmdir()
        else:
            path.unlink()
    except OSError as exc:
        _log_error("file_delete_error", exc)
        return f"Could not delete {label}."
    return f"Permanently deleted {label}."


def plan_organization(folder: Path) -> list[tuple[Path, Path]]:
    """Return (source, destination) moves that group loose files by type."""
    moves: list[tuple[Path, Path]] = []
    for entry in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_file() or is_protected_path(entry) or entry.suffix.lower() in {".lnk", ".url", ".ini"}:
            continue
        category = next((name for name, exts in ORGANIZE_CATEGORIES.items() if entry.suffix.lower() in exts), None)
        if category is None:
            continue
        target = folder / category / entry.name
        if not target.exists():
            moves.append((entry, target))
    return moves


@tool
def previsualizar_organizacion(carpeta: str = "") -> str:
    """Preview how loose files in a folder would be grouped into Images, Documents, Audio, Video,
    Archives, Installers and Code subfolders. Changes nothing."""
    path, error = _resolve_target(carpeta, must_exist=True, allow_root=True)
    if path is None:
        return error
    if not path.is_dir():
        return f"Not a folder: {_display(path)}"
    moves = plan_organization(path)
    if not moves:
        return f"Nothing to organize in {_display(path)}."
    lines = "\n".join(f"- {src.name} -> {dst.parent.name}/" for src, dst in moves[:MAX_LIST_ENTRIES])
    return f"Planned moves in {_display(path)} ({len(moves)} files):\n{lines}\nNothing has been moved yet."


@tool
def organizar_carpeta(carpeta: str = "") -> str:
    """Group loose files in a folder into type subfolders, exactly as previsualizar_organizacion shows.
    Requires confirmation. Never overwrites."""
    if not file_tools_enabled():
        return _disabled_message()
    path, error = _resolve_target(carpeta, must_exist=True, allow_root=True)
    if path is None:
        return error
    if not path.is_dir():
        return f"Not a folder: {_display(path)}"
    moved, failed = 0, 0
    for src, dst in plan_organization(path):
        try:
            dst.parent.mkdir(exist_ok=True)
            if dst.exists():
                failed += 1
                continue
            shutil.move(str(src), str(dst))
            moved += 1
        except OSError as exc:
            _log_error("file_organize_error", exc)
            failed += 1
    if not moved and not failed:
        return f"Nothing to organize in {_display(path)}."
    tail = f"; {failed} could not be moved" if failed else ""
    return f"Organized {_display(path)}: moved {moved} file(s){tail}."


# ─────────────────────────────────────────
# Read-only analysis: duplicates and large files
# ─────────────────────────────────────────
def _walk_files(folder: Path):
    """Yield (path, size) for regular files, skipping protected entries, within the search budget."""
    visited = 0
    deadline = time.monotonic() + MAX_SEARCH_SECONDS * 2
    for current, dirs, names in os.walk(folder, followlinks=False):
        dirs[:] = [d for d in dirs if d.lower() not in _PROTECTED_DIRS and not d.startswith(".")]
        for name in names:
            path = Path(current) / name
            visited += 1
            if visited > MAX_SEARCH_VISITED or time.monotonic() > deadline:
                return
            if is_protected_path(path) or path.is_symlink():
                continue
            try:
                yield path, path.stat().st_size
            except OSError:
                continue


def _sha256(path: Path) -> str | None:
    import hashlib

    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def find_duplicate_groups(folder: Path, min_size: int = 1) -> list[list[Path]]:
    """Groups of files with identical content (size match, then SHA-256)."""
    by_size: dict[int, list[Path]] = {}
    for path, size in _walk_files(folder):
        if size >= min_size:
            by_size.setdefault(size, []).append(path)
    groups: list[list[Path]] = []
    for paths in by_size.values():
        if len(paths) < 2:
            continue
        by_hash: dict[str, list[Path]] = {}
        for path in paths:
            digest = _sha256(path)
            if digest:
                by_hash.setdefault(digest, []).append(path)
        groups.extend(sorted(group) for group in by_hash.values() if len(group) > 1)
    return sorted(groups, key=lambda g: -g[0].stat().st_size if g[0].exists() else 0)


@tool
def buscar_duplicados(carpeta: str = "") -> str:
    """Find duplicate files (identical content by SHA-256) in an authorized folder. Read-only: never deletes."""
    path, error = _resolve_target(carpeta, must_exist=True, allow_root=True)
    if path is None:
        return error
    if not path.is_dir():
        return f"Not a folder: {_display(path)}"
    groups = find_duplicate_groups(path)
    if not groups:
        return f"No duplicate files in {_display(path)}."
    wasted = sum(g[0].stat().st_size * (len(g) - 1) for g in groups if g[0].exists())
    lines = []
    for group in groups[:20]:
        size = _human_size(group[0].stat().st_size) if group[0].exists() else "?"
        lines.append(f"- {len(group)} copies ({size} each): " + ", ".join(_display(p) for p in group[:5]))
    more = f"\n... and {len(groups) - 20} more groups" if len(groups) > 20 else ""
    return f"{len(groups)} duplicate group(s), {_human_size(wasted)} reclaimable. Nothing was deleted.\n" + "\n".join(lines) + more


@tool
def archivos_grandes(carpeta: str = "", cantidad: int = 10) -> str:
    """List the largest files in an authorized folder. Read-only."""
    path, error = _resolve_target(carpeta, must_exist=True, allow_root=True)
    if path is None:
        return error
    if not path.is_dir():
        return f"Not a folder: {_display(path)}"
    count = max(1, min(int(cantidad or 10), 50))
    largest = sorted(_walk_files(path), key=lambda item: item[1], reverse=True)[:count]
    if not largest:
        return f"No files in {_display(path)}."
    return f"Largest files in {_display(path)}:\n" + "\n".join(f"- {_human_size(s)}  {_display(p)}" for p, s in largest)


@tool
def informacion_archivo(ruta: str) -> str:
    """Details of one file or folder inside the allowed folders: type, size, created/modified dates,
    read-only flag, and whether it is a shortcut/link."""
    raw = Path(str(ruta or "").strip().strip('"')).expanduser()
    path, error = _resolve_target(ruta, must_exist=True, allow_root=True)
    if path is None:
        return error
    try:
        info = path.stat()
    except OSError as exc:
        _log_error("file_info_error", exc)
        return f"Windows did not allow reading details of {_display(path)}."
    kind = "folder" if path.is_dir() else (path.suffix.lower().lstrip(".") or "file") + " file"
    lines = [f"{_display(path)}: {kind}"]
    if path.is_file():
        lines.append(f"Size: {_human_size(info.st_size)}")
    lines.append(f"Modified: {datetime.fromtimestamp(info.st_mtime):%Y-%m-%d %H:%M}")
    lines.append(f"Created: {datetime.fromtimestamp(info.st_ctime):%Y-%m-%d %H:%M}")
    if not os.access(path, os.W_OK):
        lines.append("Read-only")
    if raw.is_absolute() and raw.is_symlink():
        lines.append("This is a link; details are for its target inside the allowed folders.")
    return "\n".join(lines)
