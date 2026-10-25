# Security Model

For reporting vulnerabilities see [`.github/SECURITY.md`](../.github/SECURITY.md).

JARVIS does **not** have unrestricted control of the computer. It runs as your
normal Windows user, never elevates, and can only call tools in its catalog.

## Risk levels

| Level | Policy | Examples |
| --- | --- | --- |
| 0 read-only | `public` / `elevated` | system info, list/search files, organize preview, process list |
| 1 reversible | `elevated` | open app, volume, open Settings page, create folder, copy (never overwrites) |
| 2 material | `critical` + confirmation | move, rename, organize, run action plan, terminal (opt-in) |
| 3 high-risk | `critical` + confirmation | delete (Recycle Bin on Windows), kill process, shutdown, wipe memory |

`elevated` and `critical` tools are administrator-only. Confirmation comes from
the control panel or authorization resume, never from an argument the model
can set. Voice identification alone never grants authorization.

## Files

- Every path is resolved (symlinks, `..`) and must stay inside `JARVIS_FILE_WRITE_ROOTS`.
- `.env`, `.env.*` (except `.env.example`), `*.pem`, `*.key`, `*.pfx`, `id_rsa*`, `credentials*.json`, `client_secret*.json`, Spotify caches, `.git`, `.ssh`, `.aws`, `.gnupg` are invisible and untouchable.
- Copy/move/rename refuse to overwrite. A root folder itself cannot be deleted.
- Mutating file tools are off until `JARVIS_FILE_TOOLS_ENABLED=true`.

## Emergency stop

STOP button, `Ctrl+Shift+X`, or `POST /api/security/emergency-stop`:

- Both execution gates refuse every tool until released.
- All Gemini Live sessions are closed; the UI stops local speech playback and the voice stream.
- Requests blocked by the stop are not retried after release.
- It cannot undo completed actions or recall requests already sent to external services.

## Language and untrusted content

The language policy only selects the reply language. Website, document and
tool output remain data; they cannot change the policy, the tool catalog, or
memory without going through the same guarded tools.

## Logs

`logs/log.txt` (under `%LOCALAPPDATA%\Jarvis`) contains plaintext conversation
history with secrets redacted. File tools log only exception class names, never
paths or contents.
