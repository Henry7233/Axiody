from flask import (
    abort,
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
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import smtplib
import secrets
import sqlite3

from app.models.users import create_user, delete_user, get_user_by_email, get_user_by_id, update_user_account, update_user_appearance, update_user_password, verify_user
from app.services.email_servie import EmailConfigError, EmailConnectionError, send_account_update_otp, send_password_reset_otp


auth_bp = Blueprint("auth", __name__)
PENDING_ACCOUNT_UPDATES = {}
PENDING_PASSWORD_RESETS = {}


@auth_bp.before_app_request
def load_account():
    """Load the signed-in database account for client and admin requests."""
    g.account = None
    if "user_id" not in session:
        return

    user = get_user_by_id(current_app.config["DATABASE"], session["user_id"])
    if user is None:
        forget_pending_account_update()
        session.clear()
        return

    g.account = {
        key: user[key]
        for key in ("id", "full_name", "email", "account_type", "role", "protected", "created_at", "theme", "font_size")
    }
    role = (user["role"] or "").strip()
    g.account["role"] = role if role and role.casefold() not in {"null", "none", "undefined"} else None
    session["account_type"] = user["account_type"]
    session["user_name"] = user["full_name"]
    session["user_email"] = user["email"]
    session["user_role"] = user["role"]
    session["protected"] = user["protected"]


@auth_bp.app_context_processor
def account_context():
    """Supply base.html with the shared account menu and navigation data."""
    account = g.get("account")
    is_admin = bool(account and account["account_type"] == "admin")
    is_super_admin = bool(is_admin and account["protected"] in (1, True, "1", "true", "on", "yes"))
    return {
        "current_account": account,
        "home_url": default_url_for_account(account["account_type"] if account else "client"),
        "admin_nav": is_admin,
        "admin_can_manage_admins": is_super_admin,
        "delete_account_token": delete_account_token,
    }


def delete_account_token():
    if "delete_account_token" not in session:
        session["delete_account_token"] = secrets.token_hex(32)
    return session["delete_account_token"]


def default_url_for_account(account_type):
    if account_type == "admin":
        return url_for("admin.dashboard")

    return url_for("client.dashboard")


def store_user_session(user):
    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["full_name"]
    session["user_email"] = user["email"]
    session["user_role"] = user["role"]
    session["account_type"] = user["account_type"]
    session["protected"] = user["protected"]


def wants_json_response():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def otp_digest(code):
    secret = current_app.config["SECRET_KEY"].encode("utf-8")
    return hmac.new(secret, code.encode("utf-8"), hashlib.sha256).hexdigest()


def otp_now():
    return datetime.now(timezone.utc)


def generate_otp():
    return f"{secrets.randbelow(1_000_000):06d}"


def password_is_strong(password):
    return (
        len(password) >= 8
        and any(character.isalpha() for character in password)
        and any(character.isdigit() for character in password)
        and any(not character.isalnum() for character in password)
    )


def send_account_otp(pending):
    code = generate_otp()
    expiry_minutes = current_app.config.get("OTP_EXPIRY_MINUTES", 5)
    pending["otp_hash"] = otp_digest(code)
    pending["expires_at"] = (otp_now() + timedelta(minutes=expiry_minutes)).isoformat()
    pending["attempts"] = 0
    send_account_update_otp(current_app.config, pending["email"], code, expiry_minutes)


def otp_send_error_response(error):
    current_app.logger.exception("Unable to send account update OTP")
    if isinstance(error, EmailConfigError):
        message = "Email settings are not configured. Check your .env mail values."
    elif isinstance(error, smtplib.SMTPAuthenticationError):
        message = "Gmail rejected the email login. Create a new Gmail App Password for MAIL_USERNAME and put it in MAIL_PASSWORD."
    elif isinstance(error, EmailConnectionError):
        message = "Unable to connect to the email server. Outbound SMTP may be blocked, or MAIL_SERVER, MAIL_PORT, and SSL/TLS settings may be wrong."
    elif isinstance(error, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, TimeoutError, OSError)):
        message = "Unable to connect to the email server. Check MAIL_SERVER, MAIL_PORT, and SSL/TLS settings."
    else:
        message = "Unable to send the verification code. Please try again."
    return jsonify({"message": message}), 500


def send_password_reset_code(email):
    code = generate_otp()
    expiry_minutes = current_app.config.get("OTP_EXPIRY_MINUTES", 5)
    pending = {
        "email": email,
        "otp_hash": otp_digest(code),
        "expires_at": (otp_now() + timedelta(minutes=expiry_minutes)).isoformat(),
        "attempts": 0,
    }
    send_password_reset_otp(current_app.config, email, code, expiry_minutes)
    reset_id = secrets.token_urlsafe(24)
    PENDING_PASSWORD_RESETS[reset_id] = pending
    session["password_reset_id"] = reset_id
    return pending


