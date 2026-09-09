from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.models.users import create_user, verify_user


auth_bp = Blueprint("auth", __name__)


def default_url_for_account(account_type):
    if account_type == "admin":
        return url_for("admin.dashboard")

    return url_for("client.upload")


def wants_json_response():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")

        user = verify_user(current_app.config["DATABASE"], email, password)
        if user is None:
            if wants_json_response():
                return jsonify({"message": "Invalid email or password."}), 401

            flash("Invalid email or password.", "error")
            return render_template("auth/login.html", email=email), 401

        session.clear()
        session["user_id"] = user["id"]
        session["user_email"] = user["email"]
        session["account_type"] = user["account_type"]
        session["protected"] = user["protected"]
        redirect_url = default_url_for_account(user["account_type"])

        if wants_json_response():
            return jsonify(
                {
                    "message": "Your login is successful.",
                    "redirect_url": redirect_url,
                }
            )

        flash("You are logged in.", "success")
        return redirect(redirect_url)

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
        session["account_type"] = user["account_type"]
        session["protected"] = user["protected"]
        flash("Account created. You are logged in.", "success")
        return redirect(url_for("client.upload"))

    return render_template("auth/register.html")


@auth_bp.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("auth.login"))

    return redirect(default_url_for_account(session.get("account_type")))


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You are logged out.", "success")
    return redirect(url_for("auth.login"))
