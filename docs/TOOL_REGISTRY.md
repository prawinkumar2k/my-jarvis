  [SPOTIFY] Cache: C:\Users\prawi\AppData\Local\Jarvis\cache\spotify-oauth-cache
  [SPOTIFY] Web API credentials are not configured; Windows desktop fallback remains available.
# Tool Registry

Generated from `tools._LAZY_EXPORTS` and `core/security/tool_policy.py`. Every tool call passes
`ToolExecutionService` and `security_manager._security_guard` (emergency stop, blocked tools, strict
mode, policy). Inputs are typed LangChain schemas; confirmation is never a model-controlled argument.

Catalog column: **default** = always registered; **file opt-in** = `JARVIS_FILE_TOOLS_ENABLED`;
**system opt-in** = `JARVIS_SYSTEM_TOOLS_ENABLED`.

| Tool | Module | Risk | Level | Admin only | Confirmation | Audited | Catalog | Description |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `buscar_en_internet` | `tools.search` | public | 0 | no | no | no | default | Busca información actual de CUALQUIER TIPO. Prioridad: Tavily AI → Brave Search. Úsala para: - Clima en cualqu |
| `obtener_deportes_espn` | `tools.utilities` | public | 0 | no | no | no | default | Obtiene marcadores o detalles de cualquier deporte vía ESPN (nba, nfl, mlb, soccer/eng.1, etc). Si event_id no |
| `obtener_clima` | `tools.utilities` | public | 0 | no | no | no | default | Obtiene el clima actual de una ciudad específica usando proveedores de red o Google. |
| `abrir_navegador` | `tools.browser` | public | 0 | no | no | no | default | Abre el navegador predeterminado del sistema al destino indicado (Playwright opcional por config). |
| `navegar_en_navegador` | `tools.browser` | public | 0 | no | no | no | default | Navega a una URL o búsqueda en el navegador (predeterminado por defecto). |
| `click_en_navegador` | `tools.browser` | public | 0 | no | no | no | default | Hace click en la página actual (CSS/XPath o texto visible). |
| `escribir_en_navegador` | `tools.browser` | public | 0 | no | no | no | default | Escribe texto en un campo del navegador (selector CSS/XPath o placeholder). |
| `leer_pagina_navegador` | `tools.browser` | public | 0 | no | no | no | default | Lee título, URL y texto visible de la página actual en Playwright. |
| `cerrar_navegador_playwright` | `tools.browser` | public | 0 | no | no | no | default | Cierra la sesión de navegador controlada por Playwright. |
| `abrir_youtube` | `tools.browser` | public | 0 | no | no | no | default | Busca y reproduce un video en YouTube. Abre y reproduce el video directo cuando se especifique un tema o cread |
| `reproducir_en_youtube` | `modules.youtube.tools` | elevated | 0–1 | yes | no | yes | default | Busca en YouTube, analiza los títulos de los resultados y reproduce el video más parecido a la búsqueda. |
| `buscar_en_wikipedia` | `tools.browser` | elevated | 0–1 | yes | no | yes | default | Busca un tema y abre directamente el artículo de Wikipedia en el navegador del usuario. |
| `leer_archivo` | `tools.utilities` | critical | 2–3 | yes | yes | yes | default | Lee un archivo de texto del escritorio o ruta indicada y devuelve su contenido. SOLO cuando el usuario diga 'l |
| `poner_recordatorio` | `tools.utilities` | public | 0 | no | no | no | default | Programa un recordatorio de voz en X minutos. SOLO cuando el usuario diga 'recuérdame X en Y minutos/horas'. |
| `listar_recordatorios` | `tools.utilities` | public | 0 | no | no | no | default | List pending reminders with their ids and times. |
| `cancelar_recordatorio` | `tools.utilities` | public | 0 | no | no | no | default | Cancel one pending reminder by its id from listar_recordatorios or a unique word in its text. |
| `reproducir_en_spotify` | `modules.spotify.tools` | public | 0 | no | no | no | default | Play music using a cached Spotify API session or Spotify Desktop. |
| `reproducir_mix_spotify` | `modules.spotify.tools` | public | 0 | no | no | no | default | Play a seed and build a dynamic AutoMix around it. |
| `controlar_reproduccion` | `modules.spotify.tools` | public | 0 | no | no | no | default | Control Spotify through a cached API session or Spotify Desktop. |
| `agregar_a_cola_spotify` | `modules.spotify.tools` | public | 0 | no | no | no | default | Añade una canción a la cola de reproducción de Spotify sin interrumpir lo que suena actualmente. |
| `dar_like_spotify` | `modules.spotify.tools` | public | 0 | no | no | no | default | Guarda la canción que está sonando actualmente (o una específica) en tus 'Me Gusta' de Spotify. |
| `quitar_like_spotify` | `modules.spotify.tools` | public | 0 | no | no | no | default | Elimina la canción actual (o una específica) de tus 'Me Gusta' de Spotify. |
| `cancion_actual_spotify` | `modules.spotify.tools` | public | 0 | no | no | no | default | Obtiene el nombre, artista, álbum, progreso y estado de la canción que está sonando en Spotify. |
| `ajustar_volumen` | `tools.system` | public | 0 | no | no | no | default | Ajusta el volumen maestro del sistema (0-100), o sube/baja relativamente ('subir', 'bajar', '+10', '-10', '50% |
| `modo_no_molestar` | `tools.system` | public | 0 | no | no | no | default | Silencia o activa el sonido del sistema. |
| `controlar_pc` | `tools.system` | critical | 2–3 | yes | yes | yes | default | Controlar hardware del PC: apagar, reiniciar, hibernar, bloquear, cancelar. ADVERTENCIA: Usar UNICAMENTE cuand |
| `abrir_aplicacion` | `tools.system` | elevated | 0–1 | yes | no | yes | default | Abre aplicaciones locales y juegos en Windows/Linux/macOS. |
| `ver_procesos_pesados` | `tools.system` | public | 0 | no | no | no | default | Muestra procesos con mayor carga en CPU/RAM. |
| `matar_proceso` | `tools.system` | critical | 2–3 | yes | yes | yes | default | Detiene un proceso por nombre. Requiere autorización. |
| `borrar_memoria` | `tools.system` | critical | 2–3 | yes | yes | yes | default | Reseteo total de memoria. Autorización de nivel 5 obligatoria. |
| `guardar_dato_memoria` | `tools.memory` | public | 0 | no | no | no | default | Guarda un dato, preferencia o recuerdo en la memoria permanente del usuario para recordarlo siempre. |
| `ver_memorias` | `tools.memory` | elevated | 0–1 | yes | no | yes | default | List everything JARVIS has saved about the user in long-term memory, numbered. Use for 'what do you remember a |
| `editar_memoria` | `tools.memory` | elevated | 0–1 | yes | no | yes | default | Replace one saved memory, chosen by its number from ver_memorias or a unique word in it. |
| `olvidar_memoria` | `tools.memory` | elevated | 0–1 | yes | no | yes | default | Delete one saved memory (by number from ver_memorias or a unique word in it), including its copy in the cognit |
| `modo_privado` | `tools.memory` | elevated | 0–1 | yes | no | yes | default | Turn private mode on or off. While on, JARVIS saves nothing new to long-term memory. |
| `listar_ventanas` | `tools.desktop_control` | elevated | 0–1 | yes | no | yes | default | Lista ventanas visibles del escritorio local. |
| `enfocar_ventana` | `tools.desktop_control` | elevated | 0–1 | yes | no | yes | default | Enfoca una ventana visible por titulo parcial o identificador. |
| `controlar_ventana` | `tools.desktop_control` | elevated | 0–1 | yes | no | yes | default | Controla una ventana visible: enfocar, minimizar, maximizar, restaurar o cerrar. |
| `crear_plan_acciones` | `tools.action_plan` | elevated | 0–1 | yes | no | yes | default | Crea un plan supervisado de acciones locales sin ejecutarlo. |
| `ver_plan_acciones` | `tools.action_plan` | elevated | 0–1 | yes | no | yes | default | Muestra un plan de acciones pendiente o los planes recientes. |
| `ejecutar_plan_acciones` | `tools.action_plan` | critical | 2–3 | yes | yes | yes | default | Ejecuta un plan de acciones previamente creado solo con confirmacion explicita. |
| `frase_motivacional` | `tools.utilities` | public | 0 | no | no | no | default | Genera frase motivacional o chiste al estilo JARVIS. |
| `analizar_pantalla` | `tools.utilities` | elevated | 0–1 | yes | no | yes | default | Toma una captura de pantalla y analiza el contenido visual (HUD). |
| `recargar_plugins` | `tools.utilities` | elevated | 0–1 | yes | no | yes | default | Recarga plugins dinámicos desde src/backend/plugins. |
| `ejecutar_rutina` | `tools.utilities` | elevated | 0–1 | yes | no | yes | default | Ejecuta rutinas predefinidas: trabajo, gaming, buenos dias. |
| `evaluar_expresion_matematica` | `tools.utilities` | public | 0 | no | no | no | default | Evalúa una expresión matemática compuesta (aritmética, raíces, potencias, trigonometría, logaritmos). Ejemplos |
| `listar_carpeta` | `tools.files` | elevated | 0–1 | yes | no | yes | default | List files and folders inside an authorized folder (Desktop or JARVIS_FILE_WRITE_ROOTS). Use for 'what is in m |
| `buscar_archivos` | `tools.files` | elevated | 0–1 | yes | no | yes | default | Search authorized folders for files whose name matches a pattern or contains a word (e.g. '*.pdf', 'invoice',  |
| `informacion_sistema` | `tools.files` | public | 0 | no | no | no | default | Report CPU, memory, disk, battery and uptime for this computer. |
| `abrir_configuracion_windows` | `tools.files` | elevated | 0–1 | yes | no | yes | default | Open a Windows Settings page. Valid pages: display, sound, bluetooth, wifi, network, battery, power, apps, def |
| `previsualizar_organizacion` | `tools.files` | elevated | 0–1 | yes | no | yes | default | Preview how loose files in a folder would be grouped into Images, Documents, Audio, Video, Archives, Installer |
| `buscar_duplicados` | `tools.files` | elevated | 0–1 | yes | no | yes | default | Find duplicate files (identical content by SHA-256) in an authorized folder. Read-only: never deletes. |
| `archivos_grandes` | `tools.files` | elevated | 0–1 | yes | no | yes | default | List the largest files in an authorized folder. Read-only. |
| `leer_portapapeles` | `tools.clipboard` | elevated | 0–1 | yes | no | yes | default | Read the text currently on the clipboard, only when the user asks (e.g. 'clipboard la enna irukku', 'explain w |
| `copiar_al_portapapeles` | `tools.clipboard` | elevated | 0–1 | yes | no | yes | default | Put text on the clipboard so the user can paste it (replaces the current clipboard text). |
| `crear_carpeta` | `tools.files` | elevated | 0–1 | yes | no | yes | file opt-in | Create a new folder inside an authorized folder. |
| `copiar_archivo` | `tools.files` | elevated | 0–1 | yes | no | yes | file opt-in | Copy a file or folder to another location inside the authorized folders. Never overwrites. |
| `mover_archivo` | `tools.files` | critical | 2–3 | yes | yes | yes | file opt-in | Move a file or folder to another authorized folder. Never overwrites. Requires confirmation. |
| `renombrar_archivo` | `tools.files` | critical | 2–3 | yes | yes | yes | file opt-in | Rename a file or folder in place (new name only, no folders). Requires confirmation. |
| `eliminar_archivo` | `tools.files` | critical | 2–3 | yes | yes | yes | file opt-in | Delete a file or folder inside the authorized folders. On Windows it goes to the Recycle Bin. Always requires  |
| `organizar_carpeta` | `tools.files` | critical | 2–3 | yes | yes | yes | file opt-in | Group loose files in a folder into type subfolders, exactly as previsualizar_organizacion shows. Requires conf |
| `crear_archivo_texto` | `tools.system` | critical | 2–3 | yes | yes | yes | system opt-in | Crea un archivo de texto dentro de las raíces permitidas. |
| `ejecutar_comando_terminal` | `tools.system` | critical | 2–3 | yes | yes | yes | system opt-in | Ejecuta un comando en la consola/terminal o PowerShell del sistema operativo (por ejemplo dir, mkdir, echo, sc |
| `computer_click` | `tools.computer_use` | critical | 2–3 | yes | yes | yes | default | Hace clic en un elemento por nombre o en coordenadas X/Y. coordinate_space debe ser 'normalized' (0..1000 para |
| `computer_type` | `tools.computer_use` | critical | 2–3 | yes | yes | yes | default | Escribe texto en el campo o ventana activa, o en el elemento indicado por target. Opcionalmente borra el conte |
| `computer_hotkey` | `tools.computer_use` | critical | 2–3 | yes | yes | yes | default | Ejecuta una combinacion o atajo de teclado en la computadora, como 'ctrl+c', 'ctrl+v', 'ctrl+s', 'alt+tab', 'w |
| `computer_scroll` | `tools.computer_use` | elevated | 0–1 | yes | no | yes | default | Realiza scroll vertical u horizontal en la ventana o sobre el elemento indicado. Direcciones: 'down', 'up', 'l |
| `computer_inspect_screen` | `tools.computer_use` | elevated | 0–1 | yes | no | yes | default | Inspecciona la pantalla e identifica elementos interactivos visibles (botones, campos de texto, pestanas, cont |
| `computer_drag_and_drop` | `tools.computer_use` | critical | 2–3 | yes | yes | yes | default | Arrastra entre coordenadas en espacio 'normalized' (0..1000) o 'pixel' del escritorio virtual. |
| `consultar_estado_proactivo` | `tools.proactive` | elevated | 0–1 | yes | no | yes | default | Inspecciona el contexto de trabajo actual en el escritorio (app activa, terminal, recursos) y retorna sugerenc |
| `ejecutar_accion_proactiva` | `tools.proactive` | critical | 2–3 | yes | yes | yes | default | Aplica la solucion sugerida por una alerta proactiva especificada por su action_id. |
| `predecir_siguiente_accion` | `tools.proactive` | elevated | 0–1 | yes | no | yes | default | Evalúa el estado del sistema, horario, app activa y patrones de rutina para predecir y sugerir la siguiente ac |
| `aprender_patron_rutina` | `tools.proactive` | elevated | 0–1 | yes | no | yes | default | Registra una nueva rutina aprendida o automatización predictiva basada en horario (ej: '09:00') o aplicación a |
| `consultar_rutinas_predictivas` | `tools.proactive` | elevated | 0–1 | yes | no | yes | default | Consulta todas las rutinas y patrones de comportamiento registrados en el motor predictivo. |
| `aprender_procedimiento` | `tools.procedural_memory` | elevated | 0–1 | yes | no | yes | default | Aprende y guarda un nuevo procedimiento o rutina de varios pasos y lo entrelaza en la memoria. |
| `consultar_procedimientos` | `tools.procedural_memory` | elevated | 0–1 | yes | no | yes | default | Lista todos los procedimientos y recetas aprendidos por JARVIS, o busca uno especifico. |
| `ejecutar_procedimiento` | `tools.procedural_memory` | critical | 2–3 | yes | yes | yes | default | Ejecuta un procedimiento aprendido previamente por su nombre o frase activadora. |
| `recordar_episodio` | `tools.procedural_memory` | elevated | 0–1 | yes | no | yes | default | Busca en la memoria episodica de largo plazo hitos pasados, soluciones tecnicas previas o acuerdos anteriores. |
| `guardar_memoria_entrelazada` | `tools.procedural_memory` | elevated | 0–1 | yes | no | yes | default | Guarda un nuevo nodo de conocimiento en la memoria cognitiva unificada y lo entrelaza con conceptos existentes |
| `consultar_memoria_unificada` | `tools.procedural_memory` | elevated | 0–1 | yes | no | yes | default | Realiza una busqueda asociativa profunda en toda la red cognitiva entrelazada (hechos, habilidades, proyectos, |
| `enlazar_conceptos` | `tools.procedural_memory` | elevated | 0–1 | yes | no | yes | default | Crea una conexion semantica sinaptica directa entre dos conceptos de la memoria. |
| `sincronizar_boveda_conocimiento` | `tools.procedural_memory` | elevated | 0–1 | yes | no | yes | default | Escanea la bóveda de notas en Markdown (tipo Obsidian), extrae wikilinks [[...]] y etiquetas, e indexa todo en |
| `ejecutar_consolidacion_memoria` | `tools.procedural_memory` | elevated | 0–1 | yes | no | yes | default | Ejecuta el ciclo de consolidación profunda de memoria (sleep cycle): sincroniza la bóveda, consolida hechos/co |
| `crear_nota_boveda` | `tools.procedural_memory` | elevated | 0–1 | yes | no | yes | default | Crea o actualiza una nota estructurada en Markdown en la bóveda de conocimiento con enlaces bidireccionales [[ |
| `buscar_en_boveda` | `tools.procedural_memory` | elevated | 0–1 | yes | no | yes | default | Busca directamente en el texto de los archivos Markdown de la bóveda de conocimiento. |
| `busqueda_semantica_hibrida` | `tools.procedural_memory` | elevated | 0–1 | yes | no | yes | default | Nombre compatible para búsqueda híbrida experimental: hashing léxico determinista, coincidencia textual y expa |
| `consultar_memoria_jit` | `tools.procedural_memory` | elevated | 0–1 | yes | no | yes | default | Consulta una partición de memoria RAM pre-calentada; exacta por hash o aproximada mediante ranking léxico acot |

Timeouts: terminal commands 20 s; file search 8 s / 20,000 files; startup scripts 60 s; Gemini Live tools use the live session timeouts.
