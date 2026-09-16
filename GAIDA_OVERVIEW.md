# GAIDA — Plain-Language System Overview

**GAIDA =** **G**uidance system with multimodal Anx**I**ety Intelligence and **D**etection **A**ssistance

A virtual counseling assistant for University of the East students. It chats in Tagalog,
Taglish, and English, looks for signs of anxiety in both text and voice, brings in a human
counselor when things get serious, and keeps a record of the sessions you agreed to save. It
also works as an installable app that can run with no internet.

---

## What it actually does

| Feature | In plain terms |
|---|---|
| AI chat | A fine-tuned openAI model (based on GPT-3.5) replies warmly and copies whatever language the student used. |
| Text anxiety detection | Every message is sorted into a mood — neutral, stress, sadness, anxiety, anger, loneliness, academic, suicidal — using rules plus 3 small ML models that vote. |
| Voice anxiety detection | A recording is checked for signs of stress in the voice itself (pitch, shakiness, long pauses, speaking speed) and also typed out with Whisper. The two results are then combined with the text analysis. |
| Vent mode | A "just listen" mode — GAIDA doesn't try to fix or redirect. Real crisis warnings still break through for safety. |
| Crisis handling | If a student seems to be in crisis, GAIDA shares hotlines and automatically notifies a human counselor. |
| Counselor takeover | A counselor can jump into a live chat. GAIDA goes quiet, the human takes over, and control can be handed back to GAIDA later. |
| Counselor dashboard | Live alerts, active chats, transcripts, typing indicators, case notes, PDF exports, and analytics. |
| Consent | Students must agree to a consent screen before any of their chat data is saved. |
| Offline mode | Installable app; past chats can be viewed offline, and messages sent offline are queued and resent once the connection returns. |
| Post-chat check-in | After a session, students rate how they feel (1–4), which counselors can review. |

---

## How it's built — the big picture

1. **The Browser (what students and counselors see).** A React web app with a portal
   selector, student login, consent screen, student chat, and the counselor dashboard. A
   background "service worker" caches pages and data for offline use.
2. **The Backend (the brains).** A Python server (FastAPI) that:
   - talks to the frontend over simple web requests, and streams replies as they are typed,
   - runs all the anxiety-detection logic,
   - calls openAI for the chat replies and for voice transcription,
   - can speak replies aloud (gTTS), though this isn't switched on in the chat yet,
   - saves everything worth keeping into a database.
3. **Storage and outside services.**
   - **Supabase** (a hosted database) permanently stores sessions, chat history, consent
     records, alerts, notes, ratings, and voice-analysis logs.
   - **openAI** powers the chat replies (a fine-tuned model) and voice-to-text (Whisper).
   - **gTTS (Google)** can turn text replies into spoken audio.

> ⚠️ **Good to know:** a lot of *live* information — who is currently chatting, login
> tokens, and rate limits — is kept only in the server's short-term memory, not the
> database. If the server restarts, that all resets: active chats close and everyone is
> logged out. Only the permanent records (chat history, consent, notes) live safely in
> Supabase.

---

## What it's built with

**Backend (Python)**
- FastAPI + Uvicorn — the web server
- scikit-learn — the 3 small ML models that guess the mood of a message
- openAI — chat replies (fine-tuned GPT-3.5) and voice transcription (Whisper)
- librosa + numpy (+ OpenSmile) — pull stress signals out of raw audio (pitch, shakiness,
  pauses, speaking rate)
- gTTS — text-to-speech
- Supabase — the database
- reportlab — builds PDF session reports

**Frontend (React)**
- React 19 + Vite + Tailwind CSS
- react-router-dom — page navigation
- react-markdown — displays GAIDA's replies nicely
- recharts — charts on the counselor dashboard
- vite-plugin-pwa — makes it installable and offline-capable

**Hosting**
- Backend → Render
- Frontend → deployed as a website/PWA (hosting provider not set in the code)
- Database → Supabase (cloud Postgres)

