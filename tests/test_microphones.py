"""Microphone selection and listener recovery. Uses a fake sounddevice (no real audio is captured)."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from voice import microphones, wake_word

MAPPER = {"name": "Microsoft Sound Mapper - Input", "hostapi": 0, "max_input_channels": 2}
ARRAY_MME = {"name": "Microphone Array (Intel\ufffd Smart ", "hostapi": 0, "max_input_channels": 6}
HEADSET_MME = {"name": "Headset Microphone (USB Audio)", "hostapi": 0, "max_input_channels": 1}
SPEAKERS = {"name": "Speakers", "hostapi": 0, "max_input_channels": 0}
ARRAY_DS = {"name": "Microphone Array (Intel\ufffd Smart Sound Technology for Digital Microphones)", "hostapi": 1, "max_input_channels": 6}


class FakeSD:
    def __init__(self, devices, default_in=0):
        self.devices = devices
        self.default = SimpleNamespace(device=[default_in, -1])

    def query_devices(self, index=None):
        return self.devices if index is None else self.devices[index]

    def query_hostapis(self, index=None):
        apis = [{"name": "MME"}, {"name": "Windows DirectSound"}]
        return apis if index is None else apis[index]


@pytest.fixture
def prefs(monkeypatch, tmp_path):
    monkeypatch.setattr(microphones, "_pref_path", lambda: tmp_path / "microphone.json")


def test_lists_real_inputs_once_with_full_names():
    sd = FakeSD([MAPPER, ARRAY_MME, SPEAKERS, HEADSET_MME, ARRAY_DS], default_in=0)
    devices = microphones.list_input_devices(sd)
    assert [d["name"] for d in devices] == ["Microphone Array (Intel Smart", "Headset Microphone (USB Audio)"]
    assert devices[0]["label"] == "Microphone Array (Intel Smart Sound Technology for Digital Microphones)"
    assert devices[0]["default"] is True  # mapper default -> first real device


def test_select_saves_by_name_and_rejects_unknown_devices(prefs):
    sd = FakeSD([MAPPER, ARRAY_MME, HEADSET_MME])
    assert microphones.select("Headset Microphone (USB Audio)", sd) == (True, "Headset Microphone (USB Audio)")
    assert microphones.selected_name() == "Headset Microphone (USB Audio)"
    assert microphones.resolve_device(sd)[:2] == (2, "Headset Microphone (USB Audio)")
    ok, message = microphones.select("Some Bluetooth Mic", sd)
    assert not ok and "not connected" in message
    assert microphones.selected_name() == "Headset Microphone (USB Audio)"  # unchanged


def test_unplugged_choice_falls_back_to_default_and_says_so(prefs):
    microphones.select("Headset Microphone (USB Audio)", FakeSD([MAPPER, HEADSET_MME]))
    index, name, note = microphones.resolve_device(FakeSD([MAPPER, ARRAY_MME]))
    assert index is None and name.startswith("Microphone Array")
    assert "not connected" in note


class FakeStream:
    def __init__(self, listener, reads_before_error):
        self.listener, self.left = listener, reads_before_error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n):
        if self.left is None:
            self.listener._stop.set()
            return np.zeros((n, 1), dtype=np.int16), False
        if self.left <= 0:
            raise OSError("PortAudio device unavailable")
        self.left -= 1
        return np.zeros((n, 1), dtype=np.int16), False


class SilentModel:
    def predict(self, _frame):
        return {"hey_jarvis": 0.0}


@pytest.fixture
def listener(monkeypatch):
    monkeypatch.setattr(microphones, "resolve_device", lambda sd=None: (None, "Test mic", ""))
    item = wake_word.WakeWordListener()
    waits = []
    monkeypatch.setattr(item._stop, "wait", waits.append)
    return item, waits


def test_listener_recovers_after_a_temporary_device_error(listener):
    item, waits = listener
    plan = iter([0, 0, None])  # fail, fail, then a healthy stream
    opened = []

    def open_stream(device):
        opened.append(device)
        return FakeStream(item, next(plan))

    item._open_stream = open_stream
    item._run(SilentModel())
    assert len(opened) == 3  # one stream at a time, reopened after each error
    assert waits == [1.0, 2.0]  # exponential backoff
    assert item.device_name == "Test mic"


def test_listener_gives_up_after_bounded_retries(listener):
    item, waits = listener
    opened = []

    def always_broken(device):
        opened.append(device)
        return FakeStream(item, 0)

    item._open_stream = always_broken
    item._run(SilentModel())
    assert len(opened) == wake_word.MAX_RECONNECTS + 1
    assert item.state == "failed"
    assert "microphone" in item.error.lower()
    assert waits == [1.0, 2.0, 4.0, 8.0, 16.0]


def test_status_reports_device_and_state(listener):
    item, _ = listener
    status = item.status()
    assert status["state"] == "stopped" and status["listening"] is False
    assert {"device", "reconnects"} <= status.keys()


def test_microphone_route_lists_selects_and_blocks_hostile_origins(monkeypatch, prefs):
    import asyncio

    import jarvis_backend

    monkeypatch.setenv("JARVIS_TEST_MODE", "1")
    sd = FakeSD([MAPPER, ARRAY_MME, HEADSET_MME])
    monkeypatch.setattr(microphones, "_sd", lambda: sd)
    restarts = []
    monkeypatch.setattr(wake_word.wake_word_listener, "restart", lambda: restarts.append(True) or (True, "ok"))

    async def run():
        client = jarvis_backend.app.test_client()
        h = {"Origin": "http://localhost:5002"}
        listed = await (await client.get("/api/security/microphones", headers=h)).get_json()
        chosen = await client.post("/api/security/microphones", json={"name": "Headset Microphone (USB Audio)"}, headers=h)
        unknown = await client.post("/api/security/microphones", json={"name": "Nope"}, headers=h)
        bad = await client.post("/api/security/microphones", json={"name": 5}, headers=h)
        hostile = await client.post("/api/security/microphones", json={"name": None}, headers={"Origin": "https://evil.example"})
        return listed, chosen.status_code, (await chosen.get_json())["selected"], unknown.status_code, bad.status_code, hostile.status_code

    listed, chosen, selected, unknown, bad, hostile = asyncio.run(run())
    assert [d["name"] for d in listed["devices"]] == ["Microphone Array (Intel Smart", "Headset Microphone (USB Audio)"]
    assert chosen == 200 and selected == "Headset Microphone (USB Audio)"
    assert restarts == [True]  # the listener reopened on the new device
    assert unknown == 409 and bad == 400
    assert hostile == 403
    assert microphones.selected_name() == "Headset Microphone (USB Audio)"
