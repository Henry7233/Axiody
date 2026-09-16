"""Document persistence, classification state, and bookkeeping readiness rules."""

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime

from app.time import singapore_now

DOCUMENT_TYPES = ("Invoice", "Receipt", "Bank Statement", "Other")
DOCUMENT_TYPE_LABELS = {
    "invoice": "Invoice",
    "receipt": "Receipt",
    "bank statement": "Bank Statement",
    "banking statement": "Bank Statement",
    "other": "Other",
    "others": "Other",
}


def document_filename_stem(filename):
    """Keep the exact filename, excluding only its final format extension."""
    return os.path.splitext(filename or "")[0]


def normalize_document_type(document_type):
    if not document_type:
        return "Other"
    normalized = document_type.strip().lower().replace("_", " ")
    return DOCUMENT_TYPE_LABELS.get(normalized, document_type.strip())


def is_under_review_status(status):
    return (status or "").strip().lower().replace(" ", "_") == "under_review"


def document_category(document):
    stored_type = (document["document_type"] or "").strip()
    return normalize_document_type(stored_type or document["ai_document_type"] or "Other")


def needs_document_approval(document):
    if document_validation_status(document["validation_status"]) != "Complete":
        return False
    status = (document["classification_status"] or "").strip().lower()
    if status == "success" and document["reviewed_by"] is not None:
        return False
    if status != "success" and not is_under_review_status(status):
        return False
    # Keep an Other document in review when an admin saves a category correction.
    return document_category(document) == "Other" or (
        is_under_review_status(status)
        and bool((document["ai_document_type"] or "").strip())
        and normalize_document_type(document["ai_document_type"]) == "Other"
    )


def is_bookkeeping_ready(document):
    if document_validation_status(document["validation_status"]) != "Complete":
        return False
    if needs_document_approval(document):
        return False
    category = document_category(document)
    status = (document["classification_status"] or "").strip().lower()
    if category == "Other":
        return status == "success" and document["reviewed_by"] is not None
    # Older standard classifications may still carry the confidence-based status.
    return category in DOCUMENT_TYPES and (status == "success" or is_under_review_status(status))


def get_connection(database_path):
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.create_function("filename_stem", 1, document_filename_stem, deterministic=True)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_document_db(database_path):
    with closing(get_connection(database_path)) as connection, connection:
        create_documents_table(connection)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                notification_type TEXT NOT NULL DEFAULT 'reminder',
                status TEXT NOT NULL DEFAULT 'unread',
                last_reminder_sent TIMESTAMP,
                next_reminder_date DATE,
                reminder_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            )
            """
        )
        notification_columns = {
            column["name"]
            for column in connection.execute("PRAGMA table_info(notifications)").fetchall()
        }
        if "notification_type" not in notification_columns:
            connection.execute(
                "ALTER TABLE notifications ADD COLUMN notification_type TEXT NOT NULL DEFAULT 'reminder'"
            )
        columns = connection.execute("PRAGMA table_info(documents)").fetchall()
        column_names = {column["name"] for column in columns}
        foreign_keys = connection.execute("PRAGMA foreign_key_list(documents)").fetchall()
        has_user_link = any(
            foreign_key["from"] == "user_id" and foreign_key["table"] == "users"
            for foreign_key in foreign_keys
        )
        row_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

        if row_count == 0 and (not has_user_link or "file_data" not in column_names):
            connection.execute("DROP TABLE documents")
            create_documents_table(connection)
            column_names = {
                column["name"]
                for column in connection.execute("PRAGMA table_info(documents)").fetchall()
            }

        column_updates = (
            ("user_id", "ALTER TABLE documents ADD COLUMN user_id INTEGER"),
            ("description", "ALTER TABLE documents ADD COLUMN description TEXT NOT NULL DEFAULT ''"),
            ("document_date", "ALTER TABLE documents ADD COLUMN document_date TEXT NOT NULL DEFAULT ''"),
            ("filename", "ALTER TABLE documents ADD COLUMN filename TEXT NOT NULL DEFAULT ''"),
            ("file_type", "ALTER TABLE documents ADD COLUMN file_type TEXT NOT NULL DEFAULT ''"),
            ("file_size", "ALTER TABLE documents ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0"),
            ("file_data", "ALTER TABLE documents ADD COLUMN file_data BLOB"),
            ("ai_document_type", "ALTER TABLE documents ADD COLUMN ai_document_type TEXT"),
            ("ai_confidence", "ALTER TABLE documents ADD COLUMN ai_confidence REAL"),
            ("document_type", "ALTER TABLE documents ADD COLUMN document_type TEXT"),
            (
                "classification_status",
                "ALTER TABLE documents ADD COLUMN classification_status TEXT NOT NULL DEFAULT 'Pending'",
            ),
            ("validation_status", "ALTER TABLE documents ADD COLUMN validation_status TEXT"),
            (
                "validation_reasons",
                "ALTER TABLE documents ADD COLUMN validation_reasons TEXT NOT NULL DEFAULT '[]'",
            ),
            ("created_at", "ALTER TABLE documents ADD COLUMN created_at TEXT NOT NULL DEFAULT ''"),
            ("reviewed_by", "ALTER TABLE documents ADD COLUMN reviewed_by INTEGER REFERENCES users(id)"),
            ("reviewed_at", "ALTER TABLE documents ADD COLUMN reviewed_at TEXT"),
        )
        for column_name, alter_statement in column_updates:
            if column_name not in column_names:
                connection.execute(alter_statement)

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_documents_user_id
            ON documents(user_id)
            """
        )