---

## A student's journey, step by step

1. **Pick a portal** — Student or Counselor.
2. **Log in** — student number, @ue.edu.ph email, access code, and a simple on-screen
   CAPTCHA. The backend checks the credentials and hands back a login token that lasts
   12 hours.
3. **Give consent** — must be accepted before any chat data is saved.
4. **Chat** — every message the student sends is analyzed for mood and severity, and GAIDA
   replies. The app quietly checks every 3 seconds to see whether a human counselor has
   joined.
5. **A counselor gets involved two ways:**
   - automatically, when the system detects a High or Crisis situation, or
   - on request, when the student taps "Talk to a Counselor."
   Once a counselor takes over, GAIDA stops replying until control is handed back.
6. **Ending the session** — the student rates how they feel (1–4), and the session closes.

---

## How GAIDA "reads" a message

This is the heart of the system and runs on every single message, in this order:

1. **Crisis keywords, first.** A list of dozens of English and Filipino phrases — both
   direct ("i want to kill myself", "gusto ko na mamatay") and indirect ("no point in
   living", "suko na ako sa buhay"). Any match is treated as crisis instantly, and it
   overrides everything else — so a real crisis phrase is never hidden, even inside a
   venting message.
2. **"Normal venting" check.** Common study-frustration lines ("ayoko na mag-aral", "pagod
   na ako sa school") are marked as harmless. Safety detail: the crisis check above runs
   first, so this mask can only calm things down, never hide a real emergency. Soft
   "give-up" phrases like "ayoko na ng lahat" are only treated as stress when they are
   clearly about school or work.
3. **Machine learning vote.** Three small models vote on the mood. If they agree well, that
   wins. If they're unsure, the system falls through to the rules below. If the models say
   "suicidal" but no explicit crisis phrase was typed, the context checks in step 5 run
   again before anything is alerted.
4. **Keyword rule engine (backup).** A second system scores the message against weighted
   keywords in English and Filipino and picks the strongest mood.
5. **Context correction.** The guess is softened when the message is a joke, about a movie
   or story, in the past tense, about someone else, or hypothetical ("what if"). A
   hypothetical suicide still triggers a High alert, but not the full Crisis response.
6. **Remembering the conversation.** GAIDA tracks the trend: calming words ("okay na ako",
   "salamat") ease the detected level back down, repeated distress pushes it up, and the
   level never suddenly drops without a reason. A genuine crisis always overrides this.
7. **Severity label.** The final score becomes one label: **Normal, Low, Moderate, High, or
   Crisis**.
8. **Voice fusion (if voice was used).** The voice reading is combined with the text
   reading, and a higher reading can bump the overall level up.
9. **GAIDA replies.** GPT responds using a script matched to the severity — e.g., a Crisis
   reply always includes hotline numbers. GAIDA is also told never to repeat itself or ask
   the same question twice, so the conversation keeps moving forward. (Hotline numbers used:
   1553 and (02) 893-7603.)
10. **Alert + save.** High/Crisis messages notify the counselor dashboard, and (only if
    consent was given) the interaction is saved to the database.

---

## Voice handling

1. **Recording → analysis.** The audio is converted to a standard format (ffmpeg), then
   examined for pitch changes, a shaky voice (jitter/shimmer), pauses, and speaking rate —
   the usual signs of stress.
2. **Recording → text.** The same audio is transcribed with openAI's Whisper model.
3. **Result.** An estimated stress level from voice alone that later merges with the
   text-based detection (step 8 above).
4. **Text-to-speech.** Available (via gTTS) but not used automatically in the current chat —
   it's ready for future use.

---

## What gets stored, and where

**Permanent (Supabase):**
- sessions, chat messages, consent records, counselor alerts, session notes, wellbeing
  ratings, and voice-analysis logs.

**Temporary (server memory only, lost on restart):**
- which sessions are currently active, login tokens, typing indicators, and rate-limit
  counters.

(One quirk worth knowing: two parts of the code label saved sessions slightly differently
— as `session_id` vs `session_token` — which can occasionally make a saved session hard to
look up.)

---

## Frontend pages

| Page | What happens there |
|---|---|
| Portal selection | Choose Student or Counselor. |
| Student login | Credentials + CAPTCHA. |
| Counselor login | Separate login — currently just hard-coded test credentials, not a real account system. |
| Forgot password | Show-only — it doesn't actually send a reset email; it always shows a success message so no one can guess valid emails. |
| Consent | Must be accepted before chatting. |
| Student dashboard | The chat itself, plus voice input, vent mode, and a color theme picker. |
| Counselor dashboard | Alerts, live sessions, case notes, PDF export, analytics, and an archive of resolved cases. |

---

## Offline support

- The app caches its core pages so it still opens without internet.
- Recent chats and alerts are cached so students/counselors can view them offline.
- Messages sent while offline are queued on the device and automatically resent when the
  connection returns, with a visible "sending queued messages" notice.
- One catch: if a login token expires while offline, queued messages will fail to resend
  until the person logs in again.
- Developer note: offline caching/queueing is turned off when the app runs on localhost —
  it engages when the app is served from a real web location.

---

## Machine learning and training

- The mood-detection models are trained on a labeled dataset of example phrases
  (`anxiety_training.jsonl`).
- Three model types (Logistic Regression, Random Forest, Neural Network) are trained; they
  vote and the majority wins.
- GAIDA's chat replies come from a separately fine-tuned GPT-3.5 model trained on example
  conversations.

---

## Honest limitations (things worth knowing)

**Security**
- Only the main chat endpoints require login. The counselor dashboard, voice, and session
  APIs currently have no authentication — anyone with the link could view them.
- Counselor login is just hard-coded test credentials in the frontend, not a real account
  system.
- The "Sign in with UE Gmail" buttons do not actually sign anyone in yet.
- The login CAPTCHA is checked in the browser only.

**Reliability**
- Everything assumes a single server instance — it isn't built to run across multiple
  servers yet.
- Live login sessions and alerts live only in server memory, so a restart logs everyone out
  and clears active sessions.
- Looking up resolved cases currently makes one database query per case, which will slow
  down as data grows.
- There's a slight naming mismatch between two parts of the code for saved sessions (see
  above), which can occasionally cause a session to not be found.

**Cost / models**
- The fine-tuned chat model is built on a GPT-3.5 lineage openAI is phasing out; it will
  eventually need to be re-trained on a newer model.
- The voice-transcription model (Whisper "medium") is fairly heavy, so the first voice
  message after a restart is slow.

**Rough edges**
- Some charts on the counselor dashboard fall back to sample data when there's nothing real
  to show yet.
- "Forgot password" doesn't send real emails (this is intentional, to avoid revealing which
  emails are registered).
- Consent status and the live chat can occasionally get slightly out of sync.

**Not yet built**
- No knowledge-base lookup (RAG) — GAIDA only uses its prompt and the last few messages.
- No live WebSocket updates on the frontend — it currently polls every few seconds.
- No formal database migration scripts — the database structure is assumed to already exist.

---

## Quick start (for developers)

**Backend**
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
# set OPENAI_API_KEY, SUPABASE_URL, SUPABASE_KEY in backend/.env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

**Trying it out**
1. Go to http://localhost:5173 → Student Portal.
2. Log in with student number `2024001`, email `student1@ue.edu.ph`, code `ACCESS123`.
3. Accept consent, then chat with GAIDA.
4. Try something like "I can't breathe, my chest is tight" — it should trigger High severity
   and a counselor alert.
5. Open the Counselor Portal in another tab (`counselor01` / `counsel123`), check Alerts,
   and take over the session.