import io
import mimetypes
import secrets
import sqlite3
import zipfile
from collections import Counter
from contextlib import closing
from datetime import date, datetime

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, session, url_for

from app.models.admin_dashboard import get_admin_dashboard_data
from app.models.bookkeeping import get_bookkeeping_groups
from app.services.bookkeeping_export import build_bookkeeping_workbook
from app.time import singapore_today, to_singapore
from app.models.documents import (
    DOCUMENT_TYPES,
    get_approval_documents,
    get_client_review_data,
    list_client_summaries,
    list_documents,
    save_document_review,
)
from app.models.users import (
    create_user,
    format_created_date,
    delete_unprotected_admin_users,
    delete_user,
    get_user_by_id,
    list_admin_users,
    update_admin_user,
)


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


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


def format_file_size(size_bytes):
    if size_bytes is None:
        return "0 KB"
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


def format_display_date(value):
    if not value:
        return ""
    try:
        parsed = to_singapore(value)
    except ValueError:
        return value
    return parsed.strftime("%b %d, %Y")


def build_recent_month_options(months_back=12):
    today = singapore_today()
    current = date(today.year, today.month, 1)
    options = []
    for _ in range(months_back):
        options.append({
            "value": current.strftime("%Y-%m"),
            "label": current.strftime("%B %Y"),
        })
        year = current.year
        month = current.month - 1
        if month == 0:
            year -= 1
            month = 12
        current = date(year, month, 1)
    return options


def display_file_type(filename, content_type):
    suffix = (filename or "").rsplit(".", 1)
    if len(suffix) == 2 and suffix[1]:
        return suffix[1].upper()
    if content_type:
        return content_type.split("/")[-1].upper()
    return "FILE"


def get_document_blob(document_id):
    with closing(sqlite3.connect(current_app.config["DATABASE"])) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            """
            SELECT id, filename, file_type, file_data
            FROM documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()


@admin_bp.route("/")
def index():
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/dashboard.html")
@admin_bp.route("/dashboard")
def dashboard():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    data = get_admin_dashboard_data(
        current_app.config["DATABASE"], request.args.get("period", "all")
    )
    data["recent_submissions"] = data["recent_submissions"][:5]
    data["attention_documents"] = data["attention_documents"][:5]

    return render_template(
        "admin/dashboard.html",
        **data,
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
        documents=get_approval_documents(current_app.config["DATABASE"]),
        review_token=review_token(),
        **admin_context("approve"),
    )


@admin_bp.route("/preview_approve.html")
@admin_bp.route("/preview_approve")
def preview_approve():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    document_id = request.args.get("document", type=int)
    if document_id is None:
        abort(404)
    documents = get_approval_documents(current_app.config["DATABASE"], document_id)
    if not documents:
        abort(404)
    return render_template(
        "admin/preview_approve.html",
        document=documents[0],
        document_types=DOCUMENT_TYPES,
        review_token=review_token(),
        **admin_context("approve"),
    )


def review_token():
    if "document_review_token" not in session:
        session["document_review_token"] = secrets.token_hex(32)
    return session["document_review_token"]


@admin_bp.post("/documents/<int:document_id>/review")
def review_document(document_id):
    if "user_id" not in session:
        return jsonify(message="Please log in first."), 401
    if session.get("account_type") != "admin":
        return jsonify(message="Admin access is required."), 403
    token = request.headers.get("X-Review-Token", "")
    if not token or not secrets.compare_digest(token, session.get("document_review_token", "")):
        return jsonify(message="Your review session has expired. Reload the page and try again."), 403
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("action") not in ("saved", "approved", "rejected"):
        return jsonify(message="Choose a valid review action."), 400
    changes = {}
    for field in ("title", "description", "document_date", "document_type"):
        if field in payload:
            if not isinstance(payload[field], str):
                return jsonify(message="Document fields must contain text."), 400
            changes[field] = payload[field].strip()
    if "title" in changes and not changes["title"]:
        return jsonify(message="A document title is required."), 400
    if "document_type" in changes and changes["document_type"] not in DOCUMENT_TYPES:
        return jsonify(message="Choose a valid document category."), 400
    if "document_date" in changes:
        try:
            changes["document_date"] = date.fromisoformat(changes["document_date"]).isoformat()
        except ValueError:
            return jsonify(message="Enter a valid document date."), 400
    result = save_document_review(
        current_app.config["DATABASE"], document_id, session["user_id"], payload["action"], changes
    )
    if result == "missing":
        return jsonify(message="Document not found."), 404
    if result == "reviewed":
        return jsonify(message="This document is no longer awaiting review. Reload the page."), 409
    if result == "incomplete":
        return jsonify(message="This document is no longer eligible for classification review. Reload the approval queue."), 409
    return jsonify(message={
        "saved": "Changes saved for review.",
        "approved": "Document approved.",
        "rejected": "Document deleted.",
    }[payload["action"]])


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


@admin_bp.route("/client_detail.html")
@admin_bp.route("/client_detail")
@admin_bp.route("/client_details.html")
@admin_bp.route("/client_details")
@admin_bp.route("/clients/<int:client_id>")
@admin_bp.route("/clients/<int:client_id>/preview")
def client_detail(client_id=None):
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    requested_client = request.args.get("client", "").strip()
    requested_id = request.args.get("client_id", type=int)
    client_id = client_id or requested_id

    with sqlite3.connect(current_app.config["DATABASE"]) as connection:
        connection.row_factory = sqlite3.Row
        if client_id is not None:
            client_row = connection.execute(
                """
                SELECT
                    id,
                    COALESCE(NULLIF(full_name, ''), email) AS name,
                    email,
                    created_at
                FROM users
                WHERE id = ? AND account_type = 'client'
                """,
                (client_id,),
            ).fetchone()
        elif requested_client:
            client_row = connection.execute(
                """
                SELECT
                    id,
                    COALESCE(NULLIF(full_name, ''), email) AS name,
                    email,
                    created_at
                FROM users
                WHERE account_type = 'client'
                  AND (full_name = ? OR email = ?)
                LIMIT 1
                """,
                (requested_client, requested_client),
            ).fetchone()
        else:
            client_row = None

        if client_row is None:
            abort(404)

        document_rows = connection.execute(
            """
            SELECT
                id,
                filename,
                file_type,
                file_size,
                classification_status,
                validation_status,
                created_at
            FROM documents
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (client_row["id"],),
        ).fetchall()

    documents = []
    for document in document_rows:
        status = document["validation_status"] or document["classification_status"] or "Under review"
        documents.append(
            {
                "id": document["id"],
                "filename": document["filename"] or f"document-{document['id']}",
                "file_type": display_file_type(document["filename"], document["file_type"]),
                "file_size": format_file_size(document["file_size"]),
                "created_at": format_display_date(document["created_at"]),
                "status": status,
                "is_under_review": status == "Under review",
            }
        )
    bookkept_count = sum(1 for document in documents if document["status"] in {"Complete", "Success"})
    under_review_count = max(len(documents) - bookkept_count, 0)
    latest_period = next(
        (
            format_display_date(document["created_at"])
            for document in document_rows
            if document["created_at"]
        ),
        "No submissions yet",
    )

    return render_template(
        "admin/client_detail.html",
        client={
            "id": client_row["id"],
            "name": client_row["name"],
            "email": client_row["email"],
            "created_at": format_display_date(client_row["created_at"]),
        },
        documents=documents,
        bookkeeping_period=latest_period,
        bookkept_count=bookkept_count,
        under_review_count=under_review_count,
        **admin_context("clients"),
    )


