from flask import Blueprint, flash, redirect, render_template, request, session, url_for


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


def require_login():
    if "user_id" in session:
        return None

    flash("Please log in first.", "error")
    return redirect(url_for("auth.login"))


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
    redirect_response = require_login()
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
    redirect_response = require_login()
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
    redirect_response = require_login()
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
    redirect_response = require_login()
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
    redirect_response = require_login()
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
    redirect_response = require_login()
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
    redirect_response = require_login()
    if redirect_response:
        return redirect_response

    admins_data = [
        {
            "id": "admin-1001",
            "name": "Alice Johnson",
            "email": "alice.johnson@example.com",
            "role": "Admin manager",
            "status": "active",
            "last_active": "2026-09-09",
        },
        {
            "id": "admin-1002",
            "name": "Bob Smith",
            "email": "bob.smith@example.com",
            "role": "Administrator",
            "status": "pending",
            "last_active": "Never",
        },
    ]
    return render_template(
        "admin/admin_management.html",
        admins=admins_data,
        **admin_context("admin_management"),
    )
