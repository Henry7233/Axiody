from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.models.users import create_user, verify_user


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")

        user = verify_user(current_app.config["DATABASE"], email, password)
        if user is None:
            flash("Invalid email or password.", "error")
            return render_template("auth/login.html", email=email), 401

        session.clear()
        session["user_id"] = user["id"]
        session["user_email"] = user["email"]
        flash("You are logged in.", "success")
        return redirect(url_for("auth.dashboard"))

    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("auth/register.html", email=email), 400

        user = create_user(current_app.config["DATABASE"], email, password)
        if user is None:
            flash("An account with that email already exists.", "error")
            return render_template("auth/register.html", email=email), 409

        session.clear()
        session["user_id"] = user["id"]
        session["user_email"] = user["email"]
        flash("Account created. You are logged in.", "success")
        return redirect(url_for("auth.dashboard"))

    return render_template("auth/register.html")


@auth_bp.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("auth.login"))

    return render_template("auth/dashboard.html", email=session["user_email"])


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You are logged out.", "success")
    return redirect(url_for("auth.login"))
