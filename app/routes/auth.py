from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.models.users import create_user, get_user_by_id, update_user_account, update_user_appearance, verify_user


auth_bp = Blueprint("auth", __name__)


@auth_bp.before_app_request
def load_account():
    """Load the signed-in database account for client and admin requests."""
    g.account = None
    if "user_id" not in session:
        return

    user = get_user_by_id(current_app.config["DATABASE"], session["user_id"])
    if user is None:
        session.clear()
        return

    g.account = {
        key: user[key]
        for key in ("id", "full_name", "email", "account_type", "role", "created_at", "theme", "font_size")
    }
    role = (user["role"] or "").strip()
    g.account["role"] = role if role and role.casefold() not in {"null", "none", "undefined"} else None
    session["account_type"] = user["account_type"]
    session["user_name"] = user["full_name"]
    session["user_email"] = user["email"]
    session["user_role"] = user["role"]
    session["user_role"] = user["role"]


@auth_bp.app_context_processor
def account_context():
    """Supply base.html with the shared account menu and navigation data."""
    account = g.get("account")
    return {
        "current_account": account,
        "home_url": default_url_for_account(account["account_type"] if account else "client"),
        "admin_nav": bool(account and account["account_type"] == "admin"),
    }


def default_url_for_account(account_type):
    if account_type == "admin":
        return url_for("admin.dashboard")

    return url_for("client.dashboard")


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
        session["user_name"] = user["full_name"]
        session["user_email"] = user["email"]
        session["user_role"] = user["role"]
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
        full_name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "").strip()

        if not full_name:
            flash("Full name is required.", "error")
            return render_template("auth/register.html", name=full_name, email=email, role=role), 400

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("auth/register.html", name=full_name, email=email, role=role), 400

        user = create_user(
            current_app.config["DATABASE"],
            email,
            password,
            account_type="client",
            full_name=full_name,
            role=role or "Client",
        )
        if user is None:
            flash("An account with that email already exists.", "error")
            return render_template("auth/register.html", name=full_name, email=email, role=role), 409

        session.clear()
        session["user_id"] = user["id"]
        session["user_name"] = user["full_name"]
        session["user_email"] = user["email"]
        session["user_role"] = user["role"]
        session["account_type"] = user["account_type"]
        session["protected"] = user["protected"]
        flash("Account created. You are logged in.", "success")
        return redirect(url_for("client.dashboard"))

    return render_template("auth/register.html")


@auth_bp.route("/account", methods=["POST"])
def update_account():
    if "user_id" not in session:
        return jsonify({"message": "Please log in first."}), 401

    full_name = (request.form.get("full_name", "") or request.form.get("name", "")).strip()
    email = (request.form.get("email", "") or "").strip().lower()
    role = request.form.get("role", "").strip()
    password = request.form.get("password", "")
    password_confirmation = request.form.get("password_confirmation", "")

    if not full_name:
        return jsonify({"message": "Enter your full name."}), 400
    if not email:
        return jsonify({"message": "Enter an email address."}), 400
    if password or password_confirmation:
        if len(password) < 8:
            return jsonify({"message": "Use at least 8 characters in the new password."}), 400
        if password != password_confirmation:
            return jsonify({"message": "The new passwords must match."}), 400

    result = update_user_account(
        current_app.config["DATABASE"],
        session["user_id"],
        full_name,
        email,
        password,
        password_confirmation,
        role,
    )

    if not result["updated"]:
        reason = result["reason"]
        if reason == "duplicate_email":
            return jsonify({"message": "An account with that email already exists."}), 409
        if reason == "missing_name":
            return jsonify({"message": "Enter your full name."}), 400
        if reason == "missing_email":
            return jsonify({"message": "Enter an email address."}), 400
        if reason == "password_weak":
            return jsonify({"message": "Use at least 8 characters in the new password."}), 400
        if reason == "password_mismatch":
            return jsonify({"message": "The new passwords must match."}), 400
        return jsonify({"message": "Unable to update your account."}), 400

    session["user_name"] = result["account"]["full_name"]
    session["user_email"] = result["account"]["email"]
    session["user_role"] = result["account"]["role"]
    return jsonify({"message": "Account changes saved.", "account": result["account"]})


@auth_bp.post("/account/appearance")
def update_appearance():
    if g.get("account") is None:
        return jsonify({"message": "Please log in first."}), 401
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"message": "Choose a valid theme and font size."}), 400
    theme, font_size = data.get("theme"), data.get("fontSize")
    if not isinstance(theme, str) or not isinstance(font_size, str) or not update_user_appearance(
        current_app.config["DATABASE"], g.account["id"], theme, font_size
    ):
        return jsonify({"message": "Choose a valid theme and font size."}), 400
    return jsonify({"theme": theme, "fontSize": font_size})


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


@auth_bp.get("/account-menu")
def account_menu():
    # load_account reads this signed-in user's database record on every request.
    account = g.get("account")
    if account is None:
        response = jsonify({"message": "Please log in first."})
        response.status_code = 401
    else:
        response = jsonify({"account_type": account["account_type"], "role": account["role"]})
    response.headers["Cache-Control"] = "no-store"
    return response