def get_password_reset():
    return PENDING_PASSWORD_RESETS.get(session.get("password_reset_id"))


def forget_password_reset():
    reset_id = session.pop("password_reset_id", None)
    if reset_id:
        PENDING_PASSWORD_RESETS.pop(reset_id, None)


def remember_pending_account_update(pending):
    pending_id = secrets.token_urlsafe(24)
    pending["user_id"] = session["user_id"]
    PENDING_ACCOUNT_UPDATES[pending_id] = pending
    session["pending_account_update_id"] = pending_id


def get_pending_account_update():
    pending_id = session.get("pending_account_update_id")
    pending = PENDING_ACCOUNT_UPDATES.get(pending_id)
    if not pending or pending.get("user_id") != session.get("user_id"):
        return None
    return pending


def forget_pending_account_update():
    pending_id = session.pop("pending_account_update_id", None)
    if pending_id:
        PENDING_ACCOUNT_UPDATES.pop(pending_id, None)


def account_update_payload():
    return {
        "full_name": (request.form.get("full_name", "") or request.form.get("name", "")).strip(),
        "email": (request.form.get("email", "") or "").strip().lower(),
        "role": request.form.get("role", "").strip(),
        "password": request.form.get("password", ""),
        "password_confirmation": request.form.get("password_confirmation", ""),
    }


def validate_account_update_request(payload):
    if not payload["full_name"]:
        return jsonify({"message": "Enter your full name."}), 400
    if not payload["email"]:
        return jsonify({"message": "Enter an email address."}), 400
    if payload["password"] or payload["password_confirmation"]:
        if len(payload["password"]) < 8:
            return jsonify({"message": "Use at least 8 characters in the new password."}), 400
        if payload["password"] != payload["password_confirmation"]:
            return jsonify({"message": "The new passwords must match."}), 400

    existing = get_user_by_email(current_app.config["DATABASE"], payload["email"])
    if existing is not None and existing["id"] != session["user_id"]:
        return jsonify({"message": "An account with that email already exists."}), 409

    return None


