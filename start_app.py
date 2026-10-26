from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _skip_venv_reexec() -> bool:
    return os.getenv("JARVIS_SKIP_VENV_REEXEC", "").strip().lower() in _TRUE_VALUES


def _project_venv_python(
    root: Path = ROOT_DIR, *, platform: str | None = None
) -> Path | None:
    active_platform = platform or sys.platform
    relative_path = (
        Path("venv/Scripts/python.exe")
        if active_platform == "win32"
        else Path("venv/bin/python")
    )
    candidate = Path(root) / relative_path
    return candidate if candidate.is_file() else None


def _relaunch_in_project_venv(root: Path = ROOT_DIR) -> bool:
    if _skip_venv_reexec():
        return False

    candidate = _project_venv_python(root)
    if candidate is None:
        return False

    current_python = os.path.normcase(os.path.realpath(sys.executable))
    project_python = os.path.normcase(os.path.realpath(candidate))
    if current_python == project_python:
        return False
    # pythonw.exe from the same venv is already correct; switching to python.exe
    # would open a console window and show the app under the Python icon.
    windowless = os.path.normcase(os.path.realpath(candidate.with_name("pythonw.exe")))
    if current_python == windowless:
        return False

    script_path = Path(root) / "start_app.py"
    os.execv(
        str(candidate),
        [str(candidate), str(script_path), *sys.argv[1:]],
    )
    return True


def _project_environment_error(root: Path = ROOT_DIR) -> str | None:
    if _skip_venv_reexec():
        return None
    if _project_venv_python(root) is not None:
        return None
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        return None
    return (
        "Project virtual environment not found. Run .\\setup.ps1 on Windows "
        "or ./setup.sh on macOS/Linux before starting JARVIS."
    )


if __name__ == "__main__":
    environment_error = _project_environment_error()
    if environment_error:
        print(environment_error, file=sys.stderr)
        raise SystemExit(1)
    _relaunch_in_project_venv()


try:
    import requests
    import webview
except ModuleNotFoundError as exc:
    dependency = exc.name or "unknown"
    raise SystemExit(
        f"Missing runtime dependency '{dependency}'. Run .\\setup.ps1 on Windows "
        "or ./setup.sh on macOS/Linux."
    ) from exc


BACKEND_DIR = str(ROOT_DIR / "src" / "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


_INSTANCE_MUTEX_NAME = r"Local\JARVIS-Desktop-Assistant"
_instance_mutex = None


def acquire_single_instance() -> bool:
    """Hold a per-user named mutex; False when another JARVIS window owns it."""
    global _instance_mutex
    if sys.platform != "win32":
        return True
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, _INSTANCE_MUTEX_NAME)
    if not handle:
        return True  # Cannot tell; do not block startup.
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return False
    _instance_mutex = handle
    return True


