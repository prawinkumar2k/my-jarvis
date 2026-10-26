"""Windows Package Manager (winget) search and approval-gated installs.

Safety model:
- Commands are argument lists (never a shell string); queries and package ids
  are validated first, so text from webpages or model output cannot inject
  extra options or commands.
- Only the official ``winget`` source is used.
- ``instalar_programa`` requires explicit confirmation (tool policy); the
  confirmation question shows the exact id, name, publisher, version, source
  and license (``describe_for_confirmation``). The identity is re-checked
  right before installing.
- Installs are user scope only. A package that needs a machine-wide
  (administrator) install is reported, never elevated automatically.
- One install at a time; ``cancelar_instalacion`` stops winget, but an
  installer it already launched may finish on its own (reported as such).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
import unicodedata

from langchain_core.tools import tool

SOURCE = "winget"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,127}$")
_QUERY_MAX = 80
SEARCH_TIMEOUT = 60
INSTALL_TIMEOUT = 900
_COMMON = ["--source", SOURCE, "--accept-source-agreements", "--disable-interactivity"]

_install_lock = threading.Lock()
_active: dict = {}


class WingetError(RuntimeError):
    pass


def winget_path() -> str | None:
    return shutil.which("winget")


def _run(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    exe = winget_path()
    if not exe:
        raise WingetError("winget is not available on this PC (install 'App Installer' from Microsoft Store).")
    try:
        return subprocess.run(
            [exe, *args], capture_output=True, timeout=timeout, check=False, shell=False,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        raise WingetError("winget did not answer in time.") from None
    except OSError as exc:
        raise WingetError(f"winget could not start ({type(exc).__name__}).") from None


def winget_version() -> str | None:
    try:
        result = _run(["--version"], 15)
    except WingetError:
        return None
    return result.stdout.strip() or None


def valid_package_id(package_id: str) -> bool:
    return bool(_ID_RE.fullmatch(str(package_id or "").strip()))


def _clean_query(query: str) -> str:
    raw = str(query or "")
    text = " ".join(raw.split())
    if not text or len(text) > _QUERY_MAX or text.startswith("-") or any(unicodedata.category(c)[0] == "C" for c in raw):
        raise WingetError("Give a short program name to search for.")
    return text


# ── text output parsing ───────────────────────────────────────
def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _cut(line: str, start: int, end: int | None) -> str:
    """Slice by display columns (winget aligns columns by display width)."""
    out, col = [], 0
    for ch in line:
        w = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if col >= start and (end is None or col + w <= end):
            out.append(ch)
        col += w
    return "".join(out).strip()


def parse_table(output: str) -> list[dict[str, str]]:
    """Parse winget's fixed-width table (header line, dashed rule, rows)."""
    lines = [line.rstrip() for line in output.replace("\r", "\n").split("\n")]
    for i, line in enumerate(lines[1:], 1):
        if line and set(line) == {"-"}:
            header = lines[i - 1].lstrip("﻿")
            break
    else:
        return []
    names = header.split()
    starts = []
    col = 0
    for name in names:
        idx = header.index(name, col)
        starts.append(_width(header[:idx]))
        col = idx + len(name)
    rows = []
    for line in lines[i + 1:]:
        if not line.strip() or set(line.strip()) == {"-"}:
            continue
        values = [_cut(line, s, starts[k + 1] if k + 1 < len(starts) else None) for k, s in enumerate(starts)]
        rows.append(dict(zip(names, values, strict=True)))
    return rows


def parse_show(output: str) -> dict[str, str]:
    info: dict[str, str] = {}
    for line in output.splitlines():
        found = re.match(r"^Found (.+?) \[(.+?)\]\s*$", line.strip())
        if found:
            info["name"], info["id"] = found.group(1), found.group(2)
            continue
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            key = key.strip().lower()
            if key in {"version", "publisher", "license", "homepage", "publisher url"}:
                info[key.replace(" ", "_")] = value.strip()
        elif line.strip().lower().startswith("installer type:"):
            info["installer_type"] = line.split(":", 1)[1].strip()
    return info


# ── operations ────────────────────────────────────────────────
def search(query: str, limit: int = 10) -> list[dict[str, str]]:
    result = _run(["search", "--query", _clean_query(query), *_COMMON], SEARCH_TIMEOUT)
    rows = parse_table(result.stdout)
    if result.returncode != 0 and not rows:
        if "No package found" in result.stdout:
            return []
        raise WingetError(f"winget search failed (exit {result.returncode}).")
    return [
        {"name": r.get("Name", ""), "id": r.get("Id", ""), "version": r.get("Version", ""), "source": r.get("Source", SOURCE) or SOURCE}
        for r in rows[: max(1, min(limit, 25))]
        if valid_package_id(r.get("Id", ""))
    ]


