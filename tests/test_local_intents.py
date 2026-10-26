from __future__ import annotations

import pytest
from core.brain.local_intents import match_local_intent


@pytest.mark.parametrize(
    ("text", "tool", "args"),
    [
        ("Open Chrome.", "abrir_aplicacion", {"nombre_app": "chrome"}),
        ("Hey JARVIS, open VS Code", "abrir_aplicacion", {"nombre_app": "code"}),
        ("chrome open pannu", "abrir_aplicacion", {"nombre_app": "chrome"}),
        ("Notepad open pannunga da", "abrir_aplicacion", {"nombre_app": "notepad"}),
        ("Pause music.", "control_multimedia", {"accion": "play_pause"}),
        ("song niruthu", "control_multimedia", {"accion": "play_pause"}),
        ("Next song.", "control_multimedia", {"accion": "next"}),
        ("adutha song podu", "control_multimedia", {"accion": "next"}),
        ("Previous song.", "control_multimedia", {"accion": "previous"}),
        ("Brightness 60.", "ajustar_brillo", {"nivel": "60"}),
        ("Brightness kammi pannu.", "ajustar_brillo", {"nivel": "down"}),
        ("increase brightness", "ajustar_brillo", {"nivel": "up"}),
        ("Take screenshot.", "captura_pantalla", {}),
        ("screenshot edu", "captura_pantalla", {}),
        ("Left-la Chrome, right-la VS Code.", "organizar_ventanas", {"ventanas": "chrome, vs code", "distribucion": "split"}),
        ("Set a 5 minute timer.", "poner_temporizador", {"duracion": "5 minute"}),
        ("10 nimisham timer vai", "poner_temporizador", {"duracion": "10 nimisham"}),
        ("timer for 90 seconds", "poner_temporizador", {"duracion": "90 seconds"}),
        ("Set an alarm for 7:30.", "poner_alarma", {"hora": "7:30"}),
        ("7:30-ku alarm vai", "poner_alarma", {"hora": "7:30"}),
        ("wake me up at 6 am", "poner_alarma", {"hora": "6 am"}),
        ("Note: buy milk", "guardar_nota", {"texto": "buy milk"}),
        ("idha note pannu: call Ravi at 6", "guardar_nota", {"texto": "call ravi at 6"}),
        ("Read my notes.", "leer_notas", {}),
        ("en notes sollu", "leer_notas", {}),
        ("Today's summary.", "resumen_del_dia", {}),
        ("inniku summary sollu", "resumen_del_dia", {}),
        ("Are you okay?", "estado_jarvis", {}),
        ("nee ok-a", "estado_jarvis", {}),
    ],
)
def test_everyday_commands_need_no_ai(text, tool, args):
    assert match_local_intent(text) == (tool, args)


@pytest.mark.parametrize(
    "text",
    [
        "What is the capital of France?",
        "open the report I wrote yesterday and summarize it",
        "why is my song not playing on spotify?",
        "tell me about brightness in astronomy and how stars differ",
        "explain how a timer interrupt works in a microcontroller",
        "Vanakkam JARVIS, eppadi irukka?",
        "stop",
        "",
    ],
)
def test_questions_still_go_to_the_ai(text):
    assert match_local_intent(text) is None


def test_router_uses_local_intent_without_llm():
    from core.brain.router import plan_hybrid
    from core.command_pipeline.models import CommandRequest

    request = CommandRequest.create(text="Next song", profile_id="admin", channel="chat", language="en", request_id="r1")
    plan = plan_hybrid(request)
    assert plan is not None
    assert [step.tool_name for step in plan.steps] == ["control_multimedia"]
