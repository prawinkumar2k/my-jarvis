"""Live system diagnostics: real readings only.

Every value comes from the machine at call time. A reading that cannot be
taken is reported as ``None`` with a reason ("unavailable"), never as 0, so
the UI and the assistant can tell "0%" from "unknown".
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request

import psutil

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(args: list[str], timeout: float = 8.0) -> str | None:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False,
                                shell=False, creationflags=NO_WINDOW, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _powershell_json(script: str):
    out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", f"{script} | ConvertTo-Json -Compress"], 15)
    if not out or not out.strip():
        return None
    try:
        data = json.loads(out)
    except ValueError:
        return None
    return data if isinstance(data, list) else [data]


def cpu_memory() -> dict:
    mem = psutil.virtual_memory()
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "cpu_logical_cores": psutil.cpu_count(logical=True),
        "memory_percent": mem.percent,
        "memory_used_gb": round(mem.used / 1e9, 1),
        "memory_total_gb": round(mem.total / 1e9, 1),
        "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 1),
    }


def disks() -> list[dict]:
    drives = []
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in part.opts or not part.fstype:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue  # unready drive (card reader, disconnected network share)
        drives.append({"drive": part.mountpoint, "percent": usage.percent,
                       "free_gb": round(usage.free / 1e9, 1), "total_gb": round(usage.total / 1e9, 1)})
    return drives


def _storage_disks_wmi() -> list[dict] | None:
    """MSFT_PhysicalDisk in-process through WMI (no PowerShell start-up cost)."""
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return None
    pythoncom.CoInitialize()
    try:
        return _query_storage(win32com.client)
    except Exception:
        return None
    finally:
        pythoncom.CoUninitialize()


def _query_storage(client) -> list[dict]:
    # Separate function: every COM object is released when it returns, before CoUninitialize.
    service = client.GetObject("winmgmts:root/Microsoft/Windows/Storage")
    query = "SELECT FriendlyName, MediaType, HealthStatus FROM MSFT_PhysicalDisk"
    return [{"FriendlyName": str(d.FriendlyName), "MediaType": int(d.MediaType), "HealthStatus": int(d.HealthStatus)}
            for d in service.ExecQuery(query)]


def disk_health() -> list[dict] | None:
    """Windows Storage health (no administrator rights needed). None when unavailable."""
    if os.name != "nt":
        return None
    rows = _storage_disks_wmi()
    if rows is None:
        # Slower fallback when pywin32 is missing (Get-PhysicalDisk itself took ~40 s on the dev laptop).
        rows = _powershell_json(
            "Get-CimInstance -Namespace root/Microsoft/Windows/Storage -ClassName MSFT_PhysicalDisk"
            " | Select-Object FriendlyName,MediaType,HealthStatus"
        )
    if rows is None:
        return None
    return [{"name": r.get("FriendlyName"), "type": _MEDIA.get(r.get("MediaType"), "unknown"),
             "health": _HEALTH.get(r.get("HealthStatus"), "unknown")} for r in rows]


_HEALTH = {0: "Healthy", 1: "Warning", 2: "Unhealthy", 5: "Unknown"}
_MEDIA = {0: "unspecified", 3: "HDD", 4: "SSD", 5: "SCM"}


def battery() -> dict | None:
    try:
        info = psutil.sensors_battery()
    except Exception:
        return None
    if info is None:
        return None
    minutes = None if info.secsleft in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) or info.secsleft < 0 else info.secsleft // 60
    return {"percent": round(info.percent), "plugged_in": bool(info.power_plugged), "minutes_left": minutes}


def _nvidia_smi() -> str | None:
    found = shutil.which("nvidia-smi")
    fallback = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe")
    return found or (fallback if os.path.isfile(fallback) else None)


def _number(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None  # nvidia-smi prints "[N/A]" or "[Not Supported]"


def gpus() -> list[dict]:
    """Every display adapter; utilization only where the driver reports it (NVIDIA via nvidia-smi)."""
    result: list[dict] = []
    smi = _nvidia_smi()
    if smi:
        out = _run([smi, "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits"], 20)
        for line in (out or "").strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 5:
                result.append({"name": parts[0], "utilization_percent": _number(parts[1]), "memory_used_mb": _number(parts[2]),
                               "memory_total_mb": _number(parts[3]), "temperature_c": _number(parts[4]), "source": "nvidia-smi"})
    known = {g["name"] for g in result}
    for name in _display_adapters():
        if name not in known:
            known.add(name)
            result.append({"name": name, "utilization_percent": None, "source": "windows (no utilization reading)"})
    return result


def _display_adapters() -> list[str]:
    """Adapter names from EnumDisplayDevicesW (instant; no PowerShell or WMI)."""
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes

    class DISPLAY_DEVICEW(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32), ("DeviceString", wintypes.WCHAR * 128),
                    ("StateFlags", wintypes.DWORD), ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]

    names: list[str] = []
    for index in range(16):
        dev = DISPLAY_DEVICEW()
        dev.cb = ctypes.sizeof(dev)
        if not ctypes.windll.user32.EnumDisplayDevicesW(None, index, ctypes.byref(dev), 0):
            break
        name = dev.DeviceString.strip()
        if name and name not in names:
            names.append(name)
    return names


def top_processes(limit: int = 5) -> list[dict]:
    procs = []
    for proc in psutil.process_iter(["name", "memory_info"]):
        try:
            procs.append({"name": proc.info["name"], "memory_mb": round(proc.info["memory_info"].rss / 1e6)})
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError, AttributeError):
            continue
    return sorted(procs, key=lambda p: p["memory_mb"], reverse=True)[:limit]


def tool_status() -> dict:
    from utils.audio_conversion import ffmpeg_executable

    status: dict = {"ffmpeg": bool(ffmpeg_executable())}
    try:
        from tools.browser import browser_automation_status

        status["browser_automation"] = browser_automation_status()
    except Exception:
        status["browser_automation"] = None
    winget = shutil.which("winget")
    status["winget"] = (_run([winget, "--version"], 10) or "").strip() or None if winget else None
    base = (os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
    if not base.startswith(("http://127.0.0.1", "http://localhost")):
        status["ollama"] = "remote (not probed)"
    else:
        try:
            with urllib.request.urlopen(f"{base}/api/version", timeout=2) as resp:  # noqa: S310 - loopback only
                status["ollama"] = json.loads(resp.read().decode()).get("version", "running")
        except Exception:
            status["ollama"] = None
    return status


def collect() -> dict:
    """All sections in parallel, so one slow reading (a busy PC) does not delay the others."""
    from concurrent.futures import ThreadPoolExecutor

    sections = {"cpu_memory": cpu_memory, "disks": disks, "disk_health": disk_health, "battery": battery,
                "gpus": gpus, "top_processes": top_processes, "tools": tool_status}
    report: dict = {}
    with ThreadPoolExecutor(max_workers=len(sections)) as pool:
        futures = {key: pool.submit(fn) for key, fn in sections.items()}
        for key, future in futures.items():
            try:
                report[key] = future.result()
            except Exception as exc:
                report[key] = None
                report.setdefault("unavailable", {})[key] = type(exc).__name__
    return report


def summarize(report: dict) -> str:
    lines = []
    cm = report.get("cpu_memory")
    if cm:
        lines.append(f"CPU {cm['cpu_percent']:.0f}% ({cm['cpu_logical_cores']} threads), memory {cm['memory_percent']:.0f}% "
                     f"({cm['memory_used_gb']} of {cm['memory_total_gb']} GB), up {cm['uptime_hours']} h")
    for d in report.get("disks") or []:
        lines.append(f"Drive {d['drive']} {d['percent']:.0f}% used, {d['free_gb']} GB free")
    health = report.get("disk_health")
    lines.append("Disk health: " + (", ".join(f"{h['name']} {h['health']}" for h in health) if health else "unavailable"))
    bat = report.get("battery")
    if bat is None:
        lines.append("Battery: none or unavailable")
    else:
        left = f", about {bat['minutes_left']} min left" if bat["minutes_left"] else ""
        lines.append(f"Battery {bat['percent']}% ({'plugged in' if bat['plugged_in'] else 'on battery'}{left})")
    for g in report.get("gpus") or []:
        util = "utilization unavailable" if g.get("utilization_percent") is None else f"{g['utilization_percent']:.0f}% busy"
        extra = ""
        if g.get("memory_total_mb"):
            extra = f", VRAM {g['memory_used_mb']:.0f}/{g['memory_total_mb']:.0f} MB"
        lines.append(f"GPU {g['name']}: {util}{extra}")
    procs = report.get("top_processes") or []
    if procs:
        lines.append("Most memory: " + ", ".join(f"{p['name']} {p['memory_mb']} MB" for p in procs))
    tools = report.get("tools") or {}
    lines.append(f"Tools: winget {tools.get('winget') or 'missing'}, FFmpeg {'ok' if tools.get('ffmpeg') else 'missing'}, "
                 f"Ollama {tools.get('ollama') or 'not running'}")
    web = tools.get("browser_automation") or {}
    if web:
        engine = "Playwright Chromium" if web.get("bundled_chromium") else ", ".join(web.get("installed_browsers") or []) or "none"
        lines.append(f"Browser automation: {'ready' if web.get('ready') else 'not available'} ({engine})")
    return "\n".join(lines)
