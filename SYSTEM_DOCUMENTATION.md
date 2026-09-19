# GAIDA — System Documentation

**Snapshot date:** 2026-09-19
**Branches:** `main` (local == origin/main == `5ec7bbd`, plus uncommitted work described below)
**Live endpoints:**
| Service | URL | Status |
|---|---|---|
| Backend (FastAPI) | `https://gaida-system--rainierburlasa4.replit.app` | `GET /` → `{"status":"ok","message":"GAIDA Backend"}` |
| Frontend (Vite PWA) | `https://gaida-system.vercel.app` | Live |

> **What "right now, with uncommitted changes" means:** all content below reflects the code on disk. Novel items added since the last commit (`5ec7bbd`) are tagged **[NEW / UNCOMMITTED]** — 7 modified files + 2 new directories/file groups. Once committed and pushed to `main`, the Replit Git deployment auto-deploys the backend; the Supabase migration listed at the end still needs to be run manually in the SQL editor.

---

## 1. What GAIDA Is

GAIDA (**G**uidance **A**nd **I**ntelligent **D**ialogue **A**ssistant) is a thesis-project AI mental-health support assistant for students at the **University of the East (UE)**. Students chat with GAIDA to vent, get immediate de-escalation, and request counselor help. Guidance counselors get a dashboard with live severity alerts, session history, chat takeover, and case notes.

