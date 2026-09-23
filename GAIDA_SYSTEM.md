# GAIDA System — Complete Documentation

> **GAIDA** = **G**uidance system with multimodal **A**nxiety **I**ntelligence and **D**etection **A**ssistance
>
> A virtual counseling assistant for University of the East students. Students chat with an AI
> ("GAIDA") that listens in **Tagalog, Taglish, and English**, detects anxiety from both **text and
> voice**, escalates **High/Crisis** cases to a human counselor, and records each session for the
> guidance office to review. It works offline as an installable PWA.

This document explains the whole system in plain language: what it does, how it's built, how data
flows through it, and where the interesting/risky parts are.

---

## Table of Contents

1. [What the system does](#1-what-the-system-does)
2. [High-level architecture](#2-high-level-architecture)
3. [Technology stack](#3-technology-stack)
4. [Repository layout](#4-repository-layout)
5. [End-to-end: a student's journey](#5-end-to-end-a-students-journey)
6. [Backend deep dive](#6-backend-deep-dive)
7. [The brain: intent detection pipeline](#7-the-brain-intent-detection-pipeline)
8. [Voice: transcription, acoustics, and speech output](#8-voice-transcription-acoustics-and-speech-output)
9. [Data layer](#9-data-layer)
10. [Frontend deep dive](#10-frontend-deep-dive)
11. [Offline / PWA behavior](#11-offline--pwa-behavior)
12. [Machine learning & training](#12-machine-learning--training)
13. [Deployment](#13-deployment)
14. [Testing](#14-testing)
15. [Environment variables & credentials](#15-environment-variables--credentials)
16. [Known limitations & things to know](#16-known-limitations--things-to-know)
17. [Quick start](#17-quick-start)

---

## 1. What the system does

| Feature | Description |
|---|---|
| **AI chat support** | Students talk to a fine-tuned GPT model that responds warmly and empathetically, matching the student's language (English/Tagalog/Taglish). |
| **Anxiety detection (text)** | Every message is classified into an intent (`neutral`, `stress`, `sadness`, `anxiety`, `anger`, `loneliness`, `academic`, `suicidal`) using a **rule engine + 3 machine-learning models**. |
| **Anxiety detection (voice)** | Voice recordings are analyzed for **acoustic stress markers** (pitch variance, jitter, shimmer, pauses, speech rate) and transcribed to text with Whisper. Acoustic findings are fused with text findings. |
| **Vent mode** | A "just listen, no advice" mode where GAIDA holds space without redirecting or fixing. Crisis detection still overrides it for safety. |
| **Crisis handling** | If the student is in crisis, GAIDA shares hotlines and **automatically alerts a human counselor**. |
| **Counselor takeover** | A counselor can take over a live session. The AI stops responding and the human takes the wheel; control can be handed back to GAIDA. |
| **Counselor dashboard** | Live alerts, active sessions, chat transcripts, typing indicators, case notes, PDF export, analytics, and resolved-case archive. |
| **Informed consent** | Students must accept an informed-consent form before their data is recorded/persisted. |
| **Offline PWA** | Installable app; past chats are readable offline and messages sent offline are queued and replayed when back online. |
| **Post-session rating** | Students rate how they feel after the session (1–4), stored for counselor review. |

---

## 2. High-level architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         BROWSER (Frontend)                       │
│                                                                  │
│  React 19 + Vite + Tailwind  →  single-page app                 │
│  Routes:  /  /student-login  /counselor-login  /forgot-password  │
│           /consent  /student-dashboard  /counselor-dashboard     │
│  PWA service worker (sw.js)  →  offline cache + message queue    │
└──────────────┬──────────────────────────────┬───────────────────┘
               │  HTTP (JSON)                 │  HTTP (JSON)
               ▼                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                  FastAPI BACKEND  (Python)                      │
│                                                                  │
│  Routers:                                                       │
│   /api/auth/*        login, consent, forgot-password            │
│   /virtual-agent     MAIN student chat + analysis endpoint       │
│   /api/session/*     session start/message/ws/end               │
│   /api/counselor/*   alerts, takeover, notes, PDF, analytics    │
│   /audio/*           speech-to-text, acoustics, tts             │
│                                                                  │
│  Services:                                                      │
│   intent_router → virtual_agent → ml_classifier + rule_intent   │
│               └──→ gpt_agent (OpenAI)                          │
│   session_manager, rate_limiter, tts, acoustic_features          │
│                                                                  │
│  Auth:  utils/auth.py  (in-memory bearer tokens)                │
└──────┬──────────────────────────┬───────────────────────────────┘
       │                          │
       ▼                          ▼
┌──────────────────┐   ┌─────────────────────────────────────────┐
│    SUPABASE      │   │         EXTERNAL SERVICES               │
│  (PostgreSQL)    │   │  OpenAI GPT (fine-tuned gpt-3.5-turbo)  │
│                  │   │  OpenAI Whisper (speech-to-text, medium)│
│  sessions        │   │  gTTS (text-to-speech, Google)          │
│  interactions    │   │  ffmpeg (audio→WAV conversion)          │
│  consents        │   │                                         │
│  counselor_alerts│   │                                         │
│  session_notes   │   │                                         │
│  session_ratings │   │                                         │
│  acoustic_logs   │   │                                         │
└──────────────────┘   └─────────────────────────────────────────┘
```

**One important thing to understand:** a lot of "live" state lives **in the backend's memory**
(Python dicts), not in the database. Supabase is used for durable records (history, notes, alerts,
consent). This works for a single server instance but means everything resets on a restart. See
[§16 Known limitations](#16-known-limitations--things-to-know).

---

## 3. Technology stack

### Backend (`backend/`)
- **FastAPI** — web framework (auto docs at `/docs`), CORS, security headers.
- **Uvicorn** — ASGI server.
- **scikit-learn** — 3 ML intent classifiers (Logistic Regression, Random Forest, Neural Network) trained on `anxiety_training.jsonl`, loaded from pickled pipelines.
- **openai-whisper** — `medium` model, lazy-loaded on the first voice request, converts speech → text.
- **librosa + numpy** — acoustic feature extraction (pitch, jitter, shimmer, pauses, energy, MFCCs).
- **openai** — calls the fine-tuned chat model.
- **gtts** — Google text-to-speech (returns MP3 bytes).
- **supabase** — Postgres client for all persistence.
- **reportlab** — generates the session PDF report.
- **python-multipart, python-dotenv, pytest, httpx** — file uploads, env vars, tests.
- **opensmile / pyaudio / speechrecognition** — installed (listed in `backend/README.md`) but not actively used by app code.

### Frontend (`frontend/`)
- **React 19** + **Vite 7** + **Tailwind CSS 3**.
- **react-router-dom 7** — routing.
- **react-markdown** — renders GAIDA's responses.
- **recharts** — counselor dashboard charts.
- **vite-plugin-pwa** — service worker + PWA support.

### Services / infra
- **Supabase** (hosted Postgres) — storage.
- **Replit** — hosts the backend via `.replit` (Deployments from Git; pushing to `main` auto-deploys). `render.yaml` is a legacy leftover from the Render era and is **not used**.
- **OpenAI API** — GPT model + Whisper transcription.
- **gTTS (Google Translate TTS)** — spoken replies.

---

## 4. Repository layout

```
gaida-system/
├── README.md                     # default Vite template readme (not customized)
├── requirements.txt              # full pip-freeze dump (backup copy)
├── render.yaml                   # Legacy Render deploy config (unused — backend is on Replit)
├── GAIDA_SYSTEM.md               # ← this document
│
├── backend/
│   ├── README.md                 # short note about audio libraries + run command
│   ├── requirements.txt          # actual runtime deps
│   ├── app/
│   │   ├── main.py               # FastAPI app entry, startup prewarm, /virtual-agent
│   │   ├── constants.py          # TEST_CREDENTIALS (student/counselor accounts)
│   │   ├── api/
│   │   │   ├── auth.py           # /api/auth/login, /consent, /forgot-password
│   │   │   ├── session.py        # /api/session/* + websocket
│   │   │   ├── counselor.py      # /api/counselor/*  (alerts, takeover, PDF, ...)
│   │   │   ├── voice.py          # /audio/speech-to-text, /tts, /analyze
│   │   │   └── schemas.py        # EMPTY file (dead code)
│   │   ├── services/
│   │   │   ├── intent_router.py  # orchestrates a full chat turn (the "brain")
│   │   │   ├── virtual_agent.py  # keyword/fuzzy crisis detection + severity mapping
│   │   │   ├── ml_classifier.py  # 3 sklearn models + majority vote
│   │   │   ├── rule_intent.py    # weighted keyword rule engine (fallback)
│   │   │   ├── gpt_agent.py      # builds prompts, calls OpenAI
│   │   │   ├── session_manager.py# in-memory sessions + Supabase persistence
│   │   │   ├── rate_limiter.py   # 5 requests / 60 seconds per user
│   │   │   └── tts.py            # gTTS wrapper
│   │   ├── analytics/
│   │   │   └── acoustic_features.py  # librosa features, severity mapping, fusion
│   │   ├── utils/
│   │   │   ├── auth.py           # bearer-token store + get_current_user dependency
│   │   │   ├── consent_checker.py# has_consent / log_consent against Supabase
│   │   │   ├── logger.py         # logs to logs/interactions.json (respects consent)
│   │   │   └── config.py         # UNUSED (readme explains env is read inline)
│   │   └── database/
│   │       └── database.py       # Supabase client from env vars
│   ├── tests/
│   │   ├── test_services.py      # 3 unit/API tests (auth included)
│   │   └── test_detection.py     # 30-case intent/severity scenario script
│   ├── training/
│   │   ├── anxiety_training.jsonl# labeled training data (text→label)
│   │   ├── finetune.jsonl        # GPT fine-tuning conversation data
│   │   ├── models/               # pickled sklearn pipelines
│   │   │   ├── best_model.pkl / lr_model.pkl / rf_model.pkl / nn_model.pkl
│   │   ├── upload_file.py        # script to upload finetune data
│   │   └── check_status.py       # script to check fine-tune job status
│   └── logs/
│       └── interactions.json     # local interaction log (consent-gated)
│
└── frontend/
    ├── package.json
    ├── vite.config.js            # PWA plugin + dev proxy to :8000
    ├── index.html
    └── src/
        ├── main.jsx              # React root
        ├── App.jsx               # router + PWABanner
        ├── config.js             # BACKEND_URL (VITE_BACKEND_URL || localhost:8000)
        ├── sw.js                 # service worker (cache + offline queue)
        ├── index.css
        ├── hooks/usePWA.js       # PWA hook (install, online/offline, queue sync)
        ├── components/PWABanner.jsx
        └── features/
            ├── auth/             # PortalSelection, CounselorLogin, InformedConsent,
            │                     # ForgotPassword
            ├── student/          # StudentLogin, StudentDashboard
            ├── counselor/        # CounselorDashboard
            └── voice/VoiceInput.jsx  # mic recording + Web Speech preview
```

---

## 5. End-to-end: a student's journey

```
Portal selection → Student Login → Consent → Chat with GAIDA → (crisis?) → Counselor takes over → End session → Rating
```

1. **Portal selection** (`/`): user picks Student or Counselor portal.
2. **Login** (`/student-login`): enter student number, `@ue.edu.ph` email, access code, and a
   CAPTCHA. Frontend sends `POST /api/auth/login`. Backend validates the email domain and the
   credentials, then returns a **bearer session token** (12-hour TTL). The frontend saves it to
   `localStorage`.
3. **Consent** (`/consent`): the student must check the consent box. Accepting sends
   `POST /api/auth/consent` which records consent in Supabase. Consent is required for the chat
   session to persist data.
4. **Chat** (`/student-dashboard`): the student types or speaks. Each message goes to
   `POST /virtual-agent` with `Authorization: Bearer <token>`.
   - Backend detects intent & severity, fires a counselor alert if needed, generates GAIDA's reply.
   - The dashboard polls `GET /api/counselor/chat/<session_id>` every 3 seconds to see if a
     counselor joined, is typing, or took over.
5. **Counselor involvement**:
   - **Automatic**: High/Crisis messages create a pending alert the counselor sees within ~2 seconds.
   - **On request**: student presses "Talk to a Counselor", calling
     `POST /api/counselor/request-counselor`.
   - The counselor opens the chat, sends messages via `POST /api/counselor/takeover` (which flips
     `counselor_active` so GAIDA stops replying), and can `POST /api/counselor/return-to-gaida`
     to hand control back.
6. **End session**: student presses "End Session", rates their wellbeing (1–4) → stored in
   `session_ratings`, then session is closed and local storage cleared.

---

## 6. Backend deep dive

### 6.1 App entry — `backend/app/main.py`

- Creates the `FastAPI` app and mounts 4 routers:
  - `auth.router` (`/api/auth`)
  - `audio_router` (`/audio`)
  - `counselor_router` (`/api/counselor`)
  - `session_router` (`/api/session`)
- **Startup prewarm** (`@app.on_event("startup")`):
  1. Loads the ML models so the first chat isn't slow (`_load_all_models()`).
  2. Warms the Supabase connection with a tiny `sessions` query.
  - If either fails, it logs and continues (startup still succeeds).
- **CORS**: allows `http://localhost:5173`, `http://localhost:3000`, and `https://gaida-system.vercel.app`.
- **Security headers middleware**: adds `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`.
- **Root**: `GET /` → `{"status": "ok", "message": "GAIDA Backend"}`.

### 6.2 The main endpoint — `POST /virtual-agent`

This is the heart of the system. Pydantic body model:

```python
class UserInput(BaseModel):
    message: str            # the student's text
    session_id: str | None  # existing session, or None to create one
    user_id: str | None     # ignored now — identity comes from the token
    intent: str | None      # frontend hint (usually "unknown" or "venting")
    vent_mode: bool = False # listen-only mode
```

Processing steps in `main.py:118`:

1. **Authenticate** via `Depends(get_current_user)` → 401 if the bearer token is missing/invalid.
2. **Rate limit** — `check_rate_limit(user["user_id"])` → 429 after 5 requests in 60s.
3. **Session ownership check** — if `session_id` is passed, verify the session belongs to the
   authenticated user; otherwise 403. (This prevents users reading another user's session.)
4. **`analyze_intent(...)`** — the full detection+response pipeline (see §7).
5. **Response shape**:
   - If a counselor is active: `{session_id, counselor_active: True, response: null}`.
   - Otherwise: `{session_id, intent, confidence, anxiety_level, severity, anxiety_score,
     response, method}`.

### 6.3 Authentication — `backend/app/utils/auth.py`

Simple but real bearer-token auth:

- **Token store**: in-memory dict `ACTIVE_TOKENS = { token: {user_id, role, expires_at} }`.
- **`create_session_token(user_id, role)`** → `token_<role>_<16 random bytes>` with a
  **12-hour TTL**.
- **`get_current_user`** — FastAPI dependency that:
  1. Requires an `Authorization: Bearer <token>` header (401 otherwise).
  2. Purges expired tokens.
  3. Returns the user dict or raises 401.

> ⚠️ **In-memory only.** Tokens vanish on server restart, so users must log in again. This matches
> the rest of the in-memory session state and is acceptable for the current single-instance deploy,
> but is not horizontally scalable.

Currently **only `/virtual-agent` is protected**. The `/api/counselor/*`, `/audio/*`, and
`/api/session/*` routes are open (see §16).

### 6.4 Auth API — `backend/app/api/auth.py`

| Endpoint | Body | What it does |
|---|---|---|
| `POST /api/auth/login` | `{student_number, email, access_code, antibot}` | Validates email ends with `@ue.edu.ph`, looks up `TEST_CREDENTIALS`, issues a token via `create_session_token(student_number, "student")`. Rate-limited by student number. |
| `POST /api/auth/consent` | `{session_id, consent_given}` | Upserts a row in the `consents` table (insert or update). |
| `POST /api/auth/forgot-password` | `{email, role}` | Always returns `{"ok": true, ...}` (never reveals whether an email exists — prevents enumeration). It does **not** actually send an email. |

### 6.5 Session API — `backend/app/api/session.py`

| Endpoint | Purpose |
|---|---|
| `POST /api/session/start` | Creates a session (in-memory + Supabase row). |
| `POST /api/session/message` | Records a message; runs the lightweight `analyze_with_rules` when `sender == "user"`. |
| `GET /api/session/{session_id}` | Returns the full in-memory session state. |
| `GET /api/session/active` | Lists active (non-stale) sessions. |
| `POST /api/session/{session_id}/end` | Marks a session ended, persists peak severity. |
| `WS /api/session/ws/{session_id}` | WebSocket for live message broadcasting. **Note:** the current frontend doesn't use this — it polls instead. The broadcast subscriber is registered at module import. |

### 6.6 Session manager — `backend/app/services/session_manager.py`

The source of truth for live conversation state.

- **`SESSIONS`** — `{session_id: {session_id, user_id, started_at, messages[], active, meta}}`.
- `meta` tracks: `running_confidence` (starts 0.3), `running_intent` (starts `neutral`),
  `peak_severity`, `peak_confidence`, `post_crisis`, `counselor_active`, `assigned_counselor_id`,
  `pending_acoustic`, `covered_themes`.
- **`record_interaction(...)`**: appends to `session["messages"]`, updates running meta, and **only
  persists to Supabase if the session has consent** (`has_consent(session_id)`). Bot replies are
  recorded in memory but skipped when writing to the `interactions` table.
- **`list_active_sessions()`**: filters out ended sessions, empty sessions, and sessions idle for
  > **30 minutes** (`SESSION_STALE_MINUTES = 30`).
- **`subscribe(callback)`**: publish/subscribe — every new interaction notifies subscribers (used
  by the WebSocket broadcaster).
- **`end_session()`**: marks inactive and updates `ended_at` + `peak_severity` in Supabase.

### 6.7 Rate limiter — `backend/app/services/rate_limiter.py`

- Sliding window of **5 requests per 60 seconds** per key (user id / student number).
- Raises `HTTPException(429)` when exceeded. Pure in-memory.

### 6.8 Consent checker — `backend/app/utils/consent_checker.py`

- `has_consent(session_id)` → true only if a `consents` row exists with `consent_given = True`.
- `log_consent(...)` → upsert. Every write to Supabase (`interactions`) and to the local log file is
  gated behind consent.

---

## 7. The brain: intent detection pipeline

The pipeline lives in `intent_router.py` (`analyze_intent`) and is called on every `/virtual-agent`
request. Here's the exact flow:

```
Student message
      │
      ▼
1. Ensure a session exists (create if needed)
      │
      ▼
2. detect_intent_and_level(message)      ← virtual_agent.py
      │
      ├── a. SAFE PHRASE check  (e.g. "ayoko na mag aral") → hard "neutral" (0.3)
      ├── b. SUICIDAL KEYWORD check (EN + Tagalog, exact + fuzzy) → "suicidal" (0.99)
      ├── c. ML CLASSIFIER (3 models, majority vote) → intent + confidence
      │        └─ if ML says neutral → neutral (0.3)
      │        └─ if uncertain/low confidence → fall through
      ├── d. RULE ENGINE (weighted keywords) → intent + confidence
      │        └─ "suicidal" keyword → hard crisis
      │        └─ else scaled confidence = 0.3 + 0.7 × raw
      └── e. NEGATIVE-CONTEXT multiplier (movies, jokes, past tense, "my friend"…)
               discounts confidence so normal chatter isn't flagged
      │
      ▼
3. CRISIS BYPASS
   intent == "suicidal" or confidence ≥ 0.99  →  running_confidence = 0.99,
   session marks post_crisis = True
      │
      ▼
4. RUNNING CONFIDENCE smoothing (mood over time)
   • CALMING signals  (e.g. "salamat", "better", "okay na ako")
        → confidence drops toward 0.3  (faster if after a crisis)
   • REPEATED intent (same as previous, e.g. anxiety→anxiety)  → ×1.3 boost
   • RELATED intent  (anxiety ↔ stress ↔ sadness, etc.)        → ×1.15 boost
   • URGENT PHYSICAL (can't breathe, chest tight, panic attack) → floor 0.60
   • running = 0.7×history + 0.3×current  (never drops below half of previous)
   • INTENT PRIORITY lock: intent can only escalate in severity order:
        neutral < academic < loneliness < anger < stress < sadness < anxiety < suicidal
      (unless it's a calming message after a crisis)
      │
      ▼
5. MAP to anxiety level/severity         ← _build_result()
   confidence ≥ 0.99 → Crisis / Crisis   (score 5, crisis resources included)
   confidence ≥ 0.75 → high   / High     (score 5)
   confidence ≥ 0.60 → moderate / Moderate (score 3)
   confidence ≥ 0.45 → low    / Low      (score 1)
   else              → normal / Normal   (score 0)
      │
      ▼
6. ACOUSTIC FUSION (if voice was used)
   Takes the stored pending_acoustic severity (from voice analysis) and text severity;
   fused = max of the two, with a bump for sad/anxious voice. If higher → upgrade level.
      │
      ▼
7. COUNSELOR ACTIVE?  → skip GPT, return {counselor_active: True}
      │
      ▼
8. GENERATE RESPONSE via gpt_agent (anxiety-level guide + protocol + history)
   GPT unavailable → fallback text "I'm here with you. Can you tell me more…?"
      │
      ▼
9. FIRE ALERT if anxiety_level in (high, crisis)   → process_alert() in counselor.py
      │
      ▼
10. RECORD interaction (memory + Supabase if consent)
```

### 7.1 Virtual agent — `backend/app/services/virtual_agent.py`

The first line of defense. Order matters:

1. **`SAFE_PHRASES`** (hard neutral) — common *study frustration* phrases that must never trigger a
   crisis response: `"ayoko na mag aral"`, `"pagod na ako"`, `"tired of studying"`, etc.
2. **`KEYWORDS["suicidal"]`** — ~60 direct and indirect phrases in English and Filipino, each with a
   weight. Uses exact word-boundary regex **plus** fuzzy matching (`difflib.SequenceMatcher`) with a
   0.85 phrase / 0.82 token threshold. Any hit → **crisis (0.99)**.
3. **ML classifier** — see §7.2.
4. **Rule engine** — see §7.3.

**`_build_result(intent, confidence, post_crisis)`** converts confidence → anxiety level, severity,
anxiety score (0–5), and picks a **Counselor First-Aid Protocol** (`COUNSELOR_PROTOCOLS`: low /
moderate / high / crisis). The crisis protocol includes Philippine hotlines (1553, (02) 893-7603).

**`NEGATIVE_CONTEXTS`** regexes reduce confidence when the text is:
- past tense ("used to", "before", "dati", "noon")
- clearly positive ("better now", "okay na")
- negated ("not", "no longer", "hindi na")
- jokes/media ("lol", "haha", "movie", "anime", "character")
- about someone else ("my friend", "my classmate")
- hypothetical ("what if", "hypothetically")
- academic wins ("passed", "pumasa")

Each can multiply confidence down (×0.1–×0.4). This is a big false-positive shield.

### 7.2 ML classifier — `backend/app/services/ml_classifier.py`

- Trains **3 pipelines** on `training/anxiety_training.jsonl` (JSONL of `{text, label}`):
  1. **Logistic Regression** (`C=1.0`, `max_iter=1000`)
  2. **Random Forest** (200 trees)
  3. **Neural Network** (MLP, hidden `(256, 128, 64)`)
- All use `TfidfVectorizer` (unigrams+bigrams, max 5000 features, sublinear TF).
- Pickled to `training/models/{lr,rf,nn,best}_model.pkl`. `best_model` = highest test accuracy.
- **`_load_all_models()`** loads LR + RF at startup (fast). The NN loads lazily on first use.
- **`classify_intent(text)`**:
  1. Runs all 3 models.
  2. **Majority vote** wins; on a 3-way tie, Logistic Regression breaks the tie.
  3. Confidence = average probability of the agreeing models.
  4. If average confidence < **0.55** → returns `uncertain` (falls through to rule engine).
- **`classify_intent_all(text)`** — returns each model's prediction separately (useful for the
  counselor "Detection" comparisons).

### 7.3 Rule engine — `backend/app/services/rule_intent.py`

The deterministic fallback. Weighted keyword lists for `suicidal` (weight ~4), `anxiety` (~2),
`sadness` (~1.5–2.2), `stress` (~1.8–2.5), each in English + Tagalog/Taglish. Logic:

- Normalize (lowercase, collapse repeated letters like "soooo"→"so", strip punctuation).
- Remove Filipino stopwords.
- Score each intent by summing matched keyword weights (with fuzzy matching fallback).
- **Hard escalation**: any `suicidal` match → `{"intent": "suicidal", "confidence": 0.99,
  "escalate": True}` plus the escalation message.
- Otherwise confidence = best_score / total_score; intensity boosted by "intensifier" words
  ("sobrang", "grabe", "very", "absolutely", …).

### 7.4 GPT agent — `backend/app/services/gpt_agent.py`

Builds the OpenAI request with up to 4 layers of injected system context:

1. **`SYSTEM_PROMPT`** — GAIDA's personality: warm, never repeats itself, never diagnoses, matches
   the student's language, one question at a time.
2. **Anxiety-level guide** (`ANXIETY_VALIDATION_PROMPT`) — a per-level "response flow" template:
   - `none` → conversational check-in
   - `low` → validate → reflect → normalize → reframe → grounding question
   - `moderate` → stronger validation → interrupt overthinking loop → alternative explanation
   - `high` → calm urgency, physical grounding, no "objects you can't verify"
   - `crisis` → acknowledge pain first → validate without "but" → gently interrupt hopelessness →
     normalize help → crisis resources → end with presence (no question)
   - `venting` → only reflect, name emotion, validate without fixing, leave the door open
3. **Guard rails built from session history**:
   - **Repetition guard** — lists the opening phrases of the last responses, tells GPT not to reuse
     them.
   - **Closing-question guard** — lists question themes already asked this session
     (`meta.covered_themes`), forbids re-asking reworded versions.
   - **Progression rule** — forces the conversation forward (turn 2: don't re-validate; turn 3:
     reframe; turn 4+: offer coping/gently challenge).
4. **History** — last **6** messages (`MAX_HISTORY_MESSAGES`) injected as memory.

Settings:
- Model: `ft:gpt-3.5-turbo-0125:personal::DqH2I32e` (fine-tuned, **currently deprecated** — see §16).
- `temperature = 0.75`.
- `max_tokens` by anxiety level: none 100, low 130, moderate 150, high 110, crisis 100, venting 120.
- On any error (rate limit, connection, timeout) it returns `{"response": None, "used": False}` and
  the router falls back to a safe canned line.

---

## 8. Voice: transcription, acoustics, and speech output

Routes in `backend/app/api/voice.py`.

### 8.1 `POST /audio/speech-to-text`

Called by `VoiceInput.jsx` with an audio blob (webm/ogg) + optional `session_id`.

1. **Acoustic feature extraction** (non-fatal — continues on failure):
   - `extract_features()` in `acoustic_features.py` converts to WAV (ffmpeg — system PATH first,
     then a hard-coded CapCut ffmpeg fallback), then computes with librosa:
     - pitch mean/std (`pyin`), RMS energy, pause ratio, speech rate (onsets/sec), duration,
       jitter, shimmer, zero-crossing rate, spectral centroid/rolloff, and 13 MFCCs.
   - `_score_from_features` → **acoustic anxiety score 0–1** (weighted: pitch std 0.25, jitter
     0.25, shimmer 0.20, pauses 0.15, rate 0.15).
   - `_detect_emotion` → `anxious / sad / angry / calm / neutral` from simple thresholds.
   - `map_acoustic_to_severity`: ≥0.65 High, ≥0.35 Moderate, ≥0.15 Low, else Normal.
   - Logs the full feature set to the `acoustic_logs` Supabase table.
2. **Stash in session**: stores `pending_acoustic` on the session's `meta`, so the *next* text
   message gets fused with the acoustic verdict (see §7 step 6).
3. **Whisper transcription** — lazily loads the `medium` model (takes a while on first call), saves
   bytes to a temp `.webm` file, transcribes.
4. Returns `{transcript, session_id, acoustic: {...}}`. The transcript is dropped into the chat
   input box for the student to review/send.

### 8.2 `POST /audio/analyze`

Same acoustic extraction but standalone (no transcription). Logs to Supabase with session
`"analyze"`.

### 8.3 `GET /audio/tts?text=...`

Returns GAIDA's reply as **MP3 bytes** using `gTTS` (Google Translate TTS). (The current dashboard
doesn't call it automatically — it's available for future spoken replies.)

---

## 9. Data layer

### 9.1 Supabase tables (used by the code)

| Table | Writes come from | Key columns (as used in code) |
|---|---|---|
| `sessions` | `session_manager`, `api/session.py`, `counselor.py` (resolve) | `session_token`, `session_id`, `student_id`, `peak_severity`, `created_at`, `started_at`, `ended_at`, `resolved`, `resolved_at`, `resolved_by`, `is_counselor` |
| `interactions` | `session_manager._persist_entry` (consent-gated) | `session_id`, `student_id`, `message`, `response`, `timestamp`, `intent`, `confidence`, `anxiety_score`, `severity`, `method` |
| `consents` | `api/auth.py`, `consent_checker` | `session_id`, `consent_given`, `updated_at` |
| `counselor_alerts` | `counselor.py` (`process_alert`, request/resolve/delete) | `session_id`, `user_id`, `intent`, `anxiety_score`, `severity`, `message`, `status`, `created_at`, `resolved_at`, `deleted`, `deleted_at`, `deleted_by` |
| `session_notes` | `counselor.py` | `session_id`, `note`, `outcome`, `created_at` |
| `session_ratings` | `counselor.py` | `session_id`, `wellbeing_rating`, `severity_at_end`, `rated_at` |
| `acoustic_logs` | `acoustic_features.log_to_supabase` | `session_id`, timestamps, all acoustic features + `severity` |

> The schema is **not** defined in code (no migrations). The app assumes these tables exist with
> the right columns; a missing column/table surfaces as a caught exception (`print(...)`) rather
> than a crash.

### 9.2 In-memory state (backend process)

| Store | Where | Contents |
|---|---|---|
| `SESSIONS` | `session_manager.py` | All live sessions + full transcripts |
| `ALERTS` | `counselor.py` | Pending/escalated/resolved alerts |
| `TYPING_STATES` | `counselor.py` | per-session typing flags |
| `ACTIVE_TOKENS` | `utils/auth.py` | Auth tokens (12-hr TTL) |
| `users_requests` | `rate_limiter.py` | Rate-limit timestamps |

All of these reset when the process restarts (see §16).

### 9.3 Local log file

`backend/logs/interactions.json` — every user interaction is appended here **only if the session
has consent**. (It's a developer-oriented artifact; the source of truth is Supabase.)

---

## 10. Frontend deep dive

### 10.1 Routing (`App.jsx`)

| Path | Component | Notes |
|---|---|---|
| `/` | `PortalSelection` | Student vs Counselor portal chooser |
| `/student-login` | `StudentLogin` | email/access-code + CAPTCHA; stores `session_token`, `student_id` |
| `/counselor-login` | `CounselorLogin` | client-side check against hard-coded `counselor01/counsel123`; stores `'dev-token'` |
| `/forgot-password` | `ForgotPassword` | UI only (backend always says "reset link sent") |
| `/consent` | `InformedConsent` | must accept → `POST /api/auth/consent`, sets `consent_given` + `session_id` |
| `/student-dashboard` | `StudentDashboard` | the chat app |
| `/counselor-dashboard` | `CounselorDashboard` | alerts, sessions, takeover, reports |

`PWABanner` is rendered on every route (top, fixed).

### 10.2 Student dashboard (`StudentDashboard.jsx`, ~1000 lines)

Key behaviors:

- **Auth gate**: no `session_token` → redirect to login; no consent → redirect to consent.
- **Check-in prompt**: on mount it calls `GET /api/counselor/student/checkin/<student_id>`. If the
  last session peaked at High/Crisis, GAIDA greets with a follow-up check-in message.
- **Send message** (`sendMessage`):
  - Appends the user bubble optimistically.
  - `POST /virtual-agent` with `Authorization: Bearer <token>` (line 428), `session_id`,
    `user_id`, `vent_mode`.
  - On success stores `session_id` and severity, appends GAIDA's bubble (rendered with
    `react-markdown`).
- **Counselor polling** (every 3 s, `POLL_INTERVAL`): `GET /api/counselor/chat/<session_id>`.
  - Shows "A counselor has joined your session." when the first counselor message appears.
  - Shows a counselor typing bubble.
  - Detects handback ("GAIDA has resumed the conversation.") when `counselor_active` flips to false.
- **Typing indicators**: debounced 2 s `POST /api/counselor/typing/<session_id>`.
- **Vent mode toggle**: sets `vent_mode` in the request body; UI shows "GAIDA will just listen".
- **Voice input**: `VoiceInput` component records via `MediaRecorder`, shows a live transcript from
  the browser's Web Speech API (`lang="fil-PH"`), then sends the blob to
  `/audio/speech-to-text` and drops the transcript into the input box.
- **Themes**: 4 color themes (purple/navy/charcoal/forest) stored in `localStorage`.
- **End session**: wellbeing rating modal (1–4) → `POST /api/counselor/session/rate`, then
  `POST /api/session/<id>/end`, clear localStorage, navigate to login.
- **Offline sync**: listens for the `gaida:queue-synced` event (dispatched by `App.jsx` when the
  service worker flushes the offline queue) and appends the real bot reply.

### 10.3 Counselor dashboard (`CounselorDashboard.jsx`, ~1400 lines)

Six pages, switched by a collapsible sidebar (nav icons + labels), with an alert count badge:

1. **Overview** — cards for pending alerts / active sessions / resolved cases + a
   `recharts` line chart. **Note:** some chart data is hard-coded mock data (see §16).
2. **Alerts** — live list (polls every 2 s) of `GET /api/counselor/alerts`; pending-alert sound +
   browser notification when the pending count increases; status update via
   `POST /api/counselor/alerts/update`.
3. **Sessions** — active sessions from `GET /api/counselor/sessions/active` (severity derived from
   running confidence if not set), open chat in a modal.
4. **Detection** — per-message intent/severity details (uses chat data).
5. **Reports** — analytics (`GET /api/counselor/analytics/overview`): anxiety distribution,
   sessions this week, total sessions/alerts.
6. **Resolved** — archived cases (`GET /api/counselor/sessions/resolved`) with transcript, case
   note, outcome badge; actions: Export PDF (`GET /api/counselor/export-session/<id>`, opens in a
   new tab) and Delete (`POST /api/counselor/sessions/delete`, soft delete).

**Chat modal** (`ChatModal`): polls `GET /api/counselor/chat/<id>` for the transcript, shows
student/GAIDA/counselor bubbles with intent+confidence labels, sends counselor messages through
`POST /api/counselor/takeover` (sets `counselor_active` so GAIDA stops), and can hand control back
via `POST /api/counselor/return-to-gaida`. Also sets typing indicators and lets the counselor add a
session note (`POST /api/counselor/session-notes`) and resolve the case
(`POST /api/counselor/sessions/resolve`).

### 10.4 Counselor API (backend `counselor.py`) — full endpoint list

| Method & path | Purpose |
|---|---|
| `GET /api/counselor/alerts` | all in-memory alerts |
| `GET /api/counselor/alerts/pending` | only pending alerts |
| `POST /api/counselor/alerts/update` | set alert status (`pending/resolved/...`) |
| `POST /api/counselor/request-counselor` | student requests a counselor (creates alert) |
| `GET /api/counselor/severity/{score}` | map 0/1/3/5 → severity label + alert flag |
| `GET /api/counselor/sessions/active` | active sessions + derived severity + has_alert |
| `POST /api/counselor/sessions/resolve` | mark session resolved (memory + Supabase) |
| `GET /api/counselor/sessions/resolved` | archived cases w/ note + transcript (note: N+1 queries, see §16) |
| `POST /api/counselor/sessions/delete` | soft-delete a case |
| `GET /api/counselor/chat/{session_id}` | transcript + typing flags + counselor_active |
| `POST /api/counselor/typing/{session_id}` | set typing flag for counselor/student |
| `POST /api/counselor/takeover` | counselor takes over (blocks if assigned to another counselor) |
| `POST /api/counselor/return-to-gaida` | hand control back to GAIDA |
| `POST /api/counselor/session-notes` | add a note + outcome |
| `GET /api/counselor/session-notes/{session_id}` | list notes |
| `GET /api/counselor/student-profile/{student_id}` | profile from `TEST_CREDENTIALS` |
| `GET /api/counselor/student/checkin/{student_id}` | check-in prompt for past High/Crisis sessions |
| `POST /api/counselor/session/rate` | store post-session wellbeing rating |
| `GET /api/counselor/analytics/overview` | anxiety distribution / weekly sessions / totals |
| `GET /api/counselor/export-session/{session_id}` | PDF report (reportlab) |

**`process_alert(...)`** (called from `intent_router`): if severity is `High`, upserts an alert in
memory and inserts into `counselor_alerts`. **Important:** only severity `High` triggers an alert —
the `Crisis` severity also maps through `get_severity(5) = "High"`, so crisis sessions do alert.
(`SEVERITY_MAP = {0: Normal, 1: Low, 3: Moderate, 5: High}`.)

**PDF export**: builds a "GAIDA — Session Referral Report" with student info table, session
metadata, and a timestamped transcript with intent/confidence labels, using reportlab. Requires the
session row + interactions in Supabase.

---

## 11. Offline / PWA behavior

### 11.1 Service worker (`frontend/src/sw.js`)

Three caches/strategies:

1. **App shell** (`SHELL_CACHE`) — cache-first for `/`, `/index.html`, `/offline.html`, icons.
2. **API data** (`DATA_CACHE`) — network-first for `/api/session/`, `/api/counselor/chat/`,
   `/api/counselor/alerts`, `/api/counselor/student-profile/`. If offline, serves the cached copy.
3. **Offline message queue** (`QUEUE_STORE` IndexedDB) — for `POST /virtual-agent`,
   `/api/counselor/request-counselor`, `/api/counselor/takeover`, `/api/counselor/typing/`.
   - If online → pass through immediately.
   - If offline → save the request (including headers/body) to IndexedDB, return an optimistic
     "queued" response with a placeholder GAIDA message, and notify open tabs
     (`MESSAGE_QUEUED`).
   - On `sync` (background sync, or triggered by the `online` event) → replay each queued request;
     on success, remove it and broadcast `QUEUED_MESSAGE_SENT`.

> ⚠️ Queued `/virtual-agent` requests replay with the stored `Authorization` header, so they still
> authenticate — **but** if the 12-hour token expired while offline, the replay will get a 401 and
> stay queued.

### 11.2 `usePWA` hook + `PWABanner`

- Registers the service worker; triggers background sync on `online`.
- Tracks online/offline, install prompt (`beforeinstallprompt`), standalone mode.
- Banner shows: offline bar (with queued count), "sending N queued messages…" while flushing, and
  an install prompt.

---

## 12. Machine learning & training

- **Intent classifier data**: `backend/training/anxiety_training.jsonl` — one JSON object per line:
  `{"text": "I feel tense in my whole body", "label": "anxiety"}`. Labels seen in data include
  `anxiety`, `suicidal`, `anger`, and others.
- **Models**: `lr_model.pkl`, `rf_model.pkl`, `nn_model.pkl`, `best_model.pkl` (already trained and
  committed). To retrain: `python ml_classifier.py` (or the models auto-train if missing).
- **GPT fine-tune data**: `backend/training/finetune.jsonl` (conversation format for OpenAI
  fine-tuning). `upload_file.py` uploads it, `check_status.py` polls the job.
- The fine-tuned model ID is hard-coded in `gpt_agent.py`:
  `ft:gpt-3.5-turbo-0125:personal::DqH2I32e`.

---

## 13. Deployment

### Backend — Replit (Deployments from Git)

The backend runs on Replit from the repo root's `.replit` file:

```toml
[deployment]
run = ["sh", "-c", "cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
deploymentTarget = "cloudrun"
```

- **Flow:** any push to `main` triggers an automatic deployment — no manual "Republish" needed.
- **Modules:** `nodejs-20` (unused by backend), `python-3.12`, `web`.
- **Runtime arm:** 2 vCPU / 4 GiB (Replit free tier).
- **Live URL:** `https://gaida-system--rainierburlasa4.replit.app` — health check `GET /` →
  `{"status":"ok","message":"GAIDA Backend"}`.
- **Secrets:** `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `GOOGLE_CLIENT_ID` are set as
  Replit production secrets (backend refuses to boot without the Supabase pair).
- The old `render.yaml` is a legacy leftover and is not deployed anywhere.

### Frontend — Vercel

- Live at `https://gaida-system.vercel.app`. CORS in `main.py` whitelists this origin
  (plus `localhost:5173` / `localhost:3000`).
- Build with `npm run build` (vite). The PWA plugin injects the service worker.
- `VITE_BACKEND_URL` is baked to the Replit backend URL above during the build.
- The service worker still treats `127.0.0.1` and `*.onrender.com` hosts as network-first (bypass) —
  a leftover from the Render era that is harmless for the Vercel build.

### Environment variables needed

| Variable | Used by |
|---|---|
| `OPENAI_API_KEY` | `gpt_agent.py` (chat) + `voice.py` (Whisper) |
| `SUPABASE_URL`, `SUPABASE_KEY` | `database/database.py` |
| `GOOGLE_CLIENT_ID` | `api/auth.py` (Google @ue.edu.ph sign-in) |
| `VITE_BACKEND_URL` (frontend build) | `frontend/src/config.js` — defaults to `http://localhost:8000` |

---

## 14. Testing

### `backend/tests/test_services.py` (3 tests — run with `pytest`)

1. `test_rule_intent_basic` — rule engine returns sane intent + confidence bounds.
2. `test_virtual_agent_endpoint` — logs in for a real token, then calls `/virtual-agent` with the
   bearer header; expects 200 + `intent`/`confidence`/`response`.
3. `test_virtual_agent_requires_auth` — calling `/virtual-agent` without a token → 401.

### `backend/tests/test_detection.py` (scenario script — `python test_detection.py`)

Runs ~30 messages through `analyze_intent` and checks the expected severity bucket (Normal/Low/
Moderate/High/Crisis) and whether an alert should fire. Includes English + Filipino cases, safe
phrases, jokes, and past-tense contexts.

---

## 15. Environment variables & credentials

### Test accounts (`backend/app/constants.py`)

| ID | Email | Access code | Name | Program / Year |
|---|---|---|---|---|
| `2024001` | `student1@ue.edu.ph` | `ACCESS123` | Maria Santos | BS Psychology, 2 |
| `2024002` | `student2@ue.edu.ph` | `ACCESS456` | Juan dela Cruz | BS Computer Science, 3 |
| `2024003` | `student3@ue.edu.ph` | `ACCESS789` | Ana Reyes | BS Nursing, 1 |
| `COUNSELOR01` | `counselor01` | `counsel123` | Dr. Patricia Lim | — |

The counselor login (frontend) uses its own hard-coded copy: `counselor01` / `counsel123`.

- Email domain gate: must end in `@ue.edu.ph` (checked client- and server-side).
- CAPTCHA ("antibot") is generated and validated client-side only (canvas-drawn 6 chars).

---

## 16. Known limitations & things to know

**Security / auth**
- Only `/virtual-agent` requires a token. `/api/counselor/*`, `/audio/*`, and `/api/session/*`
  are **unauthenticated** — anyone can read alerts, sessions, transcripts, export PDFs, etc.
- Counselor login is **client-side only**: credentials are hard-coded in the JS bundle and the
  stored token is the literal string `dev-token`. Google "Sign in with UE Gmail" buttons on both
  login pages are **non-functional stubs**.
- Tokens, sessions, alerts, and rate-limit state are **in-memory**: restarting the backend logs
  everyone out and loses live sessions/alerts.

**Reliability / scale**
- Single-instance assumptions everywhere (in-memory state). Not safe across multiple workers.
- `get_resolved_sessions` runs per-alert queries to Supabase (**N+1**), which will get slow as data
  grows.
- `sessions` Supabase rows are written under two different `session_token` conventions
  (`session_manager` uses the raw `sid`; `api/session.py:start_session` uses
  `session_{user}_{sid[:8]}`), and `counselor.py` queries sometimes match on `session_token`,
  sometimes on `session_id` — an inconsistency that can cause missed lookups.

**Model / cost**
- The GPT model `ft:gpt-3.5-turbo-0125:personal::DqH2I32e` is a **deprecated model lineage** —
  OpenAI has been sunsetting `gpt-3.5-turbo` fine-tunes. Plan to re-tune on `gpt-4o-mini` or newer.
- Whisper `medium` is heavy; it's lazy-loaded, but the first voice request is slow (and may struggle
  on Replit's free 4 GiB runtime under load — switching to `"base"` in `voice.py` is the workaround).
- Acoustic features include a **hard-coded CapCut ffmpeg path**
  (`acoustic_features.py:18`) as a fallback for a specific Windows machine — fine locally, ignored on
  hosts that have a system ffmpeg (Replit does; `voice.py` also auto-uses the `imageio-ffmpeg` binary
  when `ffmpeg` is missing from PATH).

**Frontend / data hygiene**
- Counselor dashboard Overview chart uses **hard-coded mock data** (`CounselorDashboard.jsx` lines
  ~74–80 and ~1078–1085) instead of the analytics API.
- `ForgotPassword` submits but the backend never sends emails.
- Consent is keyed by `session_id`; accepting consent creates the session id in `localStorage`
  before the first chat message, and `session_manager` then creates a *new* session in
  `analyze_intent` — so the consent record and the actual chat session can drift apart.
- `InformedConsent.jsx` hard-codes the user name "Juan Dela Cruz".

**Dead / unused code**
- `backend/app/api/schemas.py` is empty. `backend/app/utils/config.py` is unused.
- `backend/app/voice/tts.py` (if present) duplicates `services/tts.py`.
- `logs/interactions.json` is written but small — Supabase is the real store.

**Nice-to-have / future work**
- No **RAG** (retrieval-augmented generation): GAIDA has no knowledge base lookup; it relies on
  prompt engineering + the last 6 messages as context.
- Student chat uses a per-session **WebSocket** (`/api/session/ws/{id}`) for realtime counselor
  messages, typing indicators, and takeover state; a 3 s polling fallback still runs in case the
  socket drops (reconnect gaps, offline tabs, service-worker cached responses). The counselor
  dashboard still polls `/api/counselor/chat/{id}` every 3 s.
- No database migrations in the repo — table schema is assumed.

---

## 17. Quick start

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate                 # Windows
pip install -r requirements.txt

# set env vars (in backend/.env)
# OPENAI_API_KEY=...
# SUPABASE_URL=...
# SUPABASE_KEY=...

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173  (proxies /api, /audio, /virtual-agent to :8000)
```

### Tests

```bash
cd backend
pytest                              # fast service + auth tests
python tests/test_detection.py      # 30-case intent/severity scenarios
```

### Try it

1. Open `http://localhost:5173` → **Student Portal**.
2. Log in with `2024001` / `student1@ue.edu.ph` / `ACCESS123` (any CAPTCHA).
3. Accept consent → chat with GAIDA.
4. Say something like *"I can't breathe, my chest is tight"* → High severity + counselor alert.
5. Open **Counselor Portal** in another tab → `counselor01` / `counsel123` → Alerts → take over
   the session.
