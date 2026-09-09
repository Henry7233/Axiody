import sqlite3
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash


def get_connection(database_path):
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def format_created_date(created_at):
    return created_at[:10] if created_at else ""


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


def create_user(
    database_path,
    email,
    password,
    account_type="client",
    protected=0,
    full_name="",
    role=None,
):
    normalized_email = email.strip().lower()
    normalized_account_type = account_type if account_type in {"client", "admin"} else "client"
    normalized_protected = 1 if protected else 0
    normalized_full_name = full_name.strip()
    normalized_role = (role or ("Administrator" if normalized_account_type == "admin" else "Client")).strip()
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
    normalized_email = email.strip().lower()

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
            SELECT id, full_name, email, password_hash, account_type, role, protected, created_at
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

        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return {"deleted": True, "reason": None}


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
