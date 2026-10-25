from __future__ import annotations

from pathlib import Path

import pytest
from core.security.tool_policy import get_tool_policy
from tools import _get_base_tools_impl, clipboard, files


@pytest.fixture
def root(monkeypatch, tmp_path: Path) -> Path:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("JARVIS_FILE_WRITE_ROOTS", str(allowed))
    return allowed


def test_duplicates_found_by_content_not_name(root: Path):
    (root / "a.txt").write_text("same content", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "copy.txt").write_text("same content", encoding="utf-8")
    (root / "b.txt").write_text("same lengthX", encoding="utf-8")  # same size, different bytes
    (root / ".env").write_text("same content", encoding="utf-8")  # protected, never reported
    result = files.buscar_duplicados.invoke({"carpeta": ""})
    assert "1 duplicate group" in result
    assert "a.txt" in result and "copy.txt" in result
    assert "b.txt" not in result and ".env" not in result
    assert "Nothing was deleted" in result
    assert (root / "a.txt").exists() and (root / "sub" / "copy.txt").exists()


def test_no_duplicates_and_outside_root(root: Path):
    (root / "only.txt").write_text("x", encoding="utf-8")
    assert "No duplicate" in files.buscar_duplicados.invoke({"carpeta": ""})
    assert "outside" in files.buscar_duplicados.invoke({"carpeta": "../"})


def test_largest_files_sorted(root: Path):
    for name, size in (("small.bin", 10), ("big.bin", 5000), ("mid.bin", 800)):
        (root / name).write_bytes(b"x" * size)
    lines = files.archivos_grandes.invoke({"carpeta": "", "cantidad": 2}).splitlines()
    assert "big.bin" in lines[1] and "mid.bin" in lines[2] and len(lines) == 3


def test_new_tools_registered_with_owner_only_policy(monkeypatch):
    monkeypatch.delenv("JARVIS_FILE_TOOLS_ENABLED", raising=False)
    names = {t.name for t in _get_base_tools_impl()}
    for name in ("buscar_duplicados", "archivos_grandes", "leer_portapapeles", "copiar_al_portapapeles"):
        assert name in names
        assert get_tool_policy(name).allowed_profiles == ("admin",)


def test_clipboard_read_withholds_secrets(monkeypatch):
    monkeypatch.setattr(clipboard, "IS_WINDOWS", True)
    monkeypatch.setattr(clipboard, "read_clipboard_text", lambda: "my password is hunter2")
    assert "won't read it out" in clipboard.leer_portapapeles.invoke({})
    monkeypatch.setattr(clipboard, "read_clipboard_text", lambda: "def main(): pass")
    assert "def main(): pass" in clipboard.leer_portapapeles.invoke({})
    monkeypatch.setattr(clipboard, "read_clipboard_text", lambda: None)
    assert "Could not open" in clipboard.leer_portapapeles.invoke({})


def test_clipboard_write_refuses_secrets(monkeypatch):
    written: list[str] = []
    monkeypatch.setattr(clipboard, "IS_WINDOWS", True)
    monkeypatch.setattr(clipboard, "write_clipboard_text", lambda text: written.append(text) or True)
    assert "Not copied" in clipboard.copiar_al_portapapeles.invoke({"texto": "token = ghp_abcdefghijklmnopqrstuvwxyz123456"})
    assert written == []
    assert "Copied 11 characters" in clipboard.copiar_al_portapapeles.invoke({"texto": "hello world"})
    assert written == ["hello world"]
