from app import create_app
from app.models.documents import init_document_db, list_client_summaries
from app.models.users import create_user, init_user_db


def test_client_summary_bookkept_matches_bookkeeping_ready_logic(tmp_path):
    app = create_app()
    app.config["DATABASE"] = tmp_path / "users.db"
    init_user_db(app.config["DATABASE"])
    init_document_db(app.config["DATABASE"])

    user = create_user(app.config["DATABASE"], "summary@example.com", "Password1!", "client", full_name="Summary User")
    assert user is not None

    with app.app_context():
        import sqlite3

        with sqlite3.connect(app.config["DATABASE"]) as conn:
            conn.execute(
                """
                INSERT INTO documents (
                    user_id, title, description, document_date, filename, file_type,
                    file_size, file_data, ai_document_type, ai_confidence, document_type,
                    classification_status, validation_status, validation_reasons, reviewed_by,
                    reviewed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    "Invoice 1",
                    "",
                    "2026-09-01",
                    "invoice1.pdf",
                    "application/pdf",
                    100,
                    b"x",
                    "Invoice",
                    0.98,
                    "Invoice",
                    "Success",
                    "Complete",
                    "[]",
                    None,
                    None,
                    "2026-09-01T00:00:00",
                ),
            )
            conn.execute(
                """
                INSERT INTO documents (
                    user_id, title, description, document_date, filename, file_type,
                    file_size, file_data, ai_document_type, ai_confidence, document_type,
                    classification_status, validation_status, validation_reasons, reviewed_by,
                    reviewed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    "Other 1",
                    "",
                    "2026-09-02",
                    "other1.pdf",
                    "application/pdf",
                    100,
                    b"y",
                    "Other",
                    0.9,
                    "Other",
                    "Success",
                    "Complete",
                    "[]",
                    user["id"],
                    "2026-09-02T00:00:00",
                    "2026-09-02T00:00:00",
                ),
            )
            conn.execute(
                """
                INSERT INTO documents (
                    user_id, title, description, document_date, filename, file_type,
                    file_size, file_data, ai_document_type, ai_confidence, document_type,
                    classification_status, validation_status, validation_reasons, reviewed_by,
                    reviewed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    "Other 2",
                    "",
                    "2026-09-03",
                    "other2.pdf",
                    "application/pdf",
                    100,
                    b"z",
                    "Other",
                    0.9,
                    "Other",
                    "Under review",
                    "Complete",
                    "[]",
                    None,
                    None,
                    "2026-09-03T00:00:00",
                ),
            )
            conn.execute(
                """
                INSERT INTO documents (
                    user_id, title, description, document_date, filename, file_type,
                    file_size, file_data, ai_document_type, ai_confidence, document_type,
                    classification_status, validation_status, validation_reasons, reviewed_by,
                    reviewed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    "Invoice 2",
                    "",
                    "2026-09-04",
                    "invoice2.pdf",
                    "application/pdf",
                    100,
                    b"w",
                    "Invoice",
                    0.91,
                    "Invoice",
                    "Success",
                    "Incomplete",
                    "[]",
                    None,
                    None,
                    "2026-09-04T00:00:00",
                ),
            )

    summaries = list_client_summaries(app.config["DATABASE"])
    assert len(summaries) == 1
    assert summaries[0]["documents"] == 4
    assert summaries[0]["classified"] == 2
    assert summaries[0]["needs_review"] == 1
