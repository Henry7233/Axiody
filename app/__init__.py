from flask import Flask, redirect, session, url_for

from app.models.documents import init_document_db
from app.models.users import init_user_db
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

    return app
