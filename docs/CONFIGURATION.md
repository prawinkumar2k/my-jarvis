# Configuration

All settings live in `.env` (copy from `.env.example`). `.env` is git-ignored;
never commit it. Only the settings added or most relevant on this branch are
listed here; `.env.example` documents the rest.

## AI providers

| Variable | Default | Meaning |
| --- | --- | --- |
| `GEMINI_API_KEY` | — | Primary LLM and Gemini Live voice. |
| `GROQ_API_KEY` | — | Fallback LLM and Groq Whisper STT. |
| `JARVIS_LLM_PROVIDER` | gemini first | `groq` reverses the order. |

Without either key, AI routes return `llm_unconfigured`; status and local tools still start.

## Language

| Variable | Default | Meaning |
| --- | --- | --- |
| UI selector / `POST /api/language` | `en` | Session language: `en`, `es`, `ta`. Sets Whisper language, browser speech locale (`ta-IN`), Gemini Live directive, local voice. |
| `JARVIS_RESPONSE_LANGUAGE` | `auto` | `auto` mirrors each message (Tamil script → Tamil, Thanglish → Thanglish, English → English). Or pin: `en`, `ta`, `thanglish`, `es`. |
| `JARVIS_TTS_MODEL_TA` | empty | Path to a Tamil-capable Piper `.onnx`. Empty = English local voice is kept for Tamil mode; `/api/language` reports `local_tts_native: false`. |
| `JARVIS_WHISPER_MODEL` | `medium` | Larger models improve Tamil recognition at higher CPU/RAM cost. |

## Files and system tools

| Variable | Default | Meaning |
| --- | --- | --- |
| `JARVIS_FILE_WRITE_ROOTS` | Desktop | Folders JARVIS may list, search and modify. `;`-separated on Windows. Example: `C:\Users\you\Desktop;C:\Users\you\Downloads;D:\Projects` |
| `JARVIS_FILE_TOOLS_ENABLED` | `false` | Adds create folder, copy, move, rename, delete (Recycle Bin), organize. Does **not** enable the terminal. |
| `JARVIS_SYSTEM_TOOLS_ENABLED` | `false` | Adds terminal execution and text-file writes (and file tools). Advanced; still confirmation-gated. |

Read-only tools (list, search, organize preview, system info, Settings pages) are always available to the administrator profile.

## Security

| Variable | Meaning |
| --- | --- |
| `JARVIS_API_TOKEN` | Required for access beyond the local UI (LAN, other browsers). |
| `JARVIS_CORS_ORIGINS` | Trusted browser origins. |
| `JARVIS_VOICE_ID_ENABLED` | Voice biometrics; identification only, never sole authorization. |

Emergency stop: `POST /api/security/emergency-stop` with `{"engaged": true|false}` (critical route).
