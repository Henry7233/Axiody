import sqlite3
from datetime import datetime, timezone


def get_connection(database_path):
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_document_db(database_path):
    with get_connection(database_path) as connection:
        create_documents_table(connection)
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

        if "user_id" not in column_names:
            connection.execute("ALTER TABLE documents ADD COLUMN user_id INTEGER")
        if "description" not in column_names:
            connection.execute("ALTER TABLE documents ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        if "document_date" not in column_names:
            connection.execute("ALTER TABLE documents ADD COLUMN document_date TEXT NOT NULL DEFAULT ''")
        if "filename" not in column_names:
            connection.execute("ALTER TABLE documents ADD COLUMN filename TEXT NOT NULL DEFAULT ''")
        if "file_type" not in column_names:
            connection.execute("ALTER TABLE documents ADD COLUMN file_type TEXT NOT NULL DEFAULT ''")
        if "file_size" not in column_names:
            connection.execute("ALTER TABLE documents ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0")
        if "file_data" not in column_names:
            connection.execute("ALTER TABLE documents ADD COLUMN file_data BLOB")
        if "classification_status" not in column_names:
            connection.execute(
                "ALTER TABLE documents ADD COLUMN classification_status TEXT NOT NULL DEFAULT 'Pending'"
            )
        if "created_at" not in column_names:
            connection.execute("ALTER TABLE documents ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
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
    created_at = datetime.now(timezone.utc).isoformat()

    with get_connection(database_path) as connection:
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
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                created_at,
            ),
        )

        return cursor.lastrowid


def list_documents(database_path):
    with get_connection(database_path) as connection:
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
