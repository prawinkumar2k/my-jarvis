"""Diagnostics summaries keep 'unavailable' distinct from zero; browser actions need approval."""

from core import diagnostics
from core.security.confirmation_preview import preview
from core.security.tool_policy import get_tool_policy


def _report(**overrides):
    base = {
        "cpu_memory": {"cpu_percent": 0.0, "cpu_logical_cores": 8, "memory_percent": 50.0,
                       "memory_used_gb": 8.0, "memory_total_gb": 16.0, "uptime_hours": 1.0},
        "disks": [{"drive": "C:\\", "percent": 40.0, "free_gb": 100.0, "total_gb": 200.0}],
        "disk_health": None,
        "battery": None,
        "gpus": [
            {"name": "NVIDIA T500", "utilization_percent": 0.0, "memory_used_mb": 0.0, "memory_total_mb": 4096.0},
            {"name": "Intel Iris Xe", "utilization_percent": None},
        ],
        "top_processes": [],
        "tools": {"winget": None, "ffmpeg": False, "ollama": None},
    }
    base.update(overrides)
    return base


def test_zero_is_reported_as_zero_and_missing_as_unavailable():
    text = diagnostics.summarize(_report())
    assert "CPU 0%" in text
    assert "GPU NVIDIA T500: 0% busy, VRAM 0/4096 MB" in text
    assert "GPU Intel Iris Xe: utilization unavailable" in text
    assert "Disk health: unavailable" in text
    assert "Battery: none or unavailable" in text
    assert "winget missing" in text and "FFmpeg missing" in text and "Ollama not running" in text


def test_nvidia_placeholders_are_not_numbers():
    assert diagnostics._number("[N/A]") is None
    assert diagnostics._number("[Not Supported]") is None
    assert diagnostics._number("37") == 37.0


def test_a_failing_section_is_marked_unavailable_not_dropped(monkeypatch):
    def broken():
        raise PermissionError("denied")

    for name in ("cpu_memory", "disks", "disk_health", "battery", "gpus", "top_processes", "tool_status"):
        monkeypatch.setattr(diagnostics, name, (lambda: None) if name != "gpus" else broken)
    report = diagnostics.collect()
    assert report["gpus"] is None and report["unavailable"] == {"gpus": "PermissionError"}


def test_browser_click_and_type_need_confirmation_and_say_what_happens():
    for name in ("click_en_navegador", "escribir_en_navegador"):
        policy = get_tool_policy(name)
        assert policy.requires_confirmation and policy.allowed_profiles == ("admin",)
    assert not get_tool_policy("leer_pagina_navegador").requires_confirmation
    assert "submit" in preview("escribir_en_navegador", {"selector": "#q", "texto": "hello", "enter": True})
    assert "5 characters" in preview("escribir_en_navegador", {"selector": "#q", "texto": "hello"})
    assert "#buy" in preview("click_en_navegador", {"selector": "#buy"})
