import sqlite3
import re
from contextlib import contextmanager
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash


@contextmanager
def get_connection(database_path):
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    # Commit on success or roll back on error, then close the connection so SQLite
    # files are not left open (especially on Windows).
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_user_db(database_path):
    with get_connection(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        # Upgrade existing databases without deleting accounts. Existing users
        # start without admin access; repeat app starts skip this migration.
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
        if "is_admin" not in columns:
            connection.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        # Keep one request per account, including its final decision and reviewer.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_access_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected')),
                requested_at TEXT NOT NULL,
                reviewed_at TEXT,
                reviewed_by INTEGER REFERENCES users(id)
            )
            """
        )


def create_user(database_path, email, password):
    # Normalize email for consistent lookups and store only a password hash.
    normalized_email = email.strip().lower()
    password_hash = generate_password_hash(password)
    created_at = datetime.now(timezone.utc).isoformat()

    with get_connection(database_path) as connection:
        try:
            cursor = connection.execute(
                """
                INSERT INTO users (email, password_hash, created_at)
                VALUES (?, ?, ?)
                """,
                (normalized_email, password_hash, created_at),
            )
        except sqlite3.IntegrityError:
            return None

        return {"id": cursor.lastrowid, "email": normalized_email}


def get_user_by_email(database_path, email):
    normalized_email = email.strip().lower()

    with get_connection(database_path) as connection:
        return connection.execute(
            "SELECT id, email, password_hash, is_admin FROM users WHERE email = ?",
            (normalized_email,),
        ).fetchone()


def verify_user(database_path, email, password):
    user = get_user_by_email(database_path, email)
    if user is None:
        return None

    if not check_password_hash(user["password_hash"], password):
        return None

    return {"id": user["id"], "email": user["email"], "is_admin": bool(user["is_admin"])}


def get_user_by_id(database_path, user_id):
    # Read the current role from SQLite instead of relying on a cached session role.
    with get_connection(database_path) as connection:
        return connection.execute(
            "SELECT id, email, is_admin FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def list_accounts_by_role(database_path, is_admin):
    # Expose only the fields needed for the account picker and admin list.
    with get_connection(database_path) as connection:
        return connection.execute(
            "SELECT id, email, created_at FROM users WHERE is_admin = ? ORDER BY email",
            (int(is_admin),),
        ).fetchall()


def add_admin_account(database_path, actor_id, mode, email, password=""):
    email = email.strip().lower()
    if mode not in ("existing", "new"):
        raise ValueError("Choose an existing account or create a new account.")
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Enter a valid email address.")
    if mode == "new" and not 8 <= len(password) <= 128:
        raise ValueError("Use a password between 8 and 128 characters.")
    password_hash = generate_password_hash(password) if mode == "new" else None
    with get_connection(database_path) as connection:
        # Serialize role changes and recheck the actor's current role while locked.
        connection.execute("BEGIN IMMEDIATE")
        actor = connection.execute("SELECT is_admin FROM users WHERE id = ?", (actor_id,)).fetchone()
        if actor is None or not actor["is_admin"]:
            raise PermissionError("Admin access is required.")
        account = connection.execute("SELECT id, is_admin FROM users WHERE email = ?", (email,)).fetchone()
        if mode == "new":
            if account is not None:
                raise ValueError("This email already has an account. Use Add existing account.")
            connection.execute(
                "INSERT INTO users (email, password_hash, created_at, is_admin) VALUES (?, ?, ?, 1)",
                (email, password_hash, datetime.now(timezone.utc).isoformat()),
            )
        else:
            if account is None:
                raise ValueError("Account not found. Create a new account instead.")
            if account["is_admin"]:
                raise ValueError("This account is already an admin.")
            # Promotion preserves the existing user's password and account data.
            connection.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (account["id"],))
            # Direct promotion resolves any existing request in the same transaction.
            connection.execute(
                """UPDATE admin_access_requests SET status = 'approved', reviewed_at = ?, reviewed_by = ?
                   WHERE user_id = ? AND status != 'approved'""",
                (datetime.now(timezone.utc).isoformat(), actor_id, account["id"]),
            )
    return email


def remove_admin_access(database_path, actor_id, target_id):
    with get_connection(database_path) as connection:
        # Keep the authorization, last-admin check, and role update atomic.
        connection.execute("BEGIN IMMEDIATE")
        actor = connection.execute("SELECT is_admin FROM users WHERE id = ?", (actor_id,)).fetchone()
        if actor is None or not actor["is_admin"]:
            raise PermissionError("Admin access is required.")
        target = connection.execute("SELECT email, is_admin FROM users WHERE id = ?", (target_id,)).fetchone()
        if target is None or not target["is_admin"]:
            raise ValueError("This account is no longer an admin.")
        count = connection.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1").fetchone()[0]
        if count <= 1:
            raise ValueError("The last admin cannot be removed.")
        if actor_id == target_id:
            raise ValueError("You cannot remove your own admin access.")
        # Remove the role, not the account or its documents. Existing sessions are
        # denied admin access on their next request by the blueprint guard.
        connection.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (target_id,))
        return target["email"]


def get_admin_request(database_path, user_id):
    with get_connection(database_path) as connection:
        return connection.execute(
            "SELECT * FROM admin_access_requests WHERE user_id = ?", (user_id,)
        ).fetchone()


def request_admin_access(database_path, user_id, reason):
    # Only existing non-admin users can apply. Duplicate submissions preserve the
    # original request, including a previous approval or rejection.
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO admin_access_requests (user_id, reason, requested_at)
            SELECT id, ?, ? FROM users WHERE id = ? AND is_admin = 0
            ON CONFLICT(user_id) DO NOTHING
            """,
            (reason, datetime.now(timezone.utc).isoformat(), user_id),
        )
        return cursor.rowcount == 1


def list_admin_requests(database_path):
    # Include account emails for display and show the newest requests first.
    with get_connection(database_path) as connection:
        return connection.execute(
            """
            SELECT r.*, u.email, u.is_admin FROM admin_access_requests r
            JOIN users u ON u.id = r.user_id
            ORDER BY r.requested_at DESC, r.id DESC
            """
        ).fetchall()


def decide_admin_request(database_path, request_id, reviewer_id, decision):
    # The UPDATE below checks the reviewer's role, blocks self-approval, and only
    # changes pending requests, so competing reviewers cannot both save a decision.
    if decision not in ("approved", "rejected"):
        return False
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE admin_access_requests SET status = ?, reviewed_at = ?, reviewed_by = ?
            WHERE id = ? AND status = 'pending' AND user_id != ?
              AND EXISTS (SELECT 1 FROM users WHERE id = ? AND is_admin = 1)
              AND EXISTS (SELECT 1 FROM users WHERE id = admin_access_requests.user_id AND is_admin = 0)
            """,
            (decision, datetime.now(timezone.utc).isoformat(), reviewer_id,
             request_id, reviewer_id, reviewer_id),
        )
        if cursor.rowcount != 1:
            return False
        # Save approval and the role change in one transaction: both succeed or
        # both roll back. Rejection leaves the user's role intact.
        if decision == "approved":
            connection.execute(
                """UPDATE users SET is_admin = 1
                   WHERE id = (SELECT user_id FROM admin_access_requests WHERE id = ?)""",
                (request_id,),
            )
        return True
