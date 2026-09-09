from flask import Blueprint, flash, redirect, render_template, session, url_for


client_bp = Blueprint("client", __name__, url_prefix="/client")


def require_client():
    if "user_id" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("auth.login"))

    if session.get("account_type", "client") == "client":
        return None

    flash("Please use the client area with a client account.", "error")
    return redirect(url_for("admin.dashboard"))


@client_bp.route("/upload", methods=["GET", "POST"])
def upload():
    redirect_response = require_client()
    if redirect_response:
        return redirect_response

    return render_template("client/upload.html", username=session.get("user_email"))


@client_bp.route("/notifications")
def notifications():
    redirect_response = require_client()
    if redirect_response:
        return redirect_response

    return render_template(
        "client/notifications.html",
        username=session.get("user_email"),
    )


@client_bp.route("/settings")
def settings():
    redirect_response = require_client()
    if redirect_response:
        return redirect_response

    account = {
        "full_name": session.get("user_name", ""),
        "email": session.get("user_email", ""),
    }
    return render_template(
        "client/client_settings.html",
        account=account,
        account_update_url="",
        notifications_url=url_for("client.notifications"),
        submissions_url=url_for("client.upload"),
        username=session.get("user_name") or session.get("user_email"),
    )
