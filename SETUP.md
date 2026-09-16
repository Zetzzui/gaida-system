# GAIDA System — Full Setup Guide (Terminal)

## On the OLD laptop — push everything first

```powershell
cd C:\Users\YourName\Documents\gaida-system
git status
git add -A
git commit -m "your message"
git push origin GAIDA-commits
```

---

## On the NEW laptop — from scratch

### 1. Install prerequisites

Download and install:
- Git: https://git-scm.com/downloads
- Python 3.13: https://www.python.org/downloads/
- Node.js LTS: https://nodejs.org

### 2. Clone and switch branch

```powershell
cd C:\Users\YourName\Documents
git clone https://github.com/nyerrr/gaida-system.git
cd gaida-system
git checkout GAIDA-commits
git pull origin GAIDA-commits
```

### 3. Set up backend

```powershell
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 4. Set up frontend

```powershell
cd ..\frontend
npm install
```

### 5. Copy your .env files (DO NOT SKIP)

These files hold your API keys and are excluded from git.
Copy them manually from the old laptop via USB, Google Drive, etc.

Files to copy:
- backend\.env
- frontend\.env

### 6. Verify everything works

Open terminal 1 (backend):
```powershell
cd C:\Users\YourName\Documents\gaida-system\backend
venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Open terminal 2 (frontend):
```powershell
cd C:\Users\YourName\Documents\gaida-system\frontend
npm run dev
```

Open browser: http://localhost:5173

### 7. Run tests

```powershell
cd C:\Users\YourName\Documents\gaida-system\backend
venv\Scripts\Activate.ps1
python -m pytest -q
```

Expected: 11 passed.

---

## Going forward (keep both laptops in sync)

Before starting work:
```powershell
git pull origin GAIDA-commits
```

After finishing work:
```powershell
git add -A
git commit -m "your message"
git push origin GAIDA-commits
```

Always pull before you start and push before you stop.
