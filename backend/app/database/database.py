from supabase import create_client
from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    env_path = Path(".env").resolve()
    raise RuntimeError(
        "Missing Supabase credentials.\n"
        f"  - Expected config file: {env_path} (exists={env_path.exists()})\n"
        f"  - SUPABASE_URL set: {bool(SUPABASE_URL)}\n"
        f"  - SUPABASE_KEY set: {bool(SUPABASE_KEY)}\n"
        "  Fix: copy backend/.env.example to backend/.env and fill in your real values."
    )

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)