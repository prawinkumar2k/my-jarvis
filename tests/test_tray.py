"""System-tray helper: optional, never fatal, never keeps JARVIS alive on its own."""

from __future__ import annotations

from pathlib import Path

from core import tray

ROOT = Path(__file__).resolve().parents[1]


def test_menu_has_open_and_quit_and_runs_the_given_actions():
    calls = []
    items = tray.build_menu_items(lambda: calls.append("open"), lambda: calls.append("quit"))
    assert [label for label, _ in items] == ["Open JARVIS", "Quit JARVIS"]
    for _, action in items:
        action()
    assert calls == ["open", "quit"]


def test_tray_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("JARVIS_TRAY_ENABLED", "false")
    assert tray.start_tray(ROOT, lambda: None, lambda: None) is None


def test_missing_pystray_is_not_an_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake(name, *args, **kwargs):
        if name == "pystray":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setenv("JARVIS_TRAY_ENABLED", "true")
    monkeypatch.setattr(builtins, "__import__", fake)
    assert tray.start_tray(ROOT, lambda: None, lambda: None) is None


def test_icon_image_uses_the_project_icon_or_a_fallback():
    image = tray._icon_image(ROOT)
    assert image.size[0] > 0 and image.mode == "RGBA"
    assert tray._icon_image(ROOT / "nowhere").size == (64, 64)


def test_stop_tray_ignores_none_and_failures():
    tray.stop_tray(None)

    class Broken:
        def stop(self):
            raise RuntimeError("x")

    tray.stop_tray(Broken())
