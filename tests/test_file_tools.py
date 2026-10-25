from __future__ import annotations

from pathlib import Path

import pytest
from core.security.tool_policy import evaluate_tool_policy, get_tool_policy
from tools import _get_base_tools_impl, files

MUTATING = ("crear_carpeta", "copiar_archivo", "mover_archivo", "renombrar_archivo", "eliminar_archivo", "organizar_carpeta")


@pytest.fixture
def root(monkeypatch, tmp_path: Path) -> Path:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("JARVIS_FILE_WRITE_ROOTS", str(allowed))
    monkeypatch.setenv("JARVIS_FILE_TOOLS_ENABLED", "true")
    monkeypatch.delenv("JARVIS_SYSTEM_TOOLS_ENABLED", raising=False)
    # Deletion on Windows goes through the Recycle Bin; keep tests hermetic.
    monkeypatch.setattr(files, "IS_WINDOWS", False)
    return allowed


def _names() -> set[str]:
    return {str(getattr(tool, "name", "")) for tool in _get_base_tools_impl()}


# --- Catalog and policy ----------------------------------------------------


def test_mutating_file_tools_are_opt_in(monkeypatch):
    monkeypatch.delenv("JARVIS_FILE_TOOLS_ENABLED", raising=False)
    monkeypatch.delenv("JARVIS_SYSTEM_TOOLS_ENABLED", raising=False)
    names = _names()
    assert {"listar_carpeta", "buscar_archivos", "informacion_sistema", "previsualizar_organizacion"} <= names
    assert not set(MUTATING) & names
    monkeypatch.setenv("JARVIS_FILE_TOOLS_ENABLED", "true")
    assert set(MUTATING) <= _names()
    # Enabling file tools must not enable terminal execution.
    assert "ejecutar_comando_terminal" not in _names()


@pytest.mark.parametrize("name", ["mover_archivo", "renombrar_archivo", "eliminar_archivo", "organizar_carpeta"])
def test_destructive_file_tools_require_confirmation(name):
    policy = get_tool_policy(name)
    assert policy.risk_level == "critical"
    assert policy.requires_confirmation is True
    assert policy.audit_log is True
    decision = evaluate_tool_policy(name, profile_id="admin", authorized=True, confirmed=False)
    assert decision.allowed is False
    assert evaluate_tool_policy(name, profile_id="admin", authorized=True, confirmed=True).allowed is True


def test_disabled_tools_refuse_even_when_called_directly(monkeypatch, root: Path):
    monkeypatch.delenv("JARVIS_FILE_TOOLS_ENABLED", raising=False)
    (root / "a.txt").write_text("x", encoding="utf-8")
    result = files.eliminar_archivo.invoke({"ruta": "a.txt"})
    assert "disabled" in result
    assert (root / "a.txt").exists()


# --- Path confinement ------------------------------------------------------


@pytest.mark.parametrize("raw", ["../outside.txt", "..\\..\\Windows\\system.ini", "sub/../../escape"])
def test_traversal_outside_roots_is_rejected(root: Path, raw):
    assert files.resolve_in_roots(raw) is None


def test_absolute_path_outside_roots_is_rejected(root: Path, tmp_path: Path):
    outside = tmp_path / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    result = files.copiar_archivo.invoke({"origen": str(outside), "destino": "copy.txt"})
    assert "outside" in result
    assert not (root / "copy.txt").exists()


def test_credentials_are_hidden_and_untouchable(root: Path):
    (root / ".env").write_text("GEMINI_API_KEY=x", encoding="utf-8")
    (root / "id_rsa").write_text("key", encoding="utf-8")
    (root / ".env.example").write_text("GEMINI_API_KEY=", encoding="utf-8")
    listing = files.listar_carpeta.invoke({"carpeta": ""})
    assert ".env.example" in listing
    assert "id_rsa" not in listing
    assert "[FILE] .env " not in listing
    assert "protected" in files.eliminar_archivo.invoke({"ruta": ".env"})
    assert "protected" in files.copiar_archivo.invoke({"origen": "id_rsa", "destino": "k.txt"})
    assert (root / ".env").exists()


# --- Real operations in a temporary root -----------------------------------


def test_create_list_search_copy_rename_move_delete(root: Path):
    assert "Created" in files.crear_carpeta.invoke({"ruta": "Projects/demo"})
    assert (root / "Projects" / "demo").is_dir()

    (root / "notes.txt").write_text("hello", encoding="utf-8")
    assert "notes.txt" in files.listar_carpeta.invoke({"carpeta": ""})
    assert "notes.txt" in files.buscar_archivos.invoke({"patron": "*.txt"})
    assert "notes" in files.buscar_archivos.invoke({"patron": "note"})

    assert "Copied" in files.copiar_archivo.invoke({"origen": "notes.txt", "destino": "Projects"})
    assert (root / "Projects" / "notes.txt").read_text(encoding="utf-8") == "hello"
    assert "already exists" in files.copiar_archivo.invoke({"origen": "notes.txt", "destino": "Projects"})

    assert "Renamed" in files.renombrar_archivo.invoke({"ruta": "notes.txt", "nuevo_nombre": "todo.txt"})
    assert (root / "todo.txt").exists() and not (root / "notes.txt").exists()
    assert "only the new name" in files.renombrar_archivo.invoke({"ruta": "todo.txt", "nuevo_nombre": "../x.txt"})

    assert "Moved" in files.mover_archivo.invoke({"origen": "todo.txt", "destino": "Projects/demo"})
    assert (root / "Projects" / "demo" / "todo.txt").exists()

    assert "deleted" in files.eliminar_archivo.invoke({"ruta": "Projects/demo/todo.txt"})
    assert not (root / "Projects" / "demo" / "todo.txt").exists()
    assert "Not found" in files.eliminar_archivo.invoke({"ruta": "Projects/demo/todo.txt"})


def test_move_never_overwrites(root: Path):
    (root / "a.txt").write_text("a", encoding="utf-8")
    (root / "b.txt").write_text("b", encoding="utf-8")
    result = files.mover_archivo.invoke({"origen": "a.txt", "destino": "b.txt"})
    assert "already exists" in result
    assert (root / "b.txt").read_text(encoding="utf-8") == "b"


def test_cannot_delete_the_root_itself(root: Path):
    result = files.eliminar_archivo.invoke({"ruta": str(root)})
    assert "outside" in result
    assert root.exists()


def test_organize_preview_changes_nothing_and_apply_matches_preview(root: Path):
    for name in ("photo.jpg", "report.pdf", "song.mp3", "setup.exe", "unknown.xyz"):
        (root / name).write_text("x", encoding="utf-8")
    preview = files.previsualizar_organizacion.invoke({"carpeta": ""})
    assert "photo.jpg -> Images/" in preview
    assert "report.pdf -> Documents/" in preview
    assert "unknown.xyz" not in preview
    assert (root / "photo.jpg").exists()

    result = files.organizar_carpeta.invoke({"carpeta": ""})
    assert "moved 4 file(s)" in result
    assert (root / "Images" / "photo.jpg").exists()
    assert (root / "Installers" / "setup.exe").exists()
    assert (root / "unknown.xyz").exists()


# --- System information ------------------------------------------------------


def test_system_info_reports_resources_or_unavailability():
    report = files.informacion_sistema.invoke({})
    assert "CPU:" in report or "unavailable" in report
    assert "Battery:" in report


def test_settings_page_rejects_unknown_pages():
    assert "Unknown settings page" in files.abrir_configuracion_windows.invoke({"pagina": "regedit"})
