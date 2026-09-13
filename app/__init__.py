from flask import Flask, redirect, session, url_for

from app.models.documents import init_document_db
from app.models.users import init_user_db
from app.agents.reminder_agent import process_due_reminders
from app.routes.admin import admin_bp
from app.routes.auth import auth_bp
from app.routes.client import client_bp
from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    init_user_db(app.config["DATABASE"])
    init_document_db(app.config["DATABASE"])
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(client_bp)

    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    @app.route("/settings")
    def settings():
        if "user_id" not in session:
            return redirect(url_for("auth.login"))

        if session.get("account_type") == "admin":
            return redirect(url_for("admin.settings"))

        return redirect(url_for("client.settings"))

    @app.cli.command("process-reminders")
    def process_reminders_command():
        """Send due incomplete-document reminders."""
        result = process_due_reminders(app.config["DATABASE"], app.config)
        print(
            f"Reminder run complete: {result['sent']} sent, "
            f"{result['resolved']} resolved."
        )

    return app
