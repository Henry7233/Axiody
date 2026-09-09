from pathlib import Path
import os
import secrets


BASE_DIR = Path(__file__).resolve().parent


class Config:
    # Use a stable private key in deployment. The temporary fallback invalidates
    # existing login sessions when the server process restarts.
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    DATABASE = BASE_DIR / "users.db"