def create_documents_table(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            document_date TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL DEFAULT '',
            file_size INTEGER NOT NULL DEFAULT 0,
            file_data BLOB NOT NULL,
            ai_document_type TEXT,
            ai_confidence REAL,
            document_type TEXT,
            classification_status TEXT NOT NULL DEFAULT 'Pending',
            validation_status TEXT,
            validation_reasons TEXT NOT NULL DEFAULT '[]',
            reviewed_by INTEGER,
            reviewed_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (reviewed_by) REFERENCES users(id)
        )
        """
    )


def create_document(
    database_path,
    user_id,
    title,
    description,
    document_date,
    filename,
    content_type,
    file_data,
):
    """Save one current upload per client, record month, and filename stem."""
    created_at = singapore_now().isoformat()

    with closing(get_connection(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            """
            SELECT id FROM documents
            WHERE user_id = ? AND title = ?
              AND SUBSTR(document_date, 1, 7) = ?
              AND filename_stem(filename) = ?
            ORDER BY id DESC LIMIT 1
            """,
            (user_id, title.strip(), document_date[:7], document_filename_stem(filename)),
        ).fetchone()
        if existing is not None:
            document_id = existing["id"]
            connection.execute(
                """
                UPDATE documents
                SET description = ?, document_date = ?, filename = ?, file_type = ?,
                    file_size = ?, file_data = ?, created_at = ?,
                    ai_document_type = NULL, ai_confidence = NULL, document_type = NULL,
                    classification_status = 'Pending', validation_status = NULL,
                    validation_reasons = '[]', reviewed_by = NULL, reviewed_at = NULL
                WHERE id = ?
                """,
                (description.strip(), document_date, filename, content_type or "",
                 len(file_data), file_data, created_at, document_id),
            )
            connection.execute(
                """
                UPDATE notifications SET status = 'resolved', next_reminder_date = NULL
                WHERE document_id = ?
                """,
                (document_id,),
            )
            return document_id

        cursor = connection.execute(
            """
            INSERT INTO documents (
                user_id,
                title,
                description,
                document_date,
                filename,
                file_type,
                file_size,
                file_data,
                classification_status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                title.strip(),
                description.strip(),
                document_date,
                filename,
                content_type or "",
                len(file_data),
                file_data,
                "Pending",
                created_at,
            ),
        )

        return cursor.lastrowid


