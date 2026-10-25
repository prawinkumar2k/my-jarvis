# Implementation Plan and Continuation Steps

Phases follow the master prompt. ✅ done on `feature/jarvis-ultimate`, 🟡 partial, ⬜ not started.

| Phase | Scope | State |
| --- | --- | --- |
| A | Audit and baseline | ✅ [IMPLEMENTATION_AUDIT.md](IMPLEMENTATION_AUDIT.md) |
| B | Setup repair | ✅ ZIP/no-remote voice download; upstream links removed |
| C | Multilingual text and voice | 🟡 Tamil/Thanglish text verified; spoken Tamil needs manual check; no local Tamil TTS |
| D | Wake word, voice profiles | ⬜ local wake word; profiles are upstream (off by default) |
| E | Desktop tools and permissions | 🟡 files, system info, Settings, emergency stop done; clipboard, duplicates, monitors, winget open |
| F | Planner with DAG, retries, checkpoints | ⬜ (upstream exactly-once pipeline exists) |
| G | Coding agent, browser, dev diagnostics | ⬜ (upstream Playwright tools exist) |
| H | Memory, knowledge base, vision, offline | ⬜ beyond upstream |
| I | Calendar, email, notes, documents | ⬜ needs OAuth integrations |
| J | Scheduling, watchdog, backups | ⬜ beyond upstream |
| K | UI, packaging, security review | 🟡 STOP button, Tamil UI; visual verification pending |
| L | Regression and docs | ✅ this documentation set |

## Next steps, highest value first

1. **Manually verify voice in Tamil** (checklist in [TEST_REPORT.md](TEST_REPORT.md)) and record results in the feature matrix.
2. **Clipboard tools** in `tools/files.py` style: `leer_portapapeles` (elevated, redacts `AIza…`/`gsk_…`/private-key patterns before returning), `copiar_al_portapapeles` (critical when replacing non-empty content). Use `ctypes` `OpenClipboard`/`GetClipboardData(CF_UNICODETEXT)`; no new dependency.
3. **Duplicate finder**: read-only, group by size then SHA-256, report only; reuse `resolve_in_roots`.
4. **winget**: `buscar_paquete` (read-only, `winget search --exact --source winget`), `instalar_paquete` (critical, opt-in, exact `Publisher.App` ID regex, captured exit code, post-install `winget list --id`).
5. **Local wake word**: evaluate openWakeWord (Apache-2.0, ONNX, CPU) behind `JARVIS_WAKE_WORD_ENGINE=openwakeword`; keep browser recognition as fallback; document the model license in `THIRD_PARTY_NOTICES.md`.
6. **Persistent task checkpoints**: store `ExecutionReceipt`s in SQLite keyed by `request_id:step_id` so a restart cannot replay a non-idempotent step.
7. **Tamil local TTS**: if a Tamil Piper or other offline voice with a redistributable license becomes available, add it to `LANGUAGE_CONFIG["ta"]` with `tts_native: True` and update `THIRD_PARTY_NOTICES.md` and the release builder.

Each step: add tests first for security-sensitive behavior, run the gates in [TEST_REPORT.md](TEST_REPORT.md), update [FEATURE_MATRIX.md](FEATURE_MATRIX.md).
