# GAIDA — Local Setup Guide

Run the full system (backend + frontend) locally on any machine, including how to make
edits and push them back.

## 1. Prerequisites

- **Git** (clone + commit/push)
- **Python 3.13** — use the same major version as the other machines (3.14 may lack
  prebuilt wheels for some packages)
- **Node.js** LTS (v18+)

## 2. Clone the repository

```bash
git clone https://github.com/nyerrr/gaida-system.git
cd gaida-system
```

## 3. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

### Environment variables

Create `backend\.env` (this file is gitignored — it does not exist in the clone).
Copy the values from your Render service's Environment Variables:

```
OPENAI_API_KEY=...
SUPABASE_URL=...
SUPABASE_KEY=...
```

### Run the backend

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

> `--reload` is for local development only. Use the Dockerfile / render.yaml for production.

## 4. Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

The frontend talks to the backend at `VITE_BACKEND_URL` (defaults to
`http://localhost:8000`, which matches the local backend, so no config needed on this
machine). Set it to your deployed Render URL only if you want the local frontend to hit
the production backend.

## 5. Test logins

| Portal    | Credentials |
|-----------|-------------|
| Student   | Student number `2024001`, email `student1@ue.edu.ph`, access code `ACCESS123` |
| Counselor | `counselor01` / `counsel123` |

Flow: Student → login → accept consent → chat. Open the Counselor portal in another tab
to see alerts and take over a session.

## 6. Making edits and pushing

Recommended workflow — always work on a branch, then merge into `main`:

```bash
git checkout main
git pull origin main
git checkout -b my-fix
# ...edit files...
git add .
git commit -m "fix: describe the change"
git push origin my-fix
git push origin my-fix:main      # fast-forward main from your branch
```

Only push when you're sure — `main` is what Render/Vercel deploy.

## First-run notes (important)

- **ML models**: the trained `.pkl` models are committed under
  `backend/training/models/`, so no retraining is needed. Startup simply loads them.
- **Whisper (voice)**: the "medium" transcription model (~1.5 GB) downloads to
  `~/.cache/whisper` on your **first voice message**. Text chat works immediately.
- **ffmpeg**: not required to install on the system — `imageio-ffmpeg` (in
  `requirements.txt`) supplies a bundled ffmpeg that the acoustic features and Whisper
  automatically fall back to.
- **Supabase**: if the keys are missing, the backend still starts but persistence
  (sessions, alerts, consent) will silently degrade — set them before testing the full
  flow.