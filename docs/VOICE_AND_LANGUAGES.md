# Voice and Languages

## Capability table

| Capability | Engine | Local or cloud | Status |
| --- | --- | --- | --- |
| Written English / Tamil script / Thanglish / Spanish understanding and matching replies | Gemini or Groq LLM + `utils/language_detection.py` | Detection local; reply cloud | PASS (detection and prompt policy tested) |
| Mixed Tamil-English sentences | same | same | PASS for detection; reply quality depends on the model |
| Spoken English recognition | Gemini Live, Groq Whisper, or local faster-whisper | cloud or local | existing upstream feature |
| Spoken Tamil recognition | faster-whisper `ta`, browser `ta-IN`, Gemini Live | local or cloud | PARTIAL — configured, not tested with a microphone |
| Spoken Thanglish recognition | same engines; output is Tamil script or English words | — | PARTIAL — no Thanglish-specific model |
| Tamil speech output | Gemini Live native audio | cloud | PARTIAL — not tested here |
| Tamil speech output, offline | Piper | local | BLOCKED — no Tamil Piper voice bundled; set `JARVIS_TTS_MODEL_TA` to one you provide |
| English / Spanish speech output | Piper (`en_GB-northern_english_male-medium`, `es_MX-claude-high`) | local | existing; models verified by SHA-256 |

`GET /api/language` returns `local_tts_native` per language so the UI and you
can see when Tamil mode is using the English local voice.

## How replies choose a language

1. Session language (`en`, `es`, `ta`) from the header selector sets recognition language, local voice, and fixed messages.
2. Each typed or transcribed message is classified offline: Tamil script, Thanglish (≈150 marker words such as `pannu`, `sollu`, `irukku`, `enna`), Spanish, or English. Code spans, paths and URLs are ignored during detection.
3. The system prompt gets one `LANGUAGE POLICY` line: reply in Tamil script, in Thanglish, or in English, and never translate code, commands, file names, paths or app names.
4. `JARVIS_RESPONSE_LANGUAGE=en|ta|thanglish|es` pins the reply language.

Examples that are detected as Thanglish: `Notepad open pannu`, `laptop battery percentage sollu`,
`Downloads folder la irukkura PDF files list pannu`, `inniku weather eppadi irukku`.
English sentences such as `Open the file and close the window` stay English.

## Voice modes

| Mode | Status |
| --- | --- |
| Manual microphone button | existing |
| Text input fallback | existing |
| Gemini Live full duplex with barge-in | existing (needs `GEMINI_API_KEY`) |
| "Jarvis" wake phrase | existing, **browser speech recognition** — online in Chromium/WebView2, not an offline engine |
| Offline wake-word engine | NOT IMPLEMENTED (candidate: openWakeWord, Apache-2.0) |
| Stop voice | STOP button / `Ctrl+Shift+X` closes live sessions and playback; `Esc` interrupts speech |

Privacy: the microphone is off until you press the voice button. Audio is not
recorded to disk by default. Gemini Live and Groq Whisper send audio to the
provider; local faster-whisper does not.