It is **not** a clinical system: it is a referral-and-support layer backed by rule-based + ML intent detection, an LLM (OpenAI GPT) drafting replies, and human counselors as the escalation endpoint. The system was intentionally designed to present its capabilities honestly (see [§10 Security & Privacy](#10-security-and-privacy) and [§12 Known Limitations](#12-known-limitations)).

---

## 2. Architecture

```
┌────────────────────┐      HTTPS      ┌──────────────────────────────┐
│ Frontend (Vercel)  │────────────────▶│ Backend (Replit, cloudrun)   │
│ React 19 + Vite    │  JSON / NDJSON  │ FastAPI (Python 3.12)        │
│ PWA, offline-ready │◀────────────────│  uvicorn on :8000            │
└────────────────────┘                 │                              │
        │                              │  + ML classifier (sklearn)   │
        │                              │  + Whisper ASR + librosa     │
        │                              │  + gTTS voice output         │
        │   (opt-in research mode)     │  + in-memory token+session   │
        ▼                              │  + in-memory rate limiter    │
┌────────────────────┐                 └──────────────┬───────────────┘
│ Google sign-in     │                                │
│ (@ue.edu.ph only)  │                 ┌──────────────▼───────────────┐
└────────────────────┘                 │ Supabase (Postgres)          │
                                       │ tables: sessions, messages,  │
    LLM replies ──── OpenAI GPT        │ interactions, consents,      │
    voice TTS ────── gTTS (offline)    │ alert_logs, research data,   │
    ASR ──────────── Whisper "medium"  │ ratings, notes, feedback,    │
                                        │ acoustic_logs, ...           │
                                        └──────────────────────────────┘
```

**Key runtime decisions (all deliberate):**

- **Backend session/token state is in-memory** (`ACTIVE_TOKENS`, in-memory session store). It survives between requests but is lost on restart. Acceptable today because deployment is a single Replit instance; persistent data lives in Supabase.
- **Frontend talks only to the FastAPI backend**, never directly to Supabase.
- **CORS is locked** to `localhost:5173`, `localhost:3000`, and `https://gaida-system.vercel.app`.

---

## 3. Tech Stack

| Layer | Technology | Version / Notes |
|---|---|---|
| Frontend | React + Vite | React 19.2, Vite 7, `@vitejs/plugin-react` |
| | State / data | Fetch + AbortController (custom, no Redux) |
| | Routing | react-router-dom v7 |
| | Rendering | react-markdown (GAIDA replies) |
| | PWA | `vite-plugin-pwa`, manifest `GAIDA` |
| | Styling | Tailwind CSS 3.4 + `@tailwindcss/typography`, dark + light theme |
| | Charts | recharts |
| Backend | Python | 3.12 |
| | API | FastAPI + uvicorn |
| | ML | scikit-learn pipeline (pretrained emotion/severity classifiers) |
| | ASR | OpenAI Whisper (`medium`) |
| | Audio features | librosa (energy, RMS, pitch, mfcc, tempo...) |
| | TTS | gTTS |
| | LLM | OpenAI Chat Completions, fine-tuned `ft:gpt-3.5-turbo-0125:personal::DqH2I32e` (hardcoded in `gpt_agent.py`) |
| | Validation | Google OAuth (`google.oauth2.id_token`) for `@ue.edu.ph` |
| DB | Supabase (Postgres) | Provider-agnostic client wrapper |
| Deploy | Replit (backend, Deployments from Git) | `.replit` → `uvicorn app.main:app` on `:8000` |
| | Vercel (frontend) | Static PWA build |

---

## 4. Repository Layout

```
gaida-system/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI wiring, CORS, security headers
│   │   ├── constants.py            # TEST_CREDENTIALS (3 students + 1 counselor)
│   │   ├── api/
│   │   │   ├── auth.py             # /api/auth/* (login, google, consent, forgot)
│   │   │   ├── voice.py            # /audio/* (speech-to-text, tts, analyze) — NO token guard
│   │   │   ├── counselor.py        # 23 /api/counselor/* endpoints — NO token guard
│   │   │   ├── session.py          # /api/session/* incl. feedback + WS — no token guard
│   │   │   └── research.py         # /api/research/* incl. withdraw [NEW] — no guard
│   │   ├── services/
│   │   │   ├── intent_router.py    # intent pipeline + crisis clearance [NEW]
│   │   │   ├── virtual_agent.py    # reply drafting (LLM + fallback)
│   │   │   ├── session_manager.py  # session CRUD + welfare check [NEW]
│   │   │   ├── acoustic_service.py # librosa feature extraction
│   │   │   ├── rate_limiter.py     # sliding-window limiter
│   │   │   └── ml_classifier.py    # loads pretrained sklearn models
│   │   ├── utils/auth.py           # bearer tokens (12h TTL), get_current_user
│   │   └── database/database.py    # Supabase client (env-guarded)
│   ├── training/
│   │   ├── acoustic_validation/      # [NEW — uncommitted] labeled-clip harness
│   │   │   ├── README.md
│   │   │   ├── evaluate_acoustic.py
│   │   │   └── sample_labeled_acoustic.csv
│   │   ├── finetune.jsonl          # LLM reply-tuning examples (guidance-safe)
│   │   ├── m<model files>          # pretrained sklearn models
│   │   └── sql/                    # SQL migrations (run in Supabase)
│   │       ├── 2026_02_add_research_participants.sql      # (collaborator commit)
│   │       ├── 2026_add_research_support.sql              # (collaborator commit)
│   │       └── 2026_09_add_message_feedback.sql           # [NEW — uncommitted]
│   ├── Dockerfile                  # (already committed on main)
│   ├── .dockerignore               # (already committed on main)
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── config.js               # BACKEND_URL from VITE_BACKEND_URL
│   │   ├── App.jsx                 # routes + route guards
│   │   ├── components/             # shared UI
│   │   ├── features/
│   │   │   ├── landing/            # portal selection
│   │   │   ├── auth/               # login (ID+code / Google-in)
│   │   │   ├── student/StudentDashboard.jsx  # chat, hotline, per-message feedback
│   │   │   └── counselor/CounselorDashboard.jsx  # alerts, live chats, welfare
│   │   ├── services/chat.js        # streaming chat client (AbortController)
│   ├── .env.example
│   └── package.json                # build: "vite build"
├── .replit                         # Replit deployment config (root, committed)
├── GAIDA_SYSTEM.md                 # process/doc notes + audit answers
├── GAIDA_OVERVIEW.md               # short public/faculty summary
└── SYSTEM_DOCUMENTATION.md         # THIS FILE (current-state snapshot)
```

---

## 5. Environment Variables

**Backend (`backend/.env` / Replit Production secrets) — the app refuses to boot without all four:**

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | LLM reply drafting |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | anon/service key |
| `GOOGLE_CLIENT_ID` | Google sign-in credential verification |

`backend/app/database/database.py` raises `RuntimeError` at import time if any of the Supabase pair is missing. The GPT model is a hardcoded constant in `gpt_agent.py`: `ft:gpt-3.5-turbo-0125:personal::DqH2I32e`.

**Frontend (`frontend/.env`):**
| Variable | Purpose |
|---|---|
| `VITE_BACKEND_URL` | Backend origin (defaults to `http://localhost:8000`) |
| `VITE_GOOGLE_CLIENT_ID` | Google Sign-In button client ID |

---

## 6. Data Model (Supabase Tables)

Core chat & platform:

| Table | Notes |
|---|---|
| `sessions` | session_id, user_id, participant_code (research), status, severity info, timestamps |
| `messages` | per-turn chat log |
| `interactions` | intent classification outcome rows |
| `consents` | consent_given per session (consent to log) |
| `session_ratings` | post-session student self-rating |
| `session_notes` | counselor notes on a session |
| `counselor_alerts` | severity alerts + resolve/assign state |
| `acoustic_logs` | per-utterance audio features + fusion verdict |

Research module (added by collaborator migrations):

| Table | Notes |
|---|---|
| `research_participants` | participant_id (`anon_<code>`), consent fields, demographic opts |
| `gad7_responses` | GAD-7 scale answers during research sessions |

Feedback (added by **[NEW — uncommitted] `2026_09_add_message_feedback.sql`**):

| Table | Notes |
|---|---|
| `message_feedback` | message_id, session_id, user_id, rating (`helpful`/`not_helpful`), feedback_text (optional), created_at |

> **Action required:** run `backend/training/sql/2026_09_add_message_feedback.sql` in the Supabase SQL editor. Until then the feedback endpoint degrades gracefully (returns without storing), so the UI still works.

---

## 7. Authentication, Sessions, and Route Guards

### 7.1 Test credentials (`backend/app/constants.py`, hardcoded)

| Student # | E-mail | Access code | Name | Program |
|---|---|---|---|---|
| `2024001` | student1@ue.edu.ph | `ACCESS123` | Maria Santos | BS Psychology (Y2) |
| `2024002` | student2@ue.edu.ph | `ACCESS456` | Juan dela Cruz | BS Computer Science (Y3) |
| `2024003` | student3@ue.edu.ph | `ACCESS789` | Ana Reyes | BS Nursing (Y1) |

| Counselor ID | Access code | Name |
|---|---|---|
| `COUNSELOR01` | `counsel123` | Dr. Patricia Lim |

### 7.2 Login flows
- **Student ID login** → `POST /api/auth/login` — checks `@ue.edu.ph` domain + hardcoded credential, issues bearer token. Rate-limited by student number.
- **Google login** → `POST /api/auth/google` — verifies the ID token against `GOOGLE_CLIENT_ID`; requires `email_verified` and a `@ue.edu.ph` domain; maps a matching `TEST_CREDENTIALS` e-mail back to the student number. `503` if server-side `GOOGLE_CLIENT_ID` is unset.
- **Counselor login** → `POST /api/auth/counselor-login` — validates the `COUNSELOR01` faculty ID + access code and issues a **counselor-bearing** token (unlocks the role-gated `/api/counselor/*` routes). `401` on bad credentials (rate-limited by faculty ID).
- **Consent** → `POST /api/auth/consent` records `consent_given` per session (upsert).
- **Forgot password** → `POST /api/auth/forgot-password` — always returns success (no e-mail enumeration).

### 7.3 Tokens
`create_session_token(user_id, role)` → `token_<role>_<urlsafe>` stored in the in-memory `ACTIVE_TOKENS` dictionary with a **12-hour TTL**. `get_current_user` (FastAPI dependency) requires `Authorization: Bearer <token>`, purges expired tokens, and returns `{user_id, role, expires_at}`.

### 7.4 Route guards
- **Backend:** every route requires a bearer token except the deliberately-public list in [§13](#13-api-reference). Counselor-only routes are role-gated (`Depends(require_role("counselor"))` → 403 for other roles); student/research routes enforce session ownership (403 unless the token's `user_id` owns the `session_id`).
- **Frontend (`App.jsx` / `src/api.js`):** route guards redirect to the portal when tokens are missing. `apiFetch()` attaches `Authorization: Bearer <token>` to every call (student or counselor token from `localStorage`) and bounces to `/` on any 401.

---

## 8. Chat Pipeline (Student → GAIDA)

1. **Auth + ownership check** — token validated, session (if given) must belong to the caller; rate limit enforced.
2. **Session resolve/create** (`session_manager`) — find last active session or start a new one with consent `false` until the student opts in.
3. **Intent detection** (`intent_router.go`)
   - Keyword / rule matcher (topic: academic, relationship, bullying, family, self-harm, vent, crisis…).
   - ML classifier (`ml_classifier`) predicts emotion + severity with a confidence score.
   - Confidence is **running-averaged** across the session and mapped to a 5-level severity band:
     `≥0.99 Crisis · ≥0.75 High · ≥0.60 Moderate · ≥0.45 Low · else Normal`.
4. **Special handling — crisis / suicidal ideation:**
   - Emits counselor alert (`counselor_alerts`), marks session high-risk.
   - Reply includes immediate safety guidance + hotlines (national hotline **1553**, In Touch Community Services **(02) 8-926-8040**, **911**).
   - **`[NEW — UNCOMMITTED]` De-escalation clearance hold:** once a High/Crisis signal occurs, GAIDA does **not** step back down automatically. The session is held at High (0.80) or Crisis (0.99) and GAIDA asks "Are you safe right now?" until the student gives an **explicit safety confirmation** (e.g. *"I'm safe"*, *"safe na ako"*, *"yes po, okay na ako"*). Short affirmatives (`yes`, `opo`) only count when the session still needs clearance (`meta.needs_clearance=True`). While held, `counselor_protocol=CLEARANCE_PROTOCOL` is set so counselors see that de-escalation is in progress.
5. **Acoustic fusion (voice mode)** — if the message came through the voice pipeline, `acoustic_service` features are fused into the severity/imminence estimate.
6. **Counselor active?** — if a `COUNSELOR01`-side takeover is active for the session, GAIDA replies `counselor_active: true` and hands off to the human.
7. **Reply drafting** — fine-tuned LLM `ft:gpt-3.5-turbo-0125:personal::DqH2I32e` (OpenAI Chat Completions) with the session transcript + intent as context, guided by `finetune.jsonl`-style examples (warm, brief, PhilEnglish, validation-first, never diagnostic). On failure (missing key/network) it falls back to a deterministic scripted reply.
8. **Record** — message, intent result, and interaction row persisted to Supabase.

### 8.1 Endpoints
- `POST /virtual-agent` — one-shot JSON reply.
- `POST /virtual-agent/stream` — NDJSON stream: `{"type":"delta","text":…}`…`{"type":"done","result":{…}}`. Consumed in `StudentDashboard.jsx` via a streaming `ReadableStream` reader (with an AbortController stop button).

---

## 9. Voice Pipeline

1. **Record** (browser `MediaRecorder` → webm/opus; `VoiceInput.jsx` uses the browser Web Speech API for a live `fil-PH` preview while recording).
2. **Upload `POST /audio/speech-to-text`** → librosa extracts acoustic features (energy, RMS, pitch, MFCC, speech rate, pause ratio, jitter/shimmer) which are mapped to an acoustic severity + logged to `acoustic_logs`; then Whisper (`medium`) transcribes to text. The acoustic reading is parked on the session (`meta.pending_acoustic`) for fusion.
3. **Fusion** — acoustic features refine the text-derived severity estimate (e.g., high energy + crying cues raise imminence).
4. **TTS** — `GET /audio/tts?text=…` returns MP3 via gTTS. **Not auto-spoken in the live chat yet** — the endpoint is ready (and the recording UI only replays the student's own audio).

**[NEW — UNCOMMITTED] `backend/training/acoustic_validation/`** is the evaluation harness for the defense:
- `evaluate_acoustic.py` — runs labeled clips through the real transcription + feature + fusion pipeline and prints per-emotion accuracy (emotion prediction, severity match, panic/harm recall/false-positive).
- `sample_labeled_acoustic.csv` — template with clips named `emotion_severity_intensity_idx.ext` and columns `clip_path | true_emotion | true_severity | notes`.
- `README.md` — how to record the ~5–10 clips per emotion set with a phone, label them, and produce the accuracy table for the paper/appendix.

**Status:** harness ready; clips still need to be gathered by the team. Known risk: Whisper `medium` may run out of memory on Replit free under load — switch to `"base"` in `voice.py` if you see OOMs.

---

## 10. Security & Privacy (honest posture)

**Implemented now:**
- Bearer tokens (12 h TTL, role-tagged), backend `Depends(get_current_user)` / `Depends(require_role("counselor"))` — enforced on **every** route except the deliberately-public list in §13 (health, login, consent, research intake, withdraw-by-code).
- `POST /api/auth/counselor-login` — real backend counselor login (was a client-side check + literal `dev-token`).
- Frontend route guards + a shared `apiFetch()` wrapper that attaches the bearer token to all calls and redirects on 401.
- CORS allow-list, security headers (`nosniff`, `DENY` frame, `strict-origin-when-cross-origin`).
- Rate limiting (login, virtual-agent, research, feedback endpoints).
- Session-ownership check (`403` if `session_id` belongs to another user).
- Researcher-anonymity by construction: `participant_id = anon_<code>`, nobody but the researcher knows the code.
- **[NEW]** Right-to-erasure: `POST /api/research/withdraw` deletes a researcher's data by anonymous code (sweeps `interactions`, `consents`, `gad7_responses`, `session_ratings`, `session_notes`, `counselor_alerts`, `acoustic_logs` → `sessions` → `research_participants`; idempotent; rate-limited).
- **[NEW]** Honest copy — the UI no longer claims messages are "private and encrypted". `GAIDA_SYSTEM.md` now states sessions are "records each session for the guidance office to review".

**Honest gaps (documented, defensible for a thesis prototype):**
- Data-at-rest is **not** encrypted at the DB level; it is ordinary Supabase Postgres. Decision: **transparency + retention instead of encryption claims.**
- Tokens are in-memory (lost on restart, no cross-instance). Fine for single Replit instance.
- The audit list for the defense includes: unvalidated voice/acoustic accuracy (harness built), GAD-7 only in research flow, hardcoded test logins, no automated account registration (counselor creates accounts), retention/deletion only partially automated (**default policy: 6 months**).

---

## 11. Counselor Dashboard

Backend-protected now — every `/api/counselor/*` route requires a bearer token. Counselor-only routes are role-gated (`require_role("counselor")` → 403 for students); the student-facing routes (`/student/checkin`, `/session/rate`, `/request-counselor`, `/chat/<id>`, `/typing/<id>`) accept any valid token but enforce session ownership.

- **Student check-in** — `GET /api/counselor/student/checkin/<student_id>` top-up status of a student (student may only see their own; counselor sees any).
- **Session request** — student can request counselor; counselor sees pending.
- **Live alerts** — `alerts` feed with severity, message excerpt, and assign/resolve actions.
- **Live sessions** — active sessions list incl. severity trend data; **chat takeover** (see §8.6).
- **Session actions** — rate, write notes, resolve; query severity from score.
- **`[NEW — UNCOMMITTED]` Silent-student welfare check**: High/Crisis sessions with **no student message for ≥ 30 minutes** are surfaced via `GET /api/counselor/sessions/welfare` instead of being auto-hidden by the active-session filter; `POST /api/counselor/sessions/welfare-checked` marks them handled (a `_WELFARE_CHECKED` set keeps re-polling from re-flagging) so the counselor follows up (the "silent student" gap from the audit).

---

## 12. Research Flow (Opt-In, Identified or Anonymous)

1. Portal → **"Participate in research"**.
2. `GET/POST /api/research/participant-check` — enter the researcher-issued anonymous code.
3. Consent steps; research participant row created (`anon_<code>` in `research_participants`).
4. Research-mode sessions are labeled with `participant_code`; GAD-7 form collects responses into `gad7_responses`.
5. Researcher contact (as committed by collaborator): **reyes.laurienaemanuel@ue.edu.ph** in `ResearchFlow.jsx`.
6. **`[NEW — UNCOMMITTED]` Withdrawal:** *“Delete my data”* → `POST /api/research/withdraw` with the anonymous code → everything keyed to that code is purged (idempotent). This satisfies the audit item *“no deleted-by-code data removal”*.

---

## 13. API Reference

### Public (no token — deliberately)
| Method | Path | Notes |
|---|---|---|
| GET | `/` | health check |
| HEAD | `/` | liveness |
| POST | `/api/auth/login` | student ID login (rate-limited) |
| POST | `/api/auth/google` | verified @ue.edu.ph Google login |
| POST | `/api/auth/forgot-password` | always-ok response |
| POST | `/api/auth/consent` | record consent flag per session |
| POST | `/api/research/participant-check` | research-code check + consent |
| POST | `/api/research/start` | create research session (opt-in; issues the research token) |
| POST | `/api/research/withdraw` | self-service "delete my data" by anonymous code (a participant may have lost their token; code alone must work) |

### Token-protected (Bearer required)
| Method | Path | Access |
|---|---|---|
| POST | `/virtual-agent`, `/virtual-agent/stream` | any role + ownership |
| POST | `/api/session/start`, `/api/session/message`, `/api/session/feedback` | any role + ownership |
| GET | `/api/session/<id>`, `/api/session/active` | any role + ownership |
| POST | `/api/session/<id>/end` | any role + ownership |
| WS | `/api/session/ws/<id>?token=…` | token required (query param) |
| POST | `/api/research/gad7` | any role + ownership |
| POST | `/audio/speech-to-text`, `/audio/analyze`, `GET /audio/tts` | any role (+ ownership on provided `session_id`) |
| ALL | `/api/counselor/*` | token required; **counselor-only routes role-gated** (alerts, welfare, active/resolved/delete, takeover/return, notes, profile, analytics, export, severity → `require_role("counselor")`); **student-facing routes ownership-checked** (checkin, session/rate, request-counselor, chat, typing) |

> Effect: every endpoint requires a valid token — verified by smoke tests (no token → 401; student token on counselor route → 403; other student's session → 403; counselor → 200). Hardcoded test logins remain (documented) but the "every endpoint requires a token" claim is now true.

---

## 14. Deployment

### Backend — Replit (now Git-connected, auto-deploy)
- `.replit` (repo root, committed in `5ec7bbd`): modules `nodejs-20`, `python-3.12`, `web`; `[deployment]` → `run = ["sh","-c","cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000"]`, `deploymentTarget = "cloudrun"`.
- **Flow:** any push to `main` auto-deploys. (Manual "pull + Republish" is no longer needed.)
- Runtime const: 2 vCPU / 4 GiB; Whisper `medium` + sklearn models pre-warm on startup via the `@app.on_event("startup")` hook.
- Health: `GET /` must return `{"status":"ok"}`; an old deployment at the same URL continues serving until the new one is healthy.

### Frontend — Vercel
- Build: `vite build` (PWA assets generated by `vite-plugin-pwa`).
- `VITE_BACKEND_URL` is baked to the Replit backend URL above.

---

## 15. Testing & Validation Artifacts (for the defense)

- **Expert validation kit** — `validation_form.html` / `training_audit_form.html` for counselors (dataset + consistency audit). *Needs the counselors' kappa numbers collected.*
- **ML recall** — historical runs recalled **27/27** suicidal-intent cases. Pre-trained sklearn models under `backend/training/`.
- **LLM reply tuning** — `finetune.jsonl` (guidance-safe tone examples).
- **`[NEW]` Acoustic accuracy harness** — needs labeled clips; produces per-emotion accuracy + panic/harm recall/FP for the paper (§9).
- **Feedback telemetry — `[NEW]`** — `message_feedback` rows give per-message helpfulness counts to cite.

---

## 16. Known Limitations (be ready to say these out loud)

1. `ACTIVE_TOKENS` and session state are in-memory → resets on deploy/restart (tokens die, ongoing sessions drop). Single-instance assumption.
2. Voice accuracy is unproven until the labeled clips are run through `evaluate_acoustic.py`; Whisper `medium` is heavy for free-tier runtime.
3. Login is hardcoded test credentials (plus Google for real @ue.edu.ph users) — no self-service registration yet (intended: counselor creates accounts).
4. GAD-7 is research-flow-only, not a regular-session screening step.
5. No DB-level encryption at rest; retention automation is policy (6 months) + the manual-withdraw API, not yet a scheduled job.
6. WebSocket `/api/session/ws/<id>` validates the token but does not verify the socket owner matches the session (token-only). Research intake / withdraw stay public by design (a participant may not hold a token when re-entering or withdrawing).
7. TTS is `gTTS` (robotic but dependency-free); display name has no PH-accented voice.

---

## 17. Current Git State (uncommitted work on `main`)

`git status --short` (10 modified, 3 new files + 2 new dirs):

```
 M GAIDA_OVERVIEW.md                           docs: rewritten to match the real system
 M GAIDA_SYSTEM.md                             docs: Render → Replit updates
 M backend/app/api/auth.py                     counselor-login endpoint + LoginResponse.name
 M backend/app/api/counselor.py                bearer auth on all 23 routes (role-gated + ownership)
 M backend/app/api/research.py                 /gad7 now token-protected
 M backend/app/api/session.py                  /start /message /feedback /end ownership-checked; WS token
 M backend/app/api/voice.py                    /audio/* token-protected
 M backend/app/services/intent_router.py       de-escalation clearance hold
 M backend/app/services/session_manager.py     welfare-check helper
 M backend/app/utils/auth.py                   require_role + validate_token helpers
 M frontend/src/features/auth/CounselorLogin.jsx       → real /api/auth/counselor-login
 M frontend/src/features/counselor/CounselorDashboard.jsx  apiFetch() tokens
 M frontend/src/features/research/ResearchFlow.jsx            token on consent/gad7
 M frontend/src/features/student/StudentDashboard.jsx        apiFetch() tokens + honesty copy
 M frontend/src/features/voice/VoiceInput.jsx                apiFetch() token
?? SYSTEM_DOCUMENTATION.md
?? backend/training/acoustic_validation/        (README.md, evaluate_acoustic.py, sample_labeled_acoustic.csv)
?? backend/training/sql/2026_09_add_message_feedback.sql
?? frontend/src/api.js                          shared Bearer-token fetch wrapper + 401 redirect
```

Summary of the diff: de-escalation clearance hold (§8 step 4), welfare endpoints + flag set (§11), withdraw endpoint (§12), `message_feedback` storage + graceful-degrade (§6/§13), acoustic validation harness (§9), honesty fixes, **and backend auth hardening (§7/§13)** — every route except the public list now requires a bearer token, counselor routes are role-gated, student/research routes enforce session ownership, and the frontend sends tokens via `apiFetch()`.

**Before finalizing into the paper, still to do:**
1. Run `backend/training/sql/2026_09_add_message_feedback.sql` in Supabase.
2. Collect + label voice clips, run `evaluate_acoustic.py`, paste results into §15/§9.
3. Commit + push `main` (auto-deploys backend).
4. Next hardening batch (after auth ships): GAD-7 in the regular student flow; a scheduled 6-month retention job; counselor-created accounts.