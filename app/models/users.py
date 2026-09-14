import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash


@contextmanager
def get_connection(database_path):
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def format_created_date(created_at):
    return created_at[:10] if created_at else ""


def normalize_email(email):
    return (email or "").strip().lower()


def normalize_full_name(full_name):
    return (full_name or "").strip()


def normalize_account_type(account_type):
    return account_type if account_type in {"client", "admin"} else "client"


def normalize_role(role, account_type):
    return (role or ("Administrator" if account_type == "admin" else "Client")).strip()


def init_user_db(database_path):
    with get_connection(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                account_type TEXT NOT NULL DEFAULT 'client',
                role TEXT NOT NULL DEFAULT 'Client',
                protected INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        columns = connection.execute("PRAGMA table_info(users)").fetchall()
        column_names = {column["name"] for column in columns}
        if "full_name" not in column_names:
            connection.execute(
                "ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT ''"
            )
        if "account_type" not in column_names:
            connection.execute(
                "ALTER TABLE users ADD COLUMN account_type TEXT NOT NULL DEFAULT 'client'"
            )
        if "role" not in column_names:
            connection.execute(
                "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'Client'"
            )
            connection.execute(
                """
                UPDATE users
                SET role = 'Administrator'
                WHERE account_type = 'admin'
                """
            )
        if "protected" not in column_names:
            connection.execute(
                "ALTER TABLE users ADD COLUMN protected INTEGER NOT NULL DEFAULT 0"
            )
        for column, default in (("theme", "light"), ("font_size", "medium")):
            if column not in column_names:
                connection.execute(
                    f"ALTER TABLE users ADD COLUMN {column} TEXT NOT NULL DEFAULT '{default}'"
                )


def create_user(
    database_path,
    email,
    password,
    account_type="client",
    protected=0,
    full_name="",
    role=None,
):
    normalized_email = normalize_email(email)
    normalized_account_type = normalize_account_type(account_type)
    normalized_protected = 1 if protected else 0
    normalized_full_name = normalize_full_name(full_name)
    normalized_role = normalize_role(role, normalized_account_type)
    password_hash = generate_password_hash(password)
    created_at = datetime.now(timezone.utc).isoformat()

    with get_connection(database_path) as connection:
        try:
            cursor = connection.execute(
                """
                INSERT INTO users (
                    full_name, email, password_hash, account_type, role, protected, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_full_name,
                    normalized_email,
                    password_hash,
                    normalized_account_type,
                    normalized_role,
                    normalized_protected,
                    created_at,
                ),
            )
        except sqlite3.IntegrityError:
            return None

        return {
            "id": cursor.lastrowid,
            "full_name": normalized_full_name,
            "email": normalized_email,
            "account_type": normalized_account_type,
            "role": normalized_role,
            "protected": normalized_protected,
            "created_at": created_at,
            "date": format_created_date(created_at),
        }


def get_user_by_email(database_path, email):
    normalized_email = normalize_email(email)

    with get_connection(database_path) as connection:
        return connection.execute(
            """
            SELECT id, full_name, email, password_hash, account_type, role, protected, created_at
            FROM users
            WHERE email = ?
            """,
            (normalized_email,),
        ).fetchone()


def get_user_by_id(database_path, user_id):
    with get_connection(database_path) as connection:
        return connection.execute(
            """
            SELECT id, full_name, email, password_hash, account_type, role, protected, created_at, theme, font_size
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()


def list_admin_users(database_path):
    with get_connection(database_path) as connection:
        return [
            {
                "id": user["id"],
                "name": user["full_name"] or user["email"],
                "email": user["email"],
                "role": user["role"] or "Administrator",
                "date": format_created_date(user["created_at"]),
                "protected": user["protected"],
            }
            for user in connection.execute(
                """
                SELECT id, full_name, email, role, protected, created_at
                FROM users
                WHERE account_type = 'admin'
                ORDER BY id
                """
            ).fetchall()
        ]


def list_users(database_path):
    with get_connection(database_path) as connection:
        return [
            {
                "id": user["id"],
                "name": user["full_name"] or user["email"],
                "email": user["email"],
                "account_type": user["account_type"],
                "role": user["role"] or ("Administrator" if user["account_type"] == "admin" else "Client"),
            }
            for user in connection.execute(
                """
                SELECT id, full_name, email, account_type, role
                FROM users
                ORDER BY id
                """
            ).fetchall()
        ]


def delete_user(database_path, user_id):
    with get_connection(database_path) as connection:
        user = connection.execute(
            "SELECT protected FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if user is None:
            return {"deleted": False, "reason": "not_found"}

        if user["protected"]:
            return {"deleted": False, "reason": "protected"}

        # Keep other clients' reviewed documents when their reviewer leaves.
        connection.execute("UPDATE documents SET reviewed_by = NULL WHERE reviewed_by = ?", (user_id,))
        connection.execute("DELETE FROM documents WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return {"deleted": True, "reason": None}


def update_admin_user(database_path, user_id, full_name, email, role, password=""):
    with get_connection(database_path) as connection:
        try:
            cursor = connection.execute(
                """
                UPDATE users SET full_name = ?, email = ?, role = ?
                WHERE id = ? AND account_type = 'admin'
                """,
                (full_name.strip(), email.strip().lower(), role.strip(), user_id),
            )
        except sqlite3.IntegrityError:
            return {"updated": False, "reason": "duplicate_email"}
        if not cursor.rowcount:
            return {"updated": False, "reason": "not_found"}
        if password:
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(password), user_id),
            )
        return {"updated": True, "reason": None}


def delete_unprotected_admin_users(database_path):
    with get_connection(database_path) as connection:
        users = connection.execute(
            """
            SELECT id
            FROM users
            WHERE account_type = 'admin'
              AND protected = 0
            """
        ).fetchall()
        deleted_ids = [user["id"] for user in users]
        if deleted_ids:
            connection.executemany(
                "DELETE FROM users WHERE id = ?",
                [(user_id,) for user_id in deleted_ids],
            )

        return {"deleted": len(deleted_ids), "deleted_ids": deleted_ids}


def update_user_account(database_path, user_id, full_name, email, password="", password_confirmation="", role=""):
    normalized_full_name = normalize_full_name(full_name)
    normalized_email = normalize_email(email)
    normalized_role = normalize_role(role, "client")

    if not normalized_full_name:
        return {"updated": False, "reason": "missing_name"}
    if not normalized_email:
        return {"updated": False, "reason": "missing_email"}

    if password or password_confirmation:
        if len(password) < 8:
            return {"updated": False, "reason": "password_weak"}
        if password != password_confirmation:
            return {"updated": False, "reason": "password_mismatch"}

    with get_connection(database_path) as connection:
        current = connection.execute(
            "SELECT account_type, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if current is None:
            return {"updated": False, "reason": "not_found"}
        # Self-service role labels are optional for clients; admin roles stay assigned.
        if current["account_type"] == "admin" or not normalized_role:
            normalized_role = current["role"]
        existing = connection.execute(
            "SELECT id FROM users WHERE email = ? AND id != ?",
            (normalized_email, user_id),
        ).fetchone()
        if existing is not None:
            return {"updated": False, "reason": "duplicate_email"}

        if password:
            cursor = connection.execute(
                """
                UPDATE users
                SET full_name = ?, email = ?, role = ?, password_hash = ?
                WHERE id = ?
                """,
                (normalized_full_name, normalized_email, normalized_role, generate_password_hash(password), user_id),
            )
        else:
            cursor = connection.execute(
                """
                UPDATE users
                SET full_name = ?, email = ?, role = ?
                WHERE id = ?
                """,
                (normalized_full_name, normalized_email, normalized_role, user_id),
            )

        if not cursor.rowcount:
            return {"updated": False, "reason": "not_found"}

        updated = connection.execute(
            """
            SELECT id, full_name, email, account_type, role, protected, created_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

    return {
        "updated": True,
        "reason": None,
        "account": {
            "id": updated["id"],
            "full_name": updated["full_name"],
            "email": updated["email"],
            "account_type": updated["account_type"],
            "role": updated["role"],
            "protected": updated["protected"],
            "created_at": updated["created_at"],
        },
    }


def update_user_appearance(database_path, user_id, theme, font_size):
    if theme not in {"light", "dark", "system"} or font_size not in {"small", "medium", "large"}:
        return False
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            "UPDATE users SET theme = ?, font_size = ? WHERE id = ?",
            (theme, font_size, user_id),
        )
        return bool(cursor.rowcount)


def update_user_password(database_path, user_id, password):
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), user_id),
        )
        return bool(cursor.rowcount)


def verify_user(database_path, email, password):
    user = get_user_by_email(database_path, email)
    if user is None:
        return None

    if not check_password_hash(user["password_hash"], password):
        return None

    return {
        "id": user["id"],
        "full_name": user["full_name"],
        "email": user["email"],
        "account_type": user["account_type"],
        "role": user["role"],
        "protected": user["protected"],
        "created_at": user["created_at"],
        "date": format_created_date(user["created_at"]),
    }
