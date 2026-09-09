import sqlite3
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash


def get_connection(database_path):
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_user_db(database_path):
    with get_connection(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                account_type TEXT NOT NULL DEFAULT 'client',
                created_at TEXT NOT NULL
            )
            """
        )
        columns = connection.execute("PRAGMA table_info(users)").fetchall()
        column_names = {column["name"] for column in columns}
        if "account_type" not in column_names:
            connection.execute(
                "ALTER TABLE users ADD COLUMN account_type TEXT NOT NULL DEFAULT 'client'"
            )


def create_user(database_path, email, password, account_type="client"):
    normalized_email = email.strip().lower()
    normalized_account_type = account_type if account_type in {"client", "admin"} else "client"
    password_hash = generate_password_hash(password)
    created_at = datetime.now(timezone.utc).isoformat()

    with get_connection(database_path) as connection:
        try:
            cursor = connection.execute(
                """
                INSERT INTO users (email, password_hash, account_type, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (normalized_email, password_hash, normalized_account_type, created_at),
            )
        except sqlite3.IntegrityError:
            return None

        return {
            "id": cursor.lastrowid,
            "email": normalized_email,
            "account_type": normalized_account_type,
        }


def get_user_by_email(database_path, email):
    normalized_email = email.strip().lower()

    with get_connection(database_path) as connection:
        return connection.execute(
            "SELECT id, email, password_hash, account_type FROM users WHERE email = ?",
            (normalized_email,),
        ).fetchone()


def verify_user(database_path, email, password):
    user = get_user_by_email(database_path, email)
    if user is None:
        return None

    if not check_password_hash(user["password_hash"], password):
        return None

    return {
        "id": user["id"],
        "email": user["email"],
        "account_type": user["account_type"],
    }
