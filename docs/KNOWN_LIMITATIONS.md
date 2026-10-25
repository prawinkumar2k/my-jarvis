# Known Limitations

- **No local Tamil voice.** Piper ships no bundled Tamil model here; local TTS keeps the English voice in Tamil mode. Spoken Tamil output depends on Gemini Live (online).
- **Spoken Tamil/Thanglish not verified** in this environment (no microphone, no API key used). Text-level behavior is tested.
- **Thanglish detection is lexicon-based.** One- or two-word inputs may be classified as English; reply then follows the session language or English.
- **Fixed messages** (Spotify, weather, errors) exist only in English and Spanish; Tamil mode uses English for them.
- **Wake word** uses browser speech recognition ("jarvis"), which in Chromium/WebView2 sends audio to an online service. There is no offline wake-word engine.
- **Recycle Bin deletion** is implemented through `SHFileOperationW` but not exercised by automated tests.
- **Emergency stop** cannot interrupt a tool call already running inside a worker thread; it blocks the next one. It cannot reverse completed or externally submitted actions.
- **STOP button and Tamil UI** have not been visually checked in the desktop window on this branch.
- **Not implemented:** clipboard tools, duplicate finder, multi-monitor layouts, virtual desktops, winget, parallel task DAG with persistent checkpoints, coding-agent workflow, calendar/email/meeting notes, Docker/database diagnostics, local LLM. See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
- **Pre-existing test failure:** `test_conversation_layout_is_not_clipped_by_center_stage` fails on untouched upstream code too.
- **No remote repository** is configured; upstream links were removed. Add your remote with `git remote add origin <url>`.
