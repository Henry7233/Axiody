import io
import sqlite3
import zipfile
from datetime import date, datetime

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_file, session, url_for

from app.models.documents import (
    get_client_review_data,
    list_client_summaries,
    list_documents,
)
from app.models.users import (
    create_user,
    format_created_date,
    delete_unprotected_admin_users,
    delete_user,
    get_user_by_id,
    list_admin_users,
    list_users,
    update_admin_user,
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


def is_super_admin():
    protected = session.get("protected")
    return session.get("account_type") == "admin" and protected in (1, True, "1", "true", "on", "yes")


def require_super_admin():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    if is_super_admin():
        return None

    flash("Super admin access is required.", "error")
    return redirect(url_for("admin.dashboard"))


def admin_context(active_page):
    return {
        "active_page": active_page,
        "admin_nav": True,
        "admin_can_manage_admins": is_super_admin(),
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

    period_options = [
        {"value": "2026-09", "label": "September 2026"},
        {"value": "2026-08", "label": "August 2026"},
        {"value": "2026-07", "label": "July 2026"},
        {"value": "2026-06", "label": "June 2026"},
    ]
    selected_period = request.args.get("period", period_options[0]["value"])
    if selected_period not in {period["value"] for period in period_options}:
        selected_period = period_options[0]["value"]
    selected_period_label = next(
        period["label"] for period in period_options if period["value"] == selected_period
    )

    return render_template(
        "admin/dashboard.html",
        documents=SAMPLE_DOCUMENTS,
        period_options=period_options,
        selected_period=selected_period,
        selected_period_label=selected_period_label,
        **admin_context("dashboard"),
    )


@admin_bp.route("/reviews.html", endpoint="reviews_html")
@admin_bp.route("/reviews")
def reviews():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    client, documents = get_client_review_data(
        current_app.config["DATABASE"],
        request.args.get("client", "Acme Supplies"),
    )
    return render_template(
        "admin/reviews.html",
        client=client,
        documents=documents,
        client_name=client["name"],
        document_id=request.args.get("document", "doc-1001"),
        **admin_context("reviews"),
    )


@admin_bp.route("/approve.html")
@admin_bp.route("/approve")
def approve():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    return render_template(
        "admin/approve.html",
        documents=SAMPLE_DOCUMENTS,
        client_name=request.args.get("client", "Acme Supplies"),
        document_id=request.args.get("document", "doc-1001"),
        **admin_context("approve"),
    )


@admin_bp.route("/preview_approve.html")
@admin_bp.route("/preview_approve")
def preview_approve():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    return render_template(
        "admin/preview_approve.html",
        client_name=request.args.get("client", "Acme Supplies"),
        document_id=request.args.get("document", "doc-1001"),
        **admin_context("approve"),
    )


@admin_bp.route("/clients.html")
@admin_bp.route("/clients")
def clients():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    return render_template(
        "admin/clients.html",
        clients=list_client_summaries(current_app.config["DATABASE"]),
        **admin_context("clients"),
    )


@admin_bp.route("/bookkeeping.html")
@admin_bp.route("/bookkeeping")
def bookkeeping():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    period_options = [
        {"value": "2026-09", "label": "September 2026"},
        {"value": "2026-08", "label": "August 2026"},
        {"value": "2026-07", "label": "July 2026"},
        {"value": "2026-06", "label": "June 2026"},
    ]
    selected_period = request.args.get("period", period_options[0]["value"])
    if selected_period not in {period["value"] for period in period_options}:
        selected_period = period_options[0]["value"]

    return render_template(
        "admin/bookkeeping.html",
        period_options=period_options,
        selected_period=selected_period,
        **admin_context("bookkeeping"),
    )


@admin_bp.route("/documents.html")
@admin_bp.route("/documents")
def documents():
    return bookkeeping()


@admin_bp.route("/documents/data")
def documents_data():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    database_path = current_app.config["DATABASE"]

    def formatted_size(size_bytes):
        if size_bytes is None:
            return "0 KB"
        if size_bytes >= 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        if size_bytes >= 1024:
            return f"{size_bytes / 1024:.0f} KB"
        return f"{size_bytes} B"

    def formatted_date(value):
        if not value:
            return ""
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return value
        return parsed.strftime("%b %d").replace(" 0", " ")

    def formatted_submitted_at(value):
        if not value:
            return ""
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return value
        hour = parsed.strftime("%I").lstrip("0") or "12"
        return f"{parsed.strftime('%b %d,')} {hour}:{parsed.strftime('%M')} {parsed.strftime('%p')}"

    def category_for(title):
        text = (title or "").lower()
        if "invoice" in text or "bill" in text:
            return "invoices"
        if "receipt" in text:
            return "receipts"
        if "bank" in text or "statement" in text:
            return "statements"
        return "others"

    selected_period = request.args.get("period", "2026-09")
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                d.id,
                d.title,
                d.filename AS name,
                d.file_size AS size_bytes,
                d.created_at,
                CASE
                    WHEN TRIM(COALESCE(u.full_name, '')) <> '' THEN u.full_name
                    ELSE u.email
                END AS submittedBy
            FROM documents d
            JOIN users u
              ON u.id = d.user_id
                        WHERE substr(d.created_at, 1, 7) = ?
            ORDER BY d.created_at DESC, d.id DESC
                        """,
                        (selected_period,),
        ).fetchall()

    grouped = {
        "invoices": {"label": "Invoices", "files": []},
        "receipts": {"label": "Receipts", "files": []},
        "statements": {"label": "Bank Statements", "files": []},
        "others": {"label": "Others", "files": []},
    }

    for row in rows:
        category = category_for(row["title"])
        grouped[category]["files"].append(
            {
                "id": row["id"],
                "name": row["name"],
                "size": formatted_size(row["size_bytes"]),
                "date": formatted_date(row["created_at"]),
                "submittedBy": row["submittedBy"] or row["name"],
                "submittedAt": formatted_submitted_at(row["created_at"]),
            }
        )

    return jsonify(grouped)


@admin_bp.route("/bookkeeping/download")
def download_bookkeeping_period():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    selected_period = request.args.get("period", "2026-09")
    archive = io.BytesIO()
    with sqlite3.connect(current_app.config["DATABASE"]) as connection:
        documents = connection.execute(
            """
            SELECT filename, file_data
            FROM documents
            WHERE substr(created_at, 1, 7) = ?
            ORDER BY created_at DESC, id DESC
            """,
            (selected_period,),
        ).fetchall()

    if not documents:
        return "No documents found for this period.", 404

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_file:
        used_names = set()
        for index, (filename, file_data) in enumerate(documents, start=1):
            name = filename or f"document-{index}"
            if name in used_names:
                stem, separator, suffix = name.rpartition(".")
                name = f"{stem or name}-{index}{separator}{suffix}" if separator else f"{name}-{index}"
            used_names.add(name)
            zip_file.writestr(name, file_data or b"")

    archive.seek(0)
    return send_file(
        archive,
        as_attachment=True,
        download_name=f"bookkeeping-{selected_period}.zip",
        mimetype="application/zip",
    )


@admin_bp.route("/bookkeeping/download/<int:document_id>")
def download_bookkeeping_document(document_id):
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    with sqlite3.connect(current_app.config["DATABASE"]) as connection:
        document = connection.execute(
            "SELECT filename, file_type, file_data FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()

    if not document or document[2] is None:
        return "Document not found.", 404

    return send_file(
        io.BytesIO(document[2]),
        as_attachment=True,
        download_name=document[0] or f"document-{document_id}",
        mimetype=document[1] or "application/octet-stream",
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
        account_update_url=url_for("auth.update_account"),
        notifications_url=url_for("client.notifications"),
        submissions_url=url_for("client.upload"),
        **admin_context("settings"),
    )

@admin_bp.route("/admin_management.html")
@admin_bp.route("/admin_management")
def admin_management():
    redirect_response = require_super_admin()
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
    redirect_response = require_super_admin()
    if redirect_response:
        return jsonify({"message": "Super admin access is required."}), 403

    data = request.get_json(silent=True) or request.form
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    selected_role = data.get("role", "").strip()
    custom_role = data.get("custom_role", "").strip()
    role = custom_role if selected_role == "Other" else selected_role
    password = data.get("password", "")
    password_confirmation = data.get("password_confirmation", "")
    super_admin = data.get("super_admin", False)
    protected = 1 if super_admin in (True, "true", "1", "on", "yes") else 0

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
        protected=protected,
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
                "protected": user["protected"],
            },
        }
    ), 201


@admin_bp.route("/admin_management/admins", methods=["DELETE"])
def delete_unprotected_admins():
    redirect_response = require_super_admin()
    if redirect_response:
        return jsonify({"message": "Super admin access is required."}), 403

    result = delete_unprotected_admin_users(current_app.config["DATABASE"])
    return jsonify(
        {
            "message": f"{result['deleted']} unprotected admin account(s) were deleted.",
            "deleted_ids": result["deleted_ids"],
        }
    )


@admin_bp.route("/admin_management/admins/<int:user_id>", methods=["DELETE"])
def delete_admin(user_id):
    redirect_response = require_super_admin()
    if redirect_response:
        return jsonify({"message": "Super admin access is required."}), 403

    user = get_user_by_id(current_app.config["DATABASE"], user_id)
    if user is None or user["account_type"] != "admin":
        return jsonify({"message": "Admin account was not found."}), 404

    result = delete_user(current_app.config["DATABASE"], user_id)
    if result["deleted"]:
        return jsonify({"message": "Admin account was deleted."})

    if result["reason"] == "protected":
        return jsonify({"message": "This admin account is protected and cannot be deleted."}), 403

    return jsonify({"message": "Admin account was not found."}), 404


@admin_bp.route("/admin_management/admins/<int:user_id>", methods=["PUT"])
def update_admin(user_id):
    if require_super_admin():
        return jsonify({"message": "Super admin access is required."}), 403

    data = request.get_json(silent=True) or request.form
    fields = ("name", "email", "role", "custom_role", "password", "password_confirmation")
    if any(not isinstance(data.get(field, ""), str) for field in fields):
        return jsonify({"message": "Account fields must be text."}), 400
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    selected_role = data.get("role", "").strip()
    role = data.get("custom_role", "").strip() if selected_role == "Other" else selected_role
    password = data.get("password", "")
    confirmation = data.get("password_confirmation", "")
    if not name or not email or not role:
        return jsonify({"message": "Enter a full name, email address, and role."}), 400
    if (password or confirmation) and len(password) < 8:
        return jsonify({"message": "Password must be at least 8 characters."}), 400
    if password != confirmation:
        return jsonify({"message": "Passwords must match."}), 400

    result = update_admin_user(current_app.config["DATABASE"], user_id, name, email, role, password)
    if not result["updated"]:
        if result["reason"] == "duplicate_email":
            return jsonify({"message": "An account with that email already exists."}), 409
        return jsonify({"message": "Admin account was not found."}), 404

    user = get_user_by_id(current_app.config["DATABASE"], user_id)
    return jsonify({
        "message": f"{user['full_name']} was updated.",
        "admin": {
            "id": user["id"],
            "name": user["full_name"] or user["email"],
            "email": user["email"],
            "role": user["role"],
            "date": format_created_date(user["created_at"]),
            "protected": user["protected"],
        },
    })
