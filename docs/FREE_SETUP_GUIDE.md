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
**If a bot token ever appears in a chat or screenshot, treat it as leaked:** in BotFather send `/revoke`, pick the bot, and use the new token (only in `.env`).

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

## 4. Gmail without Google Cloud (app password, free)
JARVIS reads unread mail and sends mail over Gmail's normal IMAP/SMTP, so no Google Cloud project or OAuth
client is needed.
1. Turn on 2-Step Verification: myaccount.google.com, Security.
2. Security, 2-Step Verification, App passwords: create one named "JARVIS" (16 letters).
3. Put these in `.env` yourself (never paste them in a chat): `JARVIS_MAIL_ADDRESS=you@gmail.com`,
   `JARVIS_MAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx`. Ports: IMAP `imap.gmail.com:993` (SSL), SMTP
   `smtp.gmail.com:587` (STARTTLS); they are the defaults, change `JARVIS_MAIL_SMTP_PORT=465` for SSL.
4. Restart JARVIS. Say "any new emails?" (reads unread mail read-only, nothing is marked as read) or
   "send an email to ... saying ..." (JARVIS shows the exact message and recipient and asks every time).
Email text is treated as untrusted quoted content, never as instructions. Google Calendar still needs the
OAuth route (not built).

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

## Your first two recordings (checked 2026-10-27)
`WhatsApp Audio ... 10.09.36 PM.mp4` (13 s) and `...10.09.37 PM.mp4` (15 s) are both **English** (Indian accent).
The offline `small` model with automatic language detection (`JARVIS_STT_LANGUAGE=auto`) heard them clearly;
forcing Tamil (`ta`) on English speech gives nonsense, which is expected. They are git-ignored (voice data is
never committed). No Tamil or Thanglish sample exists yet, so Tamil accuracy is still unmeasured.