def configure_startup_log():
    """Send output to JARVIS_STARTUP_LOG when launched without a console."""
    log_path = os.getenv("JARVIS_STARTUP_LOG", "").strip()
    if not log_path and sys.stdout is not None:
        return None
    if not log_path:
        base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        log_path = str(Path(base) / "Jarvis" / "logs" / "startup.log")
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        stream = open(log_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    except OSError:
        return None
    sys.stdout = stream
    sys.stderr = stream
    return stream


APP_USER_MODEL_ID = "Prawin.JARVIS.Assistant"
ICON_PATH = ROOT_DIR / "media" / "jarvis.ico"


def set_windows_app_identity() -> None:
    """Own taskbar entry and icon instead of being grouped under python.exe."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def apply_window_icon(hwnd: int) -> bool:
    """Set the JARVIS icon on a native window (title bar, taskbar, Alt+Tab)."""
    if sys.platform != "win32" or not hwnd or not ICON_PATH.is_file():
        return False
    import ctypes

    user32 = ctypes.windll.user32
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    image_icon, load_from_file, wm_seticon = 1, 0x0010, 0x0080
    small = user32.LoadImageW(None, str(ICON_PATH), image_icon, 16, 16, load_from_file)
    big = user32.LoadImageW(None, str(ICON_PATH), image_icon, 48, 48, load_from_file)
    if small:
        user32.SendMessageW(hwnd, wm_seticon, 0, small)
    if big:
        user32.SendMessageW(hwnd, wm_seticon, 1, big)
    return bool(small or big)


def start_backend_watchdog(holder, spawn, *, interval=5.0, max_restarts=3, window_s=600.0):
    """Restart the backend if it exits unexpectedly (bounded to avoid crash loops).

    holder: one-item list with the current Popen; holder is set to [None] on
    shutdown so the watchdog stops instead of restarting a deliberate exit.
    """
    import threading

    restarts: list[float] = []

    def loop():
        while True:
            time.sleep(interval)
            proc = holder[0]
            if proc is None:
                return
            code = proc.poll()
            if code is None:
                continue
            now = time.monotonic()
            restarts[:] = [r for r in restarts if now - r < window_s]
            if len(restarts) >= max_restarts:
                print(f"[WATCHDOG] Backend keeps exiting (code {code}); not restarting again.")
                return
            restarts.append(now)
            print(f"[WATCHDOG] Backend exited (code {code}); restarting...")
            holder[0] = spawn()

    thread = threading.Thread(target=loop, name="jarvis-watchdog", daemon=True)
    thread.start()
    return thread


def is_backend_running(url):
    try:
        response = requests.get(f"{url}/api/status", timeout=1)
        return response.status_code == 200
    except requests.RequestException:
        return False


def start_app():
    # 1. Route configuration
    root_dir = os.path.dirname(os.path.abspath(__file__))
    backend_script = os.path.join(root_dir, "src", "backend", "jarvis_backend.py")
    cleanup_dir = None

    def cleanup_temporary_storage():
        nonlocal cleanup_dir
        if not cleanup_dir:
            return
        temporary_dir = cleanup_dir
        cleanup_dir = None
        shutil.rmtree(temporary_dir, ignore_errors=True)

    try:
        try:
            from core.desktop_session import load_desktop_session

            desktop_session = load_desktop_session(port=5002)
            url = desktop_session.origin
            webview_storage_dir = desktop_session.webview_storage_dir
            cleanup_dir = getattr(desktop_session, "cleanup_dir", None)
        except Exception:
            print(
                "[SYSTEM] Persistent desktop session unavailable; "
                "using temporary storage."
            )
            url = "http://localhost:5002"
            cleanup_dir = tempfile.mkdtemp(prefix="jarvis-desktop-emergency-")
            try:
                os.chmod(cleanup_dir, 0o700)
            except OSError:
                pass
            webview_storage_dir = cleanup_dir

        print("--- Starting J.A.R.V.I.S. Desktop Engine ---")

        # 2. Start backend if needed
        backend_proc = None
        if not is_backend_running(url):
            print("[SYSTEM] Starting backend server...")
            # Inherit stdout/stderr so startup diagnostics remain visible.
            log_stream = sys.stdout if getattr(sys.stdout, "fileno", None) else None
            try:
                if log_stream is not None:
                    log_stream.fileno()
            except (OSError, ValueError):
                log_stream = None
            def spawn_backend():
                return subprocess.Popen(
                    [sys.executable, backend_script],
                    cwd=root_dir,
                    stdout=log_stream,
                    stderr=subprocess.STDOUT if log_stream is not None else None,
                )

            backend_proc = spawn_backend()

            # Wait up to 90s because local ML models can be heavy.
            attempts = 0
            while attempts < 90:
                if is_backend_running(url):
                    print("[SYSTEM] Server ready.")
                    break
                time.sleep(1)
                attempts += 1
                if attempts % 10 == 0:
                    print(f"[SYSTEM] Waiting for core ({attempts}s)...")
            else:
                print("[ERROR] Core did not respond after 90s. Check terminal.")
                if backend_proc:
                    backend_proc.terminate()
                return
        else:
            print("[SYSTEM] Server is already running.")

        backend_holder = [backend_proc]
        if backend_proc is not None:
            start_backend_watchdog(backend_holder, spawn_backend)

        # 3. Create desktop window
        window = webview.create_window(
            'J.A.R.V.I.S. - Just A Rather Very Intelligent System',
            url,
            width=1366,
            height=768,
            min_size=(1024, 768),
            background_color='#000000',
            text_select=False,
            confirm_close=True
        )

        def on_closed():
            print("[SYSTEM] Closing application...")
            proc, backend_holder[0] = backend_holder[0], None  # stop the watchdog first
            if proc:
                proc.terminate()
            cleanup_temporary_storage()
            os._exit(0)

        window.events.closed += on_closed

        def on_shown():
            hwnd = 0
            try:
                hwnd = int(window.native.Handle.ToInt64())
            except Exception:
                import ctypes

                hwnd = ctypes.windll.user32.FindWindowW(None, window.title) if sys.platform == "win32" else 0
            apply_window_icon(hwnd)

        if hasattr(window.events, "shown"):
            window.events.shown += on_shown

        # 4. Start desktop app with persistent Edge Chromium storage.
        print("[SYSTEM] Opening user interface...")
        # Let the desktop window speak without a click so it can boot hands-free,
        # and skip the disk cache: the UI is served locally, and a stale cached
        # module after an update breaks the app.
        os.environ.setdefault(
            "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
            "--autoplay-policy=no-user-gesture-required --disk-cache-size=1",
        )
        gui_engine = 'edgechromium' if sys.platform == 'win32' else None

        try:
            webview.start(
                gui=gui_engine,
                debug=False,
                private_mode=False,
                storage_path=webview_storage_dir,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/DesktopJarvis/1.0"
            )
        except Exception as exc:
            if "0x800700AA" in str(exc) or "recurso solicitado" in str(exc) or "EBWebView" in str(exc):
                print("[SYSTEM] Default webview storage locked; using fresh isolated storage...")
                fallback_storage = tempfile.mkdtemp(prefix="jarvis-webview-isolated-")
                webview.start(
                    gui=gui_engine,
                    debug=False,
                    private_mode=False,
                    storage_path=fallback_storage,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/DesktopJarvis/1.0"
                )
            else:
                raise
    finally:
        cleanup_temporary_storage()


if __name__ == "__main__":
    configure_startup_log()
    set_windows_app_identity()
    if not acquire_single_instance():
        print("[SYSTEM] JARVIS is already running; not starting a second instance.")
        sys.exit(0)
    try:
        start_app()
    except KeyboardInterrupt:
        sys.exit(0)