def save_verified_account_update(payload):
    result = update_user_account(
        current_app.config["DATABASE"],
        session["user_id"],
        payload["full_name"],
        payload["email"],
        payload["password"],
        payload["password_confirmation"],
        payload["role"],
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
    forget_pending_account_update()
    return jsonify({"message": "Account changes saved.", "account": result["account"]})


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

        forget_pending_account_update()
        store_user_session(user)
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


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = get_user_by_email(current_app.config["DATABASE"], email) if email else None
        if user is None:
            return render_template(
                "auth/forgot_password.html",
                email=email,
                error="No account was found with that email address.",
            ), 404
        try:
            pending = send_password_reset_code(email)
        except Exception as error:
            return otp_send_error_response(error)
        return redirect(url_for("auth.verify_otp", email=pending["email"]))

    return render_template("auth/forgot_password.html", email="")


@auth_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    pending = get_password_reset()
    if not pending:
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form
        code = str(data.get("otp", "")).strip()
        try:
            expires_at = datetime.fromisoformat(pending["expires_at"])
        except (KeyError, ValueError, TypeError):
            forget_password_reset()
            return jsonify({"success": False, "message": "The verification code expired. Start again."}), 400
        if otp_now() > expires_at:
            forget_password_reset()
            return jsonify({"success": False, "message": "The verification code expired. Start again."}), 400
        if not code.isdigit() or len(code) != 6:
            return jsonify({"success": False, "message": "Enter the 6-digit verification code."}), 400
        pending["attempts"] += 1
        if pending["attempts"] > current_app.config.get("OTP_MAX_ATTEMPTS", 5):
            forget_password_reset()
            return jsonify({"success": False, "message": "Too many attempts. Start again."}), 429
        if not hmac.compare_digest(pending["otp_hash"], otp_digest(code)):
            return jsonify({"success": False, "message": "Invalid verification code."}), 400
        session["password_reset_verified"] = True
        return jsonify({"success": True, "redirect_url": url_for("auth.reset_password")})
    return render_template("auth/verify_otp.html", masked_email=pending["email"])


@auth_bp.post("/resend-otp")
def resend_otp():
    pending = get_password_reset()
    if not pending:
        return jsonify({"success": False, "message": "Start the password reset again."}), 400
    try:
        updated = send_password_reset_code(pending["email"])
    except Exception as error:
        return otp_send_error_response(error)
    return jsonify({"success": True, "expires_at": updated["expires_at"]})


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    pending = get_password_reset()
    if not pending or not session.get("password_reset_verified"):
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        password = request.form.get("password", "")
        confirmation = request.form.get("confirm_password", "")
        if not password_is_strong(password):
            return render_template("auth/reset_password.html", error="Use at least 8 characters with a letter, number, and symbol."), 400
        if password != confirmation:
            return render_template("auth/reset_password.html", error="The passwords must match."), 400
        user = get_user_by_email(current_app.config["DATABASE"], pending["email"])
        if user is None or not update_user_password(current_app.config["DATABASE"], user["id"], password):
            forget_password_reset()
            session.pop("password_reset_verified", None)
            return render_template("auth/reset_password.html", error="Unable to reset the password. Start again."), 400
        forget_password_reset()
        session.pop("password_reset_verified", None)
        return redirect(url_for("auth.login", reset="success"))
    return render_template("auth/reset_password.html")


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

        store_user_session(user)
        flash("Account created. You are logged in.", "success")
        return redirect(url_for("client.dashboard"))

    return render_template("auth/register.html")


@auth_bp.route("/account", methods=["POST"])
def update_account():
    if "user_id" not in session:
        return jsonify({"message": "Please log in first."}), 401

    payload = account_update_payload()
    validation_error = validate_account_update_request(payload)
    if validation_error:
        return validation_error

    pending = {
        "full_name": payload["full_name"],
        "email": payload["email"],
        "role": payload["role"],
        "password": payload["password"],
        "password_confirmation": payload["password_confirmation"],
    }
    try:
        send_account_otp(pending)
    except Exception as error:
        return otp_send_error_response(error)

    forget_pending_account_update()
    remember_pending_account_update(pending)
    return jsonify(
        {
            "message": f"We sent a 6-digit verification code to {pending['email']}.",
            "otp_required": True,
            "email": pending["email"],
            "expires_at": pending["expires_at"],
            "verify_url": url_for("auth.verify_account_otp"),
            "resend_url": url_for("auth.resend_account_otp"),
        }
    )


@auth_bp.post("/account/otp/resend")
def resend_account_otp():
    if "user_id" not in session:
        return jsonify({"message": "Please log in first."}), 401

    pending = get_pending_account_update()
    if not pending:
        return jsonify({"message": "Start by saving your account changes again."}), 400

    try:
        send_account_otp(pending)
    except Exception as error:
        return otp_send_error_response(error)

    PENDING_ACCOUNT_UPDATES[session["pending_account_update_id"]] = pending
    return jsonify(
        {
            "message": f"We sent a new 6-digit verification code to {pending['email']}.",
            "email": pending["email"],
            "expires_at": pending["expires_at"],
        }
    )


@auth_bp.post("/account/otp/verify")
def verify_account_otp():
    if "user_id" not in session:
        return jsonify({"message": "Please log in first."}), 401

    pending = get_pending_account_update()
    if not pending:
        return jsonify({"message": "Start by saving your account changes again."}), 400

    code = (request.form.get("otp", "") or "").strip()
    if not code.isdigit() or len(code) != 6:
        return jsonify({"message": "Enter the 6-digit verification code."}), 400

    try:
        expires_at = datetime.fromisoformat(pending["expires_at"])
    except (KeyError, ValueError, TypeError):
        forget_pending_account_update()
        return jsonify({"message": "The verification code expired. Save your changes again."}), 400

    if otp_now() > expires_at:
        forget_pending_account_update()
        return jsonify({"message": "The verification code expired. Save your changes again."}), 400

    pending["attempts"] = int(pending.get("attempts", 0)) + 1
    max_attempts = current_app.config.get("OTP_MAX_ATTEMPTS", 5)
    if pending["attempts"] > max_attempts:
        forget_pending_account_update()
        return jsonify({"message": "Too many incorrect attempts. Save your changes again."}), 429

    if not hmac.compare_digest(pending.get("otp_hash", ""), otp_digest(code)):
        PENDING_ACCOUNT_UPDATES[session["pending_account_update_id"]] = pending
        return jsonify({"message": "The verification code is incorrect."}), 400

    validation_error = validate_account_update_request(pending)
    if validation_error:
        forget_pending_account_update()
        return validation_error

    return save_verified_account_update(pending)


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
    forget_pending_account_update()
    session.clear()
    flash("You are logged out.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.post("/account/delete")
def delete_account():
    if g.get("account") is None:
        return redirect(url_for("auth.login"))
    token = session.get("delete_account_token", "")
    supplied = request.form.get("csrf_token", "")
    if not token or not hmac.compare_digest(token.encode(), supplied.encode()) or request.form.get("confirmed") != "yes":
        abort(400, description="Please confirm account deletion from the settings page.")

    settings_url = url_for("admin.settings" if g.account["account_type"] == "admin" else "client.settings")
    try:
        result = delete_user(current_app.config["DATABASE"], g.account["id"])
    except sqlite3.Error:
        current_app.logger.exception("Account deletion failed")
        flash("Your account could not be deleted. Please try again.", "error")
        return redirect(settings_url)
    if not result["deleted"]:
        flash("This account is protected and cannot be deleted." if result["reason"] == "protected" else "Your account could not be deleted.", "error")
        return redirect(settings_url)

    forget_pending_account_update()
    forget_password_reset()
    session.clear()
    flash("Your account has been deleted. You have been logged out.", "success")
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
