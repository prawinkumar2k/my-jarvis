# Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Setup: "required voice model files are missing" | No internet during Piper voice download | Reconnect and rerun `.\setup.ps1`, or run `.\venv\Scripts\python.exe -m piper.download_voices en_GB-northern_english_male-medium es_MX-claude-high --download-dir models --force-redownload` |
| Local voice is silent or garbled | `.onnx` files are LFS pointers (~130 bytes) | Same command as above. |
| Tamil mode speaks with an English voice / reads Tamil badly | No Tamil Piper voice is bundled | Use Gemini Live voice (needs `GEMINI_API_KEY`), or set `JARVIS_TTS_MODEL_TA`. |
| Tamil speech recognized poorly | Small Whisper model or browser engine | Set `JARVIS_WHISPER_MODEL=large-v3` (more RAM/CPU), or use Gemini Live. |
| Thanglish reply comes back in English | Message had too few Thanglish markers (e.g. one word) | Write a fuller sentence, or set `JARVIS_RESPONSE_LANGUAGE=thanglish`. |
| "File tools are disabled" | Mutating file tools are opt-in | `JARVIS_FILE_TOOLS_ENABLED=true` in `.env`, restart. |
| "That path is outside the folders JARVIS is allowed to use" | Path not under `JARVIS_FILE_WRITE_ROOTS` | Add the folder to that variable. |
| "Emergency stop is active" | STOP was pressed | Press **RESUME** or `Ctrl+Shift+X`. |
| 401/403 on API calls from another device | Critical routes need a token | Set `JARVIS_API_TOKEN` and send `X-JARVIS-API-TOKEN`. |
| `llm_unconfigured` | No AI key | Add `GEMINI_API_KEY` or `GROQ_API_KEY`. |
| pytest errors "could not create numbered dir" | Temp directory permissions on Windows | Run pytest from the project folder (uses repo-local `scratch/`). |
| `git lfs` smudge error on checkout | No LFS remote | `set GIT_LFS_SKIP_SMUDGE=1` before checkout; setup downloads voices instead. |