def update_document_classification(database_path, document_id, classification):
    with closing(get_connection(database_path)) as connection, connection:
        connection.execute(
            """
            UPDATE documents
            SET ai_document_type = ?,
                ai_confidence = ?,
                document_type = ?,
                classification_status = ?
            WHERE id = ?
            """,
            (
                classification["ai_document_type"],
                classification["ai_confidence"],
                classification["document_type"],
                classification["classification_status"],
                document_id,
            ),
        )


def _apply_document_validation(connection, document_id, validation):
    """Apply validation and resolve replaced-file reminders in one transaction."""
    validation_status = validation["validation_status"]
    connection.execute(
        """
        UPDATE documents
        SET validation_status = ?,
            validation_reasons = ?,
            ai_confidence = ?
        WHERE id = ?
        """,
        (
            validation_status,
            json.dumps(validation.get("reasons", []) if validation_status != "Complete" else []),
            validation["ai_confidence"],
            document_id,
        ),
    )
    if validation_status == "Complete":
        connection.execute(
            """
            UPDATE documents
            SET validation_status = 'Complete', validation_reasons = '[]'
            WHERE user_id = (
                SELECT user_id FROM documents WHERE id = ?
            )
              AND title = (
                SELECT title FROM documents WHERE id = ?
              )
              AND SUBSTR(document_date, 1, 7) = (
                SELECT SUBSTR(document_date, 1, 7) FROM documents WHERE id = ?
              )
              AND filename_stem(filename) = filename_stem(
                (SELECT filename FROM documents WHERE id = ?)
              )
              AND LOWER(COALESCE(TRIM(validation_status), '')) = 'incomplete'
            """,
            (document_id, document_id, document_id, document_id),
        )
        connection.execute(
            """
            UPDATE notifications SET status = 'resolved', next_reminder_date = NULL
            WHERE document_id IN (
                SELECT older.id FROM documents older
                JOIN documents current ON current.id = ?
                WHERE older.user_id = current.user_id
                  AND older.title = current.title
                  AND SUBSTR(older.document_date, 1, 7) = SUBSTR(current.document_date, 1, 7)
                  AND filename_stem(older.filename) = filename_stem(current.filename)
                  AND older.id <= current.id
            )
            """,
            (document_id,),
        )


def update_document_validation(database_path, document_id, validation):
    with closing(get_connection(database_path)) as connection, connection:
        _apply_document_validation(connection, document_id, validation)


def update_document_results(database_path, document_id, classification, validation):
    """Save both AI results together to avoid multiple SQLite transactions per upload."""
    with closing(get_connection(database_path)) as connection, connection:
        connection.execute(
            """
            UPDATE documents
            SET ai_document_type = ?,
                ai_confidence = ?,
                document_type = ?,
                classification_status = ?
            WHERE id = ?
            """,
            (
                classification["ai_document_type"],
                classification["ai_confidence"],
                classification["document_type"],
                classification["classification_status"],
                document_id,
            ),
        )
        _apply_document_validation(connection, document_id, validation)


def document_validation_status(value):
    return {"complete": "Complete", "incomplete": "Incomplete"}.get(
        (value or "").strip().lower(), "Pending validation"
    )


def document_status_for_notification(document):
    """Return the user-visible document status for notifications."""
    validation_status = document_validation_status(document.get("validation_status"))
    if validation_status == "Complete" and normalize_document_type(
        document.get("document_type") or document.get("ai_document_type") or "Other"
    ) == "Other":
        return "Under review"
    return validation_status


def validation_messages(value):
    """Summarize a document's saved validation reasons in one sentence."""
    try:
        reasons = json.loads(value or "[]")
    except (TypeError, ValueError):
        reasons = []
    if not isinstance(reasons, list):
        reasons = []
    reasons = list(dict.fromkeys(
        reason.strip()
        for reason in reasons if isinstance(reason, str) and reason.strip()
    ))
    return [f"This document contains {', '.join(reasons)}."] if reasons else []


