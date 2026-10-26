"""Windows toast notifications (Action Center) for reminders, timers and alarms.

Uses the built-in Windows Runtime toast API through Windows PowerShell, so no
extra package is needed. The message is passed through an environment
variable and XML-escaped inside PowerShell, never interpolated into the
script, so reminder text cannot inject commands or markup.
"""

from __future__ import annotations

import os
import subprocess
import sys

# PowerShell's registered app id lets a desktop app raise toasts without a
# separate Start Menu registration.
_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

_SCRIPT = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$title = [Security.SecurityElement]::Escape($env:JARVIS_TOAST_TITLE)
$body = [Security.SecurityElement]::Escape($env:JARVIS_TOAST_TEXT)
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$title</text><text>$body</text></binding></visual><audio src='ms-winsoundevent:Notification.Reminder'/></toast>")
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:JARVIS_TOAST_APP).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""


def show_toast(title: str, text: str, timeout: float = 15.0) -> bool:
    """Show a Windows notification. Returns True when Windows accepted it."""
    if sys.platform != "win32":
        return False
    env = {
        **os.environ,
        "JARVIS_TOAST_TITLE": str(title or "JARVIS")[:80],
        "JARVIS_TOAST_TEXT": str(text or "")[:300],
        "JARVIS_TOAST_APP": _APP_ID,
    }
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _SCRIPT],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0
