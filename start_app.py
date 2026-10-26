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
            backend_proc = subprocess.Popen(
                [sys.executable, backend_script],
                cwd=root_dir,
                stdout=log_stream,
                stderr=subprocess.STDOUT if log_stream is not None else None,
            )

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
            if backend_proc:
                backend_proc.terminate()
            cleanup_temporary_storage()
            os._exit(0)

        window.events.closed += on_closed

        # 4. Start desktop app with persistent Edge Chromium storage.
        print("[SYSTEM] Opening user interface...")
        # Let the desktop window speak without a click so it can boot hands-free.
        os.environ.setdefault(
            "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
            "--autoplay-policy=no-user-gesture-required",
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
    if not acquire_single_instance():
        print("[SYSTEM] JARVIS is already running; not starting a second instance.")
        sys.exit(0)
    try:
        start_app()
    except KeyboardInterrupt:
        sys.exit(0)