def show(package_id: str) -> dict[str, str]:
    package_id = str(package_id or "").strip()
    if not valid_package_id(package_id):
        raise WingetError("That is not a valid winget package id.")
    result = _run(["show", "--id", package_id, "--exact", *_COMMON], SEARCH_TIMEOUT)
    info = parse_show(result.stdout)
    if result.returncode != 0 or info.get("id", "").lower() != package_id.lower():
        raise WingetError(f"No package with the exact id '{package_id}' in the {SOURCE} source.")
    info["source"] = SOURCE
    return info


def is_installed(package_id: str) -> bool:
    result = _run(["list", "--id", package_id, "--exact", "--accept-source-agreements", "--disable-interactivity"], SEARCH_TIMEOUT)
    return result.returncode == 0 and package_id.lower() in result.stdout.lower()


def describe(info: dict[str, str]) -> str:
    parts = [f"{info.get('name', '?')} [{info.get('id', '?')}]", f"version {info.get('version', '?')}",
             f"publisher {info.get('publisher', 'unknown')}", f"source {info.get('source', SOURCE)}"]
    if info.get("license"):
        parts.append(f"license {info['license']}")
    return ", ".join(parts)


def describe_for_confirmation(args: dict) -> str:
    """Shown in the confirmation question, before anything is installed."""
    try:
        info = show(str((args or {}).get("id_paquete", "")))
    except WingetError as exc:
        return f"Package check failed: {exc}"
    return (f"Install {describe(info)} for this Windows user? "
            "Approving also accepts that package's license.")


def install(package_id: str) -> str:
    package_id = str(package_id or "").strip()
    if not _install_lock.acquire(blocking=False):
        return f"An install is already running ({_active.get('id', 'unknown')}). Wait for it or cancel it."
    try:
        info = show(package_id)  # re-verify identity right before installing
        if is_installed(package_id):
            return f"{describe(info)} is already installed. Nothing to do."
        exe = winget_path()
        args = [exe, "install", "--id", info["id"], "--exact", "--scope", "user",
                "--accept-package-agreements", *_COMMON]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                encoding="utf-8", errors="replace", shell=False)
        _active.update(id=info["id"], process=proc, cancelled=False)
        try:
            output, _ = proc.communicate(timeout=INSTALL_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            return f"Install of {info['id']} took over {INSTALL_TIMEOUT // 60} minutes and was stopped. Check whether it finished."
        if _active.get("cancelled"):
            return f"Install of {info['id']} was cancelled. An installer winget had already started may still finish; check Installed apps."
        code = proc.returncode
        if code != 0:
            if "No applicable installer" in output or "scope" in output.lower():
                return (f"{info['id']} has no per-user installer; it needs a machine-wide (administrator) install, "
                        "which I did not do. Approve that separately if you want it.")
            return f"winget install of {info['id']} failed (exit code {code})."
        verified = is_installed(info["id"])
        return f"Installed {describe(info)} (exit code 0). " + (
            "Verified in winget's installed list." if verified else "winget reported success, but it is not in the installed list yet.")
    except WingetError as exc:
        return str(exc)
    finally:
        _active.clear()
        _install_lock.release()


def cancel_install() -> str:
    proc = _active.get("process")
    if not proc or proc.poll() is not None:
        return "No install is running."
    _active["cancelled"] = True
    proc.terminate()
    return f"Stopping the install of {_active.get('id')}. An installer that already started may not stop."


# ── tools ─────────────────────────────────────────────────────
@tool
def buscar_programa(nombre: str) -> str:
    """Search the official winget catalog for a program (e.g. 'vlc', '7zip'). Returns real ids and versions."""
    try:
        results = search(nombre)
    except WingetError as exc:
        return str(exc)
    if not results:
        return f"No winget packages match '{nombre}'."
    lines = [f"- {r['name']} [{r['id']}] {r['version']} ({r['source']})" for r in results]
    return f"winget results for '{nombre}':\n" + "\n".join(lines)


@tool
def ver_programa(id_paquete: str) -> str:
    """Show the exact identity of a winget package (name, publisher, version, source, license) before installing."""
    try:
        return describe(show(id_paquete))
    except WingetError as exc:
        return str(exc)


@tool
def instalar_programa(id_paquete: str) -> str:
    """Install a program with winget by its exact package id (find it with buscar_programa first).
    Always asks the user to approve first; installs for the current user only."""
    return install(id_paquete)


@tool
def cancelar_instalacion() -> str:
    """Stop the winget install that is running, if any."""
    return cancel_install()