def list_client_document_records(database_path, user_id, period):
    """Group the latest files by title and month, optionally across all dates."""
    start_date = end_date = None
    if period != "all":
        start = datetime.strptime(period, "%Y-%m")
        end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
        start_date, end_date = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    connection = get_connection(database_path)
    try:
        rows = connection.execute(
            """
            SELECT id, title, description, filename, document_date, created_at,
                   document_type, ai_document_type, validation_status, validation_reasons
            FROM documents current_document
            WHERE user_id = ? AND (? IS NULL OR (document_date >= ? AND document_date < ?))
              AND NOT EXISTS (
                  SELECT 1 FROM documents newer
                  WHERE newer.user_id = current_document.user_id
                    AND newer.title = current_document.title
                    AND SUBSTR(newer.document_date, 1, 7) = SUBSTR(current_document.document_date, 1, 7)
                    AND filename_stem(newer.filename) = filename_stem(current_document.filename)
                    AND newer.id > current_document.id
              )
            ORDER BY created_at DESC, id DESC
            """,
            (user_id, start_date, start_date, end_date),
        ).fetchall()
    finally:
        connection.close()

    records = {}
    for row in rows:
        document = dict(row)
        stored_type = (document["document_type"] or document["ai_document_type"] or "").strip()
        document["type"] = normalize_document_type(stored_type)
        document["status"] = document_validation_status(document["validation_status"])
        document["completed"] = document["status"] == "Complete"
        document["reasons"] = validation_messages(document["validation_reasons"]) if document["status"] == "Incomplete" else []
        document_period = (document["document_date"] or "")[:7]
        try:
            period_label = datetime.strptime(document_period, "%Y-%m").strftime("%B %Y")
        except ValueError:
            period_label = "Date not recorded"
        record = records.setdefault((document["title"], document_period), {
            "id": document["id"], "name": document["title"],
            "description": document["description"],
            "period_label": period_label,
            "groups": {}, "file_count": 0, "completed_count": 0,
        })
        record["groups"].setdefault(document["type"], []).append(document)
        record["file_count"] += 1
        record["completed_count"] += document["completed"]
    return list(records.values())


def approval_record(row):
    document = dict(row)
    document["category"] = document_category(document)
    document["submission_date"] = (document["created_at"] or "")[:10]
    document["is_under_review"] = needs_document_approval(document)
    return document


def get_approval_documents(database_path, document_id=None):
    """Load review metadata without copying uploaded file blobs into the queue."""
    with closing(get_connection(database_path)) as connection:
        rows = connection.execute(
            """
            SELECT d.id, d.title, d.description, d.filename, d.file_type,
                   d.document_date, d.document_type, d.ai_document_type,
                   d.ai_confidence, d.classification_status, d.validation_status,
                   d.created_at, d.reviewed_by, d.reviewed_at,
                   COALESCE(NULLIF(TRIM(u.full_name), ''), u.email) AS submitter
            FROM documents d JOIN users u ON u.id = d.user_id
            WHERE """ + ("1 = 1" if document_id is None else "d.id = ?") + """
              AND LOWER(TRIM(COALESCE(d.validation_status, ''))) = 'complete'
            ORDER BY d.created_at DESC, d.id DESC
            """,
            () if document_id is None else (document_id,),
        ).fetchall()
    return [approval_record(row) for row in rows if needs_document_approval(row)
            or (document_id is not None and is_bookkeeping_ready(row))]


