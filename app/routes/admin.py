from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from app.models.users import (
    create_user,
    delete_unprotected_admin_users,
    delete_user,
    get_user_by_id,
    list_admin_users,
)


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


SAMPLE_DOCUMENTS = [
    {
        "id": "doc-1001",
        "title": "September GST Invoice",
        "submitter": "Acme Supplies",
        "submission_date": "2026-09-03",
    },
    {
        "id": "doc-1002",
        "title": "August Payroll Summary",
        "submitter": "Northstar Foods",
        "submission_date": "2026-09-05",
    },
    {
        "id": "doc-1003",
        "title": "Bank Statement Review",
        "submitter": "Greenline Studio",
        "submission_date": "2026-09-07",
    },
]


def require_admin():
    if "user_id" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("auth.login"))

    if session.get("account_type") == "admin":
        return None

    flash("Please log in with an admin account.", "error")
    return redirect(url_for("client.upload"))


def admin_context(active_page):
    return {
        "active_page": active_page,
        "admin_nav": True,
        "home_url": url_for("admin.dashboard"),
        "profile_url": url_for("admin.settings") + "#account-information",
        "settings_url": url_for("admin.settings"),
        "username": session.get("user_name") or session.get("user_email"),
    }


@admin_bp.route("/")
def index():
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/dashboard.html")
@admin_bp.route("/dashboard")
def dashboard():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    return render_template(
        "admin/dashboard.html",
        documents=SAMPLE_DOCUMENTS,
        **admin_context("dashboard"),
    )


@admin_bp.route("/reviews.html")
@admin_bp.route("/reviews")
def reviews():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    return render_template(
        "admin/reviews.html",
        client_name=request.args.get("client", "Acme Supplies"),
        document_id=request.args.get("document", "doc-1001"),
        **admin_context("reviews"),
    )


@admin_bp.route("/clients.html")
@admin_bp.route("/clients")
def clients():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    clients_data = [
        {"name": "Acme Supplies", "status": "Needs review", "documents": 4},
        {"name": "Northstar Foods", "status": "Pending files", "documents": 2},
        {"name": "Greenline Studio", "status": "Ready", "documents": 6},
    ]
    return render_template(
        "admin/clients.html",
        clients=clients_data,
        **admin_context("clients"),
    )


@admin_bp.route("/documents.html")
@admin_bp.route("/documents")
def documents():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    return render_template(
        "admin/documents.html",
        documents=SAMPLE_DOCUMENTS,
        **admin_context("documents"),
    )


@admin_bp.route("/reminders.html")
@admin_bp.route("/reminders")
def reminders():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    reminders_data = [
        {"client": "Acme Supplies", "due": "2026-09-10", "type": "Missing GST receipt"},
        {"client": "Northstar Foods", "due": "2026-09-12", "type": "Payroll confirmation"},
        {"client": "Greenline Studio", "due": "2026-09-15", "type": "Bank statement follow-up"},
    ]
    return render_template(
        "admin/reminders.html",
        reminders=reminders_data,
        **admin_context("reminders"),
    )


@admin_bp.route("/settings.html")
@admin_bp.route("/settings")
def settings():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    account = {
        "full_name": session.get("user_name", ""),
        "email": session.get("user_email", ""),
    }
    return render_template(
        "admin/admin_settings.html",
        account=account,
        account_update_url="",
        notifications_url=url_for("client.notifications"),
        submissions_url=url_for("client.upload"),
        **admin_context("settings"),
    )

@admin_bp.route("/admin_management.html")
@admin_bp.route("/admin_management")
def admin_management():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    admins = list_admin_users(current_app.config["DATABASE"])
    admin_roles = sorted({admin["role"] for admin in admins} | {"Admin manager", "Administrator", "Reviewer"})
    standard_roles = {"Administrator", "Admin manager", "Reviewer"}
    admin_role_counts = {
        "total": len(admins),
        "administrator": sum(1 for admin in admins if admin["role"] == "Administrator"),
        "admin_manager": sum(1 for admin in admins if admin["role"] == "Admin manager"),
        "reviewer": sum(1 for admin in admins if admin["role"] == "Reviewer"),
        "other": sum(1 for admin in admins if admin["role"] not in standard_roles),
    }
    return render_template(
        "admin/admin_management.html",
        admins=admins,
        admin_roles=admin_roles,
        admin_role_counts=admin_role_counts,
        **admin_context("admin_management"),
    )


@admin_bp.route("/admin_management/admins", methods=["POST"])
def create_admin():
    redirect_response = require_admin()
    if redirect_response:
        return jsonify({"message": "Admin access is required."}), 403

    data = request.get_json(silent=True) or request.form
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    selected_role = data.get("role", "").strip()
    custom_role = data.get("custom_role", "").strip()
    role = custom_role if selected_role == "Other" else selected_role
    password = data.get("password", "")
    password_confirmation = data.get("password_confirmation", "")

    if not name:
        return jsonify({"message": "Enter a full name."}), 400
    if not email:
        return jsonify({"message": "Enter an email address."}), 400
    if not role:
        return jsonify({"message": "Enter a role."}), 400
    if len(password) < 8:
        return jsonify({"message": "Password must be at least 8 characters."}), 400
    if password != password_confirmation:
        return jsonify({"message": "Passwords must match."}), 400

    user = create_user(
        current_app.config["DATABASE"],
        email,
        password,
        account_type="admin",
        protected=0,
        full_name=name,
        role=role,
    )
    if user is None:
        return jsonify({"message": "An account with that email already exists."}), 409

    return jsonify(
        {
            "message": f"{name} was added.",
            "admin": {
                "id": user["id"],
                "name": user["full_name"] or user["email"],
                "email": user["email"],
                "role": user["role"],
                "date": user["date"],
            },
        }
    ), 201


@admin_bp.route("/admin_management/admins", methods=["DELETE"])
def delete_unprotected_admins():
    redirect_response = require_admin()
    if redirect_response:
        return jsonify({"message": "Admin access is required."}), 403

    result = delete_unprotected_admin_users(current_app.config["DATABASE"])
    return jsonify(
        {
            "message": f"{result['deleted']} unprotected admin account(s) were deleted.",
            "deleted_ids": result["deleted_ids"],
        }
    )


@admin_bp.route("/admin_management/admins/<int:user_id>", methods=["DELETE"])
def delete_admin(user_id):
    redirect_response = require_admin()
    if redirect_response:
        return jsonify({"message": "Admin access is required."}), 403

    user = get_user_by_id(current_app.config["DATABASE"], user_id)
    if user is None or user["account_type"] != "admin":
        return jsonify({"message": "Admin account was not found."}), 404

    result = delete_user(current_app.config["DATABASE"], user_id)
    if result["deleted"]:
        return jsonify({"message": "Admin account was deleted."})

    if result["reason"] == "protected":
        return jsonify({"message": "This admin account is protected and cannot be deleted."}), 403

    return jsonify({"message": "Admin account was not found."}), 404