@admin_bp.route("/documents/<int:document_id>/preview")
def preview_document(document_id):
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    document = get_document_blob(document_id)
    if not document or document["file_data"] is None:
        abort(404)

    filename = document["filename"] or f"document-{document_id}"
    mimetype = document["file_type"] or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return send_file(
        io.BytesIO(document["file_data"]),
        as_attachment=False,
        download_name=filename,
        mimetype=mimetype,
    )


@admin_bp.route("/documents/<int:document_id>/download")
def download_document(document_id):
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    document = get_document_blob(document_id)
    if not document or document["file_data"] is None:
        abort(404)

    filename = document["filename"] or f"document-{document_id}"
    mimetype = document["file_type"] or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return send_file(
        io.BytesIO(document["file_data"]),
        as_attachment=True,
        download_name=filename,
        mimetype=mimetype,
    )


@admin_bp.route("/clients/<int:client_id>/documents/download")
def download_all_client_documents(client_id):
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    with sqlite3.connect(current_app.config["DATABASE"]) as connection:
        client = connection.execute(
            """
            SELECT COALESCE(NULLIF(full_name, ''), email) AS name
            FROM users
            WHERE id = ? AND account_type = 'client'
            """,
            (client_id,),
        ).fetchone()
        documents = connection.execute(
            """
            SELECT filename, file_data
            FROM documents
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (client_id,),
        ).fetchall()

    if client is None:
        abort(404)
    if not documents:
        return "No documents found for this client.", 404

    archive = io.BytesIO()
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
    safe_client_name = "".join(
        character if character.isalnum() or character in ("-", "_") else "-"
        for character in client[0].strip().lower()
    ).strip("-") or f"client-{client_id}"
    return send_file(
        archive,
        as_attachment=True,
        download_name=f"{safe_client_name}-documents.zip",
        mimetype="application/zip",
    )


@admin_bp.route("/bookkeeping.html")
@admin_bp.route("/bookkeeping")
def bookkeeping():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    period_options = build_recent_month_options()
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


@admin_bp.route("/recent_submissions.html")
@admin_bp.route("/recent_submissions")
def recent_submissions():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    return render_template(
        "admin/recent_submissions.html",
        **get_admin_dashboard_data(current_app.config["DATABASE"], request.args.get("period", "all")),
        **admin_context("dashboard"),
    )


@admin_bp.route("/clients_attention.html")
@admin_bp.route("/clients_attention")
def clients_attention():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    return render_template(
        "admin/clients_attention.html",
        **get_admin_dashboard_data(current_app.config["DATABASE"], request.args.get("period", "all")),
        **admin_context("dashboard"),
    )


def bookkeeping_request_period():
    default_period = singapore_today().strftime("%Y-%m")
    period = request.args.get("period", default_period)
    try:
        parsed = datetime.strptime(period, "%Y-%m")
    except ValueError:
        abort(400, description="Choose a valid bookkeeping month (YYYY-MM).")
    if parsed.strftime("%Y-%m") != period:
        abort(400, description="Choose a valid bookkeeping month (YYYY-MM).")
    return period


@admin_bp.route("/documents/data")
def documents_data():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    return jsonify(get_bookkeeping_groups(current_app.config["DATABASE"], bookkeeping_request_period()))


@admin_bp.route("/bookkeeping/download")
def download_bookkeeping_period():
    redirect_response = require_admin()
    if redirect_response:
        return redirect_response

    selected_period = bookkeeping_request_period()
    groups = get_bookkeeping_groups(current_app.config["DATABASE"], selected_period)
    period_label = datetime.strptime(selected_period, "%Y-%m").strftime("%B %Y")
    return send_file(
        build_bookkeeping_workbook(groups, selected_period),
        as_attachment=True,
        download_name=f"{period_label} Bookkeeping.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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

    selected_period = request.args.get("period", "all")
    selected_client = request.args.get("client", "all")

    with sqlite3.connect(current_app.config["DATABASE"]) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                u.full_name AS client_name,
                u.email AS client_email,
                d.title AS document_title,
                d.document_date AS bookkeeping_date,
                n.id AS reminder_id,
                n.title AS notification_title,
                n.message,
                n.last_reminder_sent,
                n.next_reminder_date,
                n.reminder_count,
                n.status
            FROM notifications n
            JOIN documents d ON d.id = n.document_id
            JOIN users u ON u.id = d.user_id
            WHERE n.status != 'resolved'
            ORDER BY n.next_reminder_date IS NULL, n.next_reminder_date ASC, n.last_reminder_sent DESC
            """
        ).fetchall()

    unique_periods = []
    seen_periods = set()
    unique_clients = []
    seen_clients = set()
    reminders_data = []

    for row in rows:
        client_name = row["client_name"] or row["client_email"] or "Unknown client"
        client_email = row["client_email"] or ""
        bookkeeping_date = (row["bookkeeping_date"] or "")[:10]
        document_title = row["document_title"] or row["notification_title"] or "Document reminder"

        if bookkeeping_date and bookkeeping_date not in seen_periods:
            seen_periods.add(bookkeeping_date)
            try:
                label = datetime.strptime(bookkeeping_date, "%Y-%m-%d").strftime("%B %Y")
            except ValueError:
                label = bookkeeping_date
            unique_periods.append({"value": bookkeeping_date, "label": label})

        if client_name not in seen_clients:
            seen_clients.add(client_name)
            unique_clients.append(client_name)

        if selected_period != "all" and bookkeeping_date != selected_period:
            continue
        if selected_client != "all" and client_name != selected_client:
            continue

        last_reminder_sent = row["last_reminder_sent"]
        last_date = last_time = ""
        if last_reminder_sent:
            try:
                parsed = to_singapore(last_reminder_sent)
                last_date = parsed.strftime("%Y-%m-%d")
                last_time = parsed.strftime("%H:%M")
            except ValueError:
                last_date = str(last_reminder_sent)[:10]
                last_time = str(last_reminder_sent)[11:16] if len(str(last_reminder_sent)) > 10 else ""

        reminders_data.append(
            {
                "id": row["reminder_id"],
                "client_name": client_name,
                "client_email": client_email,
                "title": document_title,
                "message": row["message"] or "",
                "last_reminder_sent": last_reminder_sent,
                "last_reminder_sent_date": last_date,
                "last_reminder_sent_time": last_time,
                "next_reminder_date": row["next_reminder_date"],
                "reminder_count": int(row["reminder_count"] or 0),
                "bookkeeping_date": bookkeeping_date,
            }
        )

    unique_periods.sort(key=lambda item: item["value"], reverse=True)
    unique_clients.sort()
    period_options = [{"value": "all", "label": "All dates"}] + [
        {"value": item["value"], "label": item["label"]} for item in unique_periods
    ]
    client_options = [{"value": "all", "label": "All Clients"}] + [
        {"value": name, "label": name} for name in unique_clients
    ]

    return render_template(
        "admin/reminders.html",
        reminders=reminders_data,
        period_options=period_options,
        client_options=client_options,
        selected_period=selected_period,
        selected_client=selected_client,
        active_followups=len(reminders_data),
        total_emails_sent=sum(item["reminder_count"] for item in reminders_data),
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
    role_counts = Counter(admin["role"] for admin in admins)
    admin_role_counts = {
        "total": len(admins),
        "administrator": role_counts.get("Administrator", 0),
        "admin_manager": role_counts.get("Admin manager", 0),
        "reviewer": role_counts.get("Reviewer", 0),
        "other": sum(count for role, count in role_counts.items() if role not in standard_roles),
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
