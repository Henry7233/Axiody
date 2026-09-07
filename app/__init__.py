from flask import Flask, redirect, url_for

from app.models.users import init_user_db
from app.routes.auth import auth_bp
from app.routes.client import client_bp
from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    init_user_db(app.config["DATABASE"])
    app.register_blueprint(auth_bp)
    app.register_blueprint(client_bp)

    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    return app
