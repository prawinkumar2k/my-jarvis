"""Formal tool permission policy.

Policy fields map directly to the audit requirement:
tool_name, risk_level, allowed_profiles, requires_confirmation, audit_log.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ToolPolicy:
    tool_name: str
    risk_level: str
    allowed_profiles: tuple[str, ...]
    requires_confirmation: bool
    audit_log: bool


@dataclass(frozen=True)
class ToolPolicyDecision:
    allowed: bool
    reason: str
    policy: ToolPolicy


PUBLIC_POLICY = ToolPolicy(
    tool_name="*",
    risk_level="public",
    allowed_profiles=("admin", "guest", "authorized"),
    requires_confirmation=False,
    audit_log=False,
)

DEFAULT_TOOL_POLICIES: dict[str, ToolPolicy] = {
    "leer_archivo": ToolPolicy("leer_archivo", "critical", ("admin",), True, True),
    "analizar_pantalla": ToolPolicy("analizar_pantalla", "elevated", ("admin",), False, True),
    "controlar_pc": ToolPolicy("controlar_pc", "critical", ("admin",), True, True),
    "controlar_ventana": ToolPolicy("controlar_ventana", "elevated", ("admin",), False, True),
    "matar_proceso": ToolPolicy("matar_proceso", "critical", ("admin",), True, True),
    "borrar_memoria": ToolPolicy("borrar_memoria", "critical", ("admin",), True, True),
    "abrir_aplicacion": ToolPolicy("abrir_aplicacion", "elevated", ("admin",), False, True),
    "ejecutar_rutina": ToolPolicy("ejecutar_rutina", "elevated", ("admin",), False, True),
    "recargar_plugins": ToolPolicy("recargar_plugins", "elevated", ("admin",), False, True),
    "listar_ventanas": ToolPolicy("listar_ventanas", "elevated", ("admin",), False, True),
    "enfocar_ventana": ToolPolicy("enfocar_ventana", "elevated", ("admin",), False, True),
    "crear_plan_acciones": ToolPolicy("crear_plan_acciones", "elevated", ("admin",), False, True),
    "ver_plan_acciones": ToolPolicy("ver_plan_acciones", "elevated", ("admin",), False, True),
    "ejecutar_plan_acciones": ToolPolicy("ejecutar_plan_acciones", "critical", ("admin",), True, True),
    "crear_archivo_texto": ToolPolicy("crear_archivo_texto", "critical", ("admin",), True, True),
    "ejecutar_comando_terminal": ToolPolicy("ejecutar_comando_terminal", "critical", ("admin",), True, True),
    "buscar_en_wikipedia": ToolPolicy("buscar_en_wikipedia", "elevated", ("admin",), False, True),
    "reproducir_en_youtube": ToolPolicy("reproducir_en_youtube", "elevated", ("admin",), False, True),
    "computer_click": ToolPolicy("computer_click", "critical", ("admin",), True, True),
    "computer_type": ToolPolicy("computer_type", "critical", ("admin",), True, True),
    "computer_hotkey": ToolPolicy("computer_hotkey", "critical", ("admin",), True, True),
    "computer_scroll": ToolPolicy("computer_scroll", "elevated", ("admin",), False, True),
    "computer_inspect_screen": ToolPolicy("computer_inspect_screen", "elevated", ("admin",), False, True),
    "computer_drag_and_drop": ToolPolicy("computer_drag_and_drop", "critical", ("admin",), True, True),
    "consultar_estado_proactivo": ToolPolicy("consultar_estado_proactivo", "elevated", ("admin",), False, True),
    "ejecutar_accion_proactiva": ToolPolicy("ejecutar_accion_proactiva", "critical", ("admin",), True, True),
    "predecir_siguiente_accion": ToolPolicy("predecir_siguiente_accion", "elevated", ("admin",), False, True),
    "aprender_patron_rutina": ToolPolicy("aprender_patron_rutina", "elevated", ("admin",), False, True),
    "consultar_rutinas_predictivas": ToolPolicy("consultar_rutinas_predictivas", "elevated", ("admin",), False, True),
    "aprender_procedimiento": ToolPolicy("aprender_procedimiento", "elevated", ("admin",), False, True),
    "consultar_procedimientos": ToolPolicy("consultar_procedimientos", "elevated", ("admin",), False, True),
    "ejecutar_procedimiento": ToolPolicy("ejecutar_procedimiento", "critical", ("admin",), True, True),
    "recordar_episodio": ToolPolicy("recordar_episodio", "elevated", ("admin",), False, True),
    "guardar_memoria_entrelazada": ToolPolicy("guardar_memoria_entrelazada", "elevated", ("admin",), False, True),
    "consultar_memoria_unificada": ToolPolicy("consultar_memoria_unificada", "elevated", ("admin",), False, True),
    "enlazar_conceptos": ToolPolicy("enlazar_conceptos", "elevated", ("admin",), False, True),
    "sincronizar_boveda_conocimiento": ToolPolicy("sincronizar_boveda_conocimiento", "elevated", ("admin",), False, True),
    "ejecutar_consolidacion_memoria": ToolPolicy("ejecutar_consolidacion_memoria", "elevated", ("admin",), False, True),
    "crear_nota_boveda": ToolPolicy("crear_nota_boveda", "elevated", ("admin",), False, True),
    "buscar_en_boveda": ToolPolicy("buscar_en_boveda", "elevated", ("admin",), False, True),
    "busqueda_semantica_hibrida": ToolPolicy("busqueda_semantica_hibrida", "elevated", ("admin",), False, True),
    "consultar_memoria_jit": ToolPolicy("consultar_memoria_jit", "elevated", ("admin",), False, True),
    # File management (tools/files.py). Reads and reversible creates are elevated;
    # moving, renaming, organizing and deleting require explicit confirmation.
    "listar_carpeta": ToolPolicy("listar_carpeta", "elevated", ("admin",), False, True),
    "buscar_archivos": ToolPolicy("buscar_archivos", "elevated", ("admin",), False, True),
    "previsualizar_organizacion": ToolPolicy("previsualizar_organizacion", "elevated", ("admin",), False, True),
    "abrir_configuracion_windows": ToolPolicy("abrir_configuracion_windows", "elevated", ("admin",), False, True),
    "crear_carpeta": ToolPolicy("crear_carpeta", "elevated", ("admin",), False, True),
    "buscar_duplicados": ToolPolicy("buscar_duplicados", "elevated", ("admin",), False, True),
    "informacion_archivo": ToolPolicy("informacion_archivo", "elevated", ("admin",), False, True),
    "archivos_grandes": ToolPolicy("archivos_grandes", "elevated", ("admin",), False, True),
    # Clipboard: owner-only, on request only, contents never logged.
    # Reading needs a yes each time: the text may go to a cloud AI.
    "leer_portapapeles": ToolPolicy("leer_portapapeles", "critical", ("admin",), True, True),
    "limpiar_portapapeles": ToolPolicy("limpiar_portapapeles", "elevated", ("admin",), False, True),
    # Software: searching is read-only; installing always needs explicit approval.
    "recordatorio_recurrente": ToolPolicy("recordatorio_recurrente", "elevated", ("admin",), False, True),
    "diagnostico_sistema": ToolPolicy("diagnostico_sistema", "elevated", ("admin",), False, True),
    "buscar_programa": ToolPolicy("buscar_programa", "elevated", ("admin",), False, True),
    "ver_programa": ToolPolicy("ver_programa", "elevated", ("admin",), False, True),
    "instalar_programa": ToolPolicy("instalar_programa", "critical", ("admin",), True, True),
    "cancelar_instalacion": ToolPolicy("cancelar_instalacion", "elevated", ("admin",), False, True),
    "ejecutar_tarea_multipaso": ToolPolicy("ejecutar_tarea_multipaso", "elevated", ("admin",), False, True),
    "ver_tareas": ToolPolicy("ver_tareas", "elevated", ("admin",), False, True),
    "reanudar_tarea": ToolPolicy("reanudar_tarea", "elevated", ("admin",), False, True),
    "cancelar_tarea": ToolPolicy("cancelar_tarea", "elevated", ("admin",), False, True),
    # Everyday controls and companion tools: owner-only, reversible, audited.
    "control_multimedia": ToolPolicy("control_multimedia", "elevated", ("admin",), False, True),
    "ajustar_brillo": ToolPolicy("ajustar_brillo", "elevated", ("admin",), False, True),
    "captura_pantalla": ToolPolicy("captura_pantalla", "elevated", ("admin",), False, True),
    "organizar_ventanas": ToolPolicy("organizar_ventanas", "elevated", ("admin",), False, True),
    # Browser automation: clicking and typing can submit forms, buy or send messages, so each one
    # needs a yes (page text is untrusted and could try to steer the assistant).
    "click_en_navegador": ToolPolicy("click_en_navegador", "critical", ("admin",), True, True),
    "escribir_en_navegador": ToolPolicy("escribir_en_navegador", "critical", ("admin",), True, True),
    "listar_pantallas": ToolPolicy("listar_pantallas", "elevated", ("admin",), False, True),
    "mover_ventana_a_pantalla": ToolPolicy("mover_ventana_a_pantalla", "elevated", ("admin",), False, True),
    "poner_temporizador": ToolPolicy("poner_temporizador", "elevated", ("admin",), False, True),
    "poner_alarma": ToolPolicy("poner_alarma", "elevated", ("admin",), False, True),
    "guardar_nota": ToolPolicy("guardar_nota", "elevated", ("admin",), False, True),
    "leer_notas": ToolPolicy("leer_notas", "elevated", ("admin",), False, True),
    "borrar_nota": ToolPolicy("borrar_nota", "elevated", ("admin",), False, True),
    "copiar_al_portapapeles": ToolPolicy("copiar_al_portapapeles", "elevated", ("admin",), False, True),
    "copiar_archivo": ToolPolicy("copiar_archivo", "elevated", ("admin",), False, True),
    "mover_archivo": ToolPolicy("mover_archivo", "critical", ("admin",), True, True),
    "renombrar_archivo": ToolPolicy("renombrar_archivo", "critical", ("admin",), True, True),
    "organizar_carpeta": ToolPolicy("organizar_carpeta", "critical", ("admin",), True, True),
    "eliminar_archivo": ToolPolicy("eliminar_archivo", "critical", ("admin",), True, True),
    # Personal memory: owner-only; edits are audited.
    "ver_memorias": ToolPolicy("ver_memorias", "elevated", ("admin",), False, True),
    "editar_memoria": ToolPolicy("editar_memoria", "elevated", ("admin",), False, True),
    "olvidar_memoria": ToolPolicy("olvidar_memoria", "elevated", ("admin",), False, True),
    "modo_privado": ToolPolicy("modo_privado", "elevated", ("admin",), False, True),
}


def _profile_role(profile_id: str | None, authorized: bool) -> str:
    pid = str(profile_id or "").strip().lower()
    from core.jarvis_config import resolve_runtime_features

    if not resolve_runtime_features().allow_guest_mode and not pid.startswith("guest_") and pid != "guest":
        return "admin"
    if authorized:
        return "admin"
    pid = str(profile_id or "").strip().lower()
    if pid == "admin":
        return "admin" if authorized else "guest"
    if pid.startswith("guest_") or pid in {"guest", "guest_unverified", ""}:
        return "guest"
    return "guest"


def _policy_from_override(tool_name: str, raw: dict[str, Any]) -> ToolPolicy | None:
    entry = (raw or {}).get(tool_name)
    if not isinstance(entry, dict):
        return None
    allowed = entry.get("allowed_profiles", PUBLIC_POLICY.allowed_profiles)
    if isinstance(allowed, str):
        allowed = (allowed,)
    return ToolPolicy(
        tool_name=tool_name,
        risk_level=str(entry.get("risk_level") or "public"),
        allowed_profiles=tuple(str(x) for x in allowed),
        requires_confirmation=bool(entry.get("requires_confirmation", False)),
        audit_log=bool(entry.get("audit_log", False)),
    )


def get_tool_policy(tool_name: str, overrides: dict[str, Any] | None = None) -> ToolPolicy:
    name = str(tool_name or "").strip()
    override = _policy_from_override(name, overrides or {})
    if override:
        return override
    return DEFAULT_TOOL_POLICIES.get(name, PUBLIC_POLICY)


def tool_requires_authorization(tool_name: str, overrides: dict[str, Any] | None = None) -> bool:
    policy = get_tool_policy(tool_name, overrides=overrides)
    return policy.risk_level in {"critical", "elevated"} or policy.allowed_profiles == ("admin",)


def evaluate_tool_policy(
    tool_name: str,
    *,
    profile_id: str | None,
    authorized: bool,
    confirmed: bool,
    overrides: dict[str, Any] | None = None,
) -> ToolPolicyDecision:
    policy = get_tool_policy(tool_name, overrides=overrides)
    role = _profile_role(profile_id, authorized)

    role_allowed = role in policy.allowed_profiles
    authorized_allowed = "authorized" in policy.allowed_profiles and authorized
    if not role_allowed and not authorized_allowed:
        return ToolPolicyDecision(
            allowed=False,
            reason="La herramienta requiere autorizacion del Administrador.",
            policy=policy,
        )
    if policy.requires_confirmation and not confirmed:
        return ToolPolicyDecision(
            allowed=False,
            reason="La herramienta requiere confirmacion explicita.",
            policy=policy,
        )
    return ToolPolicyDecision(allowed=True, reason="", policy=policy)


def export_tool_policy_table(overrides: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    names = set(DEFAULT_TOOL_POLICIES)
    names.update((overrides or {}).keys())
    return {name: asdict(get_tool_policy(name, overrides=overrides)) for name in sorted(names)}
