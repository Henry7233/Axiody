import io

from app import create_app
from app.models.documents import init_document_db
from app.models.users import create_user, init_user_db


def test_client_upload_rejects_files_over_50mb(tmp_path):
    app = create_app()
    app.config["DATABASE"] = tmp_path / "users.db"
    init_user_db(app.config["DATABASE"])
    init_document_db(app.config["DATABASE"])

    user = create_user(app.config["DATABASE"], "client@example.com", "Password1!", "client", full_name="Client User")
    assert user is not None

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = user["id"]
            session["account_type"] = "client"
            session["user_email"] = user["email"]
            session["user_name"] = user["full_name"]

        response = client.post(
            "/client/upload",
            data={
                "title": "Invoice",
                "description": "",
                "document_date": "2026-09-01",
                "document_files_1": (io.BytesIO(b"x" * (50 * 1024 * 1024 + 1)), "invoice.pdf"),
            },
            content_type="multipart/form-data",
        )

    assert response.status_code == 400
    with client.session_transaction() as session:
        messages = session.get("_flashes", [])

    assert any("50MB" in message.lower() or "50 MB" in message.lower() or "smaller file" in message.lower()
               for category, message in messages)
