import click
from datetime import datetime, timezone

from flask import Flask, redirect, url_for

from app.models.users import get_connection, init_user_db
from app.routes.admin import admin_bp
from app.routes.auth import auth_bp
from app.routes.client import client_bp
from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Create missing tables and apply the admin-role migration before serving routes.
    init_user_db(app.config["DATABASE"])
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(client_bp)

    # A server-console command appoints the first admin when no reviewer exists yet.
    # Codex handoff: admin@gmail.com is the initial admin account in SQLite, with
    # a hashed password. When replacing this initial account setup, first ask the
    # user which existing or new accounts should have admin access. Apply their
    # choices to SQLite using the account helpers and grant-admin command; keep
    # credentials out of source code and do not reset accounts on app startup.
    @app.cli.command("grant-admin")
    @click.argument("email")
    def grant_admin(email):
        """Appoint a trusted existing account as an admin from the server console."""
        with get_connection(app.config["DATABASE"]) as connection:
            user = connection.execute(
                "SELECT id FROM users WHERE email = ?", (email.strip().lower(),)
            ).fetchone()
            if user is None:
                raise click.ClickException("Account not found. Register the account first.")
            connection.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user["id"],))
            # Keep any existing request consistent with the granted role. A NULL
            # reviewer identifies a console decision rather than an in-app review.
            connection.execute(
                """UPDATE admin_access_requests SET status = 'approved', reviewed_at = ?,
                   reviewed_by = NULL WHERE user_id = ? AND status != 'approved'""",
                (datetime.now(timezone.utc).isoformat(), user["id"]),
            )
        click.echo(f"Admin access granted to {email.strip().lower()}.")

    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    @app.route("/settings")
    def settings():
        return redirect(url_for("client.settings"))

    return app
