from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = "change-this-secret-key"
    DATABASE = BASE_DIR / "users.db"
