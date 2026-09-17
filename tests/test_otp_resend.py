from app import create_app
from app.models.documents import init_document_db
from app.models.users import create_user, init_user_db
from app.routes.auth import PENDING_PASSWORD_RESETS


def test_password_reset_resend_is_single_active_code(tmp_path):
    app = create_app()
    app.config["DATABASE"] = tmp_path / "users.db"
    init_user_db(app.config["DATABASE"])
    init_document_db(app.config["DATABASE"])

    user = create_user(
        app.config["DATABASE"],
        "reset@example.com",
        "Password1!",
        "client",
        full_name="Reset User",
    )
    assert user is not None

    with app.test_client() as client:
        response = client.post("/forgot-password", data={"email": user["email"]})
        assert response.status_code == 302

        first_resend = client.post("/resend-otp")
        second_resend = client.post("/resend-otp")

        assert first_resend.status_code == 429
        assert second_resend.status_code == 429
        assert len(PENDING_PASSWORD_RESETS) == 1
