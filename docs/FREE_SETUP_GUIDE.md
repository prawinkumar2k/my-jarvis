# Free setup guide (no payment needed)

Everything below costs nothing. Never paste tokens or secrets into a chat, an issue or a commit; they only
go into your local `.env` (git-ignored) or a file path you tell JARVIS about.

## 1. Natural voice: done, nothing to collect
JARVIS now speaks with free Microsoft Edge neural voices: Tamil `ta-IN-PallaviNeural` and Indian English
`en-IN-NeerjaNeural` (reads Thanglish well). No key, no account. Order: Gemini voice (when it has quota),
then this, then the offline Piper voice. Needs `pip install edge-tts` (already in `requirements-optional.txt`)
and FFmpeg. It is off in `local_only` mode (the text goes to Microsoft). Other voices: set
`JARVIS_EDGE_TTS_VOICE` / `JARVIS_EDGE_TTS_VOICE_TA` (for example `ta-IN-ValluvarNeural`, a male Tamil voice).
The service is unofficial; if it ever stops, JARVIS falls back to Piper by itself.

## 2. Telegram: free
1. In Telegram search `@BotFather`, send `/newbot`, choose a name, copy the token it gives you.
2. Open your new bot, press Start and send "hi".
3. In a browser open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`; find `"chat":{"id":123456789`.
4. Put them in `.env` yourself (do not send them to anyone): `TELEGRAM_TOKEN=...`, `TELEGRAM_CHAT_ID=123456789`,
   `JARVIS_TELEGRAM_ENABLED=true`, and set `JARVIS_CORE_MODE=false` (Telegram is skipped in core mode).
5. Restart JARVIS. Only your chat ID is allowed to talk to it.

## 3. Spotify: no payment needed for the desktop route
- **Free Spotify account:** the Spotify web API refuses playback control without Premium, so use the desktop
  route: install the Spotify app for Windows and sign in. `SPOTIFY_PLAYBACK_MODE=auto` already falls back to
  controlling the desktop app (no credentials needed).
- **Premium (only if you have it):** create a free app at developer.spotify.com/dashboard, set the redirect
  to exactly `http://127.0.0.1:8888/callback`, and put `SPOTIPY_CLIENT_ID` / `SPOTIPY_CLIENT_SECRET` in `.env`.

## 4. Gmail and Google Calendar: free
Google Cloud has a free tier and these two APIs cost nothing at personal use. No card is needed.
1. console.cloud.google.com, create a project (for example "jarvis").
2. APIs and Services, Library: enable "Gmail API" and "Google Calendar API".
3. OAuth consent screen: User type External, app name "JARVIS", add your own Gmail as a Test user.
4. Credentials, Create credentials, OAuth client ID, type **Desktop app**, then Download JSON.
5. Save that file as `C:\Users\prawi\Documents\jarvis-google-credentials.json` (anywhere outside the repo)
   and tell me the path (not the contents). I will build read-only Gmail/Calendar on it; the first run opens
   your browser once for you to sign in and allow. Sending mail or changing events will always ask you first.

## 5. Tamil / Thanglish speech accuracy: record yourself
Speech recognition accuracy can only be measured on your real voice. Record these on your normal mic:
1. Make a folder `C:\Users\prawi\Documents\jarvis-stt`.
2. Read each line below out loud, one recording per line, in the Windows "Sound Recorder" app, and save as
   `01.wav`, `02.wav`, ... (WAV or M4A both work).
3. Make `manifest.csv` in the same folder with the header `file,language,kind,reference` and one row per
   recording, `reference` being exactly what you said.
4. Run `venv\Scripts\python.exe scripts\evaluate_stt.py C:\Users\prawi\Documents\jarvis-stt` and share the
   printed summary (it does not contain secrets).

Lines to read (mix of quiet room and with fan or music on):
- Tamil (`ta`, kind `tamil`): "இப்போது நேரம் என்ன", "நாளைக்கு காலை ஏழு மணிக்கு அலாரம் வை", "என் பேட்டரி எவ்வளவு இருக்கு", "ஸ்பாட்டிஃபையில் ஒரு பாட்டு போடு"
- Thanglish (`en`, kind `thanglish`): "jarvis ippo time enna", "naalaiku kaalai ezhu mani ku alarm vai", "en battery evlo irukku", "oru paatu podu"
- English (`en`, kind `english`): "what time is it", "set a timer for five minutes", "open notepad", "what is the weather in Chennai"
