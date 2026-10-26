"""Chat/voice tools for the persistent multi-step task engine."""

from __future__ import annotations

import json

from core import task_engine
from langchain_core.tools import tool


@tool
def ejecutar_tarea_multipaso(objetivo: str, pasos_json: str) -> str:
    """Preferred tool for any multi-step task ("do X, then Y, then Z", "create a task", "saved task"):
    runs existing JARVIS tools in order, saved so it survives restarts and shows in the task panel.
    pasos_json: JSON list like [{"tool": "abrir_aplicacion", "args": {"nombre_app": "chrome"}},
    {"tool": "organizar_ventanas", "args": {"ventanas": "Chrome, VS Code"}}] (max 12 steps).
    Risky steps pause for approval in the JARVIS control panel."""
    try:
        steps = json.loads(pasos_json) if isinstance(pasos_json, str) else pasos_json
        task = task_engine.create_task(objetivo, steps)
    except (ValueError, json.JSONDecodeError) as exc:
        return f"Task not created: {exc}"
    return task_engine.summarize(task_engine.run_task(task["id"]))


@tool
def ver_tareas() -> str:
    """List recent multi-step tasks with their state (completed, failed, approval_required, interrupted)."""
    tasks = task_engine.list_tasks(10)
    if not tasks:
        return "No tasks yet."
    return "\n".join(task_engine.summarize(t).splitlines()[0] for t in tasks)


@tool
def reanudar_tarea(id_tarea: str) -> str:
    """Resume an interrupted or pending task by id. Completed steps are not repeated."""
    task = task_engine.get_task(str(id_tarea).strip())
    if task is None:
        return "No task with that id."
    if task["state"] == "approval_required":
        return "That task is waiting for your approval in the JARVIS control panel."
    return task_engine.summarize(task_engine.run_task(task["id"]))


@tool
def cancelar_tarea(id_tarea: str) -> str:
    """Cancel a task by id. Steps already completed are not undone."""
    task = task_engine.cancel_task(str(id_tarea).strip())
    if task is None:
        return "No task with that id."
    return f"Task {task['id']} is now {task['state']}. Completed steps were not undone."