def save_document_review(database_path, document_id, reviewer_id, action, changes):
    """Save corrections and decisions atomically, only while review is pending."""
    with closing(get_connection(database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        document = connection.execute(
            """SELECT classification_status, validation_status, document_type,
                      ai_document_type, reviewed_by FROM documents WHERE id = ?""", (document_id,)
        ).fetchone()
        if document is None:
            return "missing"
        if document_validation_status(document["validation_status"]) != "Complete":
            return "incomplete"
        if not needs_document_approval(document):
            return "reviewed"
        if action == "rejected":
            connection.execute(
                """
                UPDATE documents
                SET classification_status = 'Rejected', reviewed_by = ?, reviewed_at = ?
                WHERE id = ?
                """,
                (reviewer_id, singapore_now().isoformat(), document_id),
            )
            return "ok"
        assignments, values = [], []
        for field in ("title", "description", "document_date", "document_type"):
            if field in changes:
                assignments.append(f"{field} = ?")
                values.append(changes[field])
        if action == "approved":
            assignments.append("classification_status = ?")
            values.append("Success")
            assignments.extend(("reviewed_by = ?", "reviewed_at = ?"))
            values.extend((reviewer_id, singapore_now().isoformat()))
        else:
            assignments.append("classification_status = ?")
            values.append("Under review")
            if not (document["ai_document_type"] or "").strip():
                assignments.append("ai_document_type = ?")
                values.append(document_category(document))
        values.append(document_id)
        connection.execute(
            "UPDATE documents SET " + ", ".join(assignments) + " WHERE id = ?", values
        )
    return "ok"


def list_documents(database_path):
    with closing(get_connection(database_path)) as connection, connection:
        return [
            {
                "id": document["id"],
                "title": document["title"],
                "submitter": document["submitter"] or document["email"],
                "submission_date": document["created_at"][:10],
                "filename": document["filename"],
                "status": document["status"],
            }
            for document in connection.execute(
                """
                SELECT
                    documents.id,
                    documents.title,
                    documents.filename,
                    documents.classification_status AS status,
                    documents.created_at,
                    users.full_name AS submitter,
                    users.email AS email
                FROM documents
                JOIN users ON users.id = documents.user_id
                ORDER BY documents.created_at DESC, documents.id DESC
                """
            ).fetchall()
        ]


def list_client_summaries(database_path):
    with closing(get_connection(database_path)) as connection, connection:
        rows = connection.execute(
            """
            SELECT
                users.id,
                users.email,
                COALESCE(NULLIF(users.full_name, ''), users.email) AS name,
                COUNT(documents.id) AS documents,
                SUM(CASE WHEN documents.classification_status = 'Success' THEN 1 ELSE 0 END) AS classified,
                SUM(CASE WHEN documents.classification_status = 'Under review' THEN 1 ELSE 0 END) AS needs_review
            FROM users
            LEFT JOIN documents ON documents.user_id = users.id
            WHERE users.account_type = 'client'
            GROUP BY users.id, users.full_name, users.email
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()

    summaries = []
    for row in rows:
        documents = row["documents"]
        classified = row["classified"] or 0
        needs_review = row["needs_review"] or 0
        if needs_review:
            status = "Needs review"
        elif not documents:
            status = "Pending files"
        elif classified == documents:
            status = "Complete"
        else:
            status = "Ready"
        summaries.append(
            {
                "id": row["id"],
                "name": row["name"],
                "email": row["email"],
                "status": status,
                "documents": documents,
                "classified": classified,
                "needs_review": needs_review,
            }
        )
    return summaries


def get_client_review_data(database_path, client_name):
    with closing(get_connection(database_path)) as connection, connection:
        client = connection.execute(
            """
            SELECT
                users.id,
                COALESCE(NULLIF(users.full_name, ''), users.email) AS name,
                users.email
            FROM users
            WHERE users.account_type = 'client'
              AND (users.full_name = ? OR users.email = ?)
            LIMIT 1
            """,
            (client_name, client_name),
        ).fetchone()

        if client is None:
            return {"name": client_name, "email": ""}, []

        documents = connection.execute(
            """
            SELECT
                id,
                filename,
                COALESCE(document_type, ai_document_type, 'Other') AS classification_type,
                COALESCE(ai_confidence, 0) / 100.0 AS classification_confidence,
                validation_status
            FROM documents
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (client["id"],),
        ).fetchall()

    return (
        {"name": client["name"], "email": client["email"]},
        [
            {
                "id": document["id"],
                "stored_filename": document["filename"],
                "classification_type": document["classification_type"],
                "classification_confidence": document["classification_confidence"],
                "validation_status": document["validation_status"],
            }
            for document in documents
        ],
    )
