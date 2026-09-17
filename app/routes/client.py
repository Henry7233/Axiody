"""Client routes for dashboards, uploads, reminders, and account settings."""

import os
from datetime import date, datetime

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from app.time import singapore_now, singapore_today, to_singapore
from app.agents.classification_agent import classify_document, extract_document_text
from app.agents.reminder_agent import (
    create_initial_reminder,
    process_due_reminders,
)
from app.agents.validation_agent import validate_document

from app.models.notifications import list_client_notifications
from app.models.documents import (
    create_document,
    list_client_document_records,
    update_document_results,
)



client_bp = Blueprint("client", __name__, url_prefix="/client")


def format_period_date(period_date):
    return f"{period_date.day} {period_date.strftime('%B %Y')}"


def format_file_size(size):
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{round(size / 1024)} KB"
    return f"{size} B"


def submission_window(today=None):
    today = today or singapore_today()
    current_period = date(today.year, today.month, 1)
    deadline = date(today.year, today.month, 25)
    next_month_number = today.year * 12 + today.month
    next_year, next_month_index = divmod(next_month_number, 12)
    next_period = date(next_year, next_month_index + 1, 1)

    return {
        "is_closed": today.day > 25,
        "period_label": current_period.strftime("%B %Y"),
        "deadline_label": format_period_date(deadline),
        "next_period_label": next_period.strftime("%B %Y"),
        "next_period_open_label": format_period_date(next_period),
    }


def bookkeeping_periods():
    today = singapore_today()
    periods = [{"value": "all", "label": "All dates"}]
    for offset in range(12):
        year, month = divmod(today.year * 12 + today.month - 1 - offset, 12)
        period = date(year, month + 1, 1)
        periods.append({"value": period.strftime("%Y-%m"), "label": period.strftime("%B %Y")})
    selected_period = request.args.get("period", periods[0]["value"])
    if selected_period not in {period["value"] for period in periods}:
        selected_period = periods[0]["value"]
    return periods, selected_period


@client_bp.route("/")
@client_bp.route("/dashboard.html")
@client_bp.route("/dashboard")
def dashboard():
    """Render templates/client/dashboard.html with the current client's data."""
    redirect_response = require_client()
    if redirect_response:
        return redirect_response

    periods, selected_period = bookkeeping_periods()
    records = list_client_document_records(current_app.config["DATABASE"], session["user_id"], selected_period)
    submitted_count = sum(record["file_count"] for record in records)
    completed_count = sum(record["completed_count"] for record in records)
    today = singapore_today()
    notification_data = list_client_notifications(current_app.config["DATABASE"], session["user_id"], today)
    reminders = [
        notification for notification in notification_data["notifications"]
        if notification["category"] == "deadlines"
        and (selected_period == "all" or any(
            (file["document_date"] or "").startswith(selected_period)
            for file in notification["files"]
        ))
    ]
    # Keep overdue work visible first, using the same deadline as Notifications.
    deadline_reminder = min(
        (reminder for reminder in reminders if reminder["deadline"]),
        key=lambda reminder: reminder["deadline"]["deadline"], default=None,
    )
    deadline_days = (
        (date.fromisoformat(deadline_reminder["deadline"]["deadline"]) - today).days
        if deadline_reminder else None
    )

    account = g.account
    try:
        member_since = to_singapore(account["created_at"]).strftime("%b %Y")
    except (TypeError, ValueError):
        member_since = "Not provided"

    return render_template(
        "client/dashboard.html", account=account, member_since=member_since,
        periods=periods, selected_period=selected_period, records=records,
        submitted_count=submitted_count, completed_count=completed_count,
        pending_count=submitted_count - completed_count,
        outstanding_reminder_count=len(reminders),
        reminder_file_count=sum(len(reminder["files"]) for reminder in reminders),
        complete_count=notification_data["complete_count"],
        changes_count=notification_data["changes_count"],
        changes_file_count=notification_data["files_to_change"],
        approved_count=notification_data["approved_count"],
        deadline_reminder=deadline_reminder, deadline_days=deadline_days,
        period_label=next(period["label"] for period in periods if period["value"] == selected_period),
        username=account["full_name"] or account["email"],
    )


ALLOWED_UPLOAD_EXTENSIONS = {".pdf"}
MAX_SUBMISSION_FILE_SIZE = 50 * 1024 * 1024


def get_uploaded_file_size(uploaded_file):
    try:
        current_position = uploaded_file.tell()
        uploaded_file.seek(0, os.SEEK_END)
        size = uploaded_file.tell()
        uploaded_file.seek(current_position)
        return size
    except (AttributeError, OSError):
        return len(uploaded_file.read())


def require_client():
    if "user_id" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("auth.login"))

    if session.get("account_type", "client") == "client":
        return None

    flash("Please use the client area with a client account.", "error")
    return redirect(url_for("admin.dashboard"))


def is_allowed_submission_file(filename, content_type=""):
    extension = os.path.splitext(filename or "")[1].lower()
    if content_type and content_type.startswith("image/"):
        return False
    if extension in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return False
    return extension in ALLOWED_UPLOAD_EXTENSIONS


@client_bp.route("/upload", methods=["GET", "POST"])
def upload():
    redirect_response = require_client()
    if redirect_response:
        return redirect_response

    submission_status = submission_window()
    initial_title = request.form.get("title", "") if request.method == "POST" else request.args.get("title", "")
    initial_document_date = request.form.get("document_date", "") if request.method == "POST" else request.args.get("document_date", "")
    required_filenames_raw = request.form.get("required_filenames", "") if request.method == "POST" else request.args.get("required_filenames", "")
    try:
        initial_document_date = date.fromisoformat(initial_document_date).isoformat()
    except ValueError:
        initial_document_date = ""

    required_filenames = {
        os.path.splitext(item.strip())[0].lower()
        for item in required_filenames_raw.split(",")
        if item and item.strip()
    }

    if request.method == "POST":
        if submission_status["is_closed"]:
            flash("The submission period for this month is closed.", "error")
            return render_template(
                "client/upload.html",
                username=session.get("user_email"),
                initial_title=initial_title,
                initial_document_date=initial_document_date,
                submission_status=submission_status,
            ), 403

        titles = request.form.getlist("title")
        descriptions = request.form.getlist("description")
        document_dates = request.form.getlist("document_date")
        saved_count = 0
        uploaded_files = []
        upload_time = singapore_now()

        if required_filenames:
            for index, title in enumerate(titles, start=1):
                description = descriptions[index - 1] if index <= len(descriptions) else ""
                document_date = document_dates[index - 1] if index <= len(document_dates) else ""
                files = request.files.getlist(f"document_files_{index}")
                if not title.strip() or not document_date:
                    continue
                for uploaded_file in files:
                    if not uploaded_file or not uploaded_file.filename:
                        continue
                    filename = secure_filename(uploaded_file.filename) or uploaded_file.filename
                    stem = os.path.splitext(filename)[0].lower()
                    if stem not in required_filenames:
                        flash(
                            "Please upload the exact required file name(s): " + ", ".join(sorted(required_filenames)),
                            "error",
                        )
                        return render_template(
                            "client/upload.html",
                            username=session.get("user_email"),
                            initial_title=initial_title,
                            initial_document_date=initial_document_date,
                            required_filenames=sorted(required_filenames),
                            submission_status=submission_status,
                        ), 400

        for index, title in enumerate(titles, start=1):
            description = descriptions[index - 1] if index <= len(descriptions) else ""
            document_date = document_dates[index - 1] if index <= len(document_dates) else ""
            files = request.files.getlist(f"document_files_{index}")

            if not title.strip() or not document_date:
                continue

            for uploaded_file in files:
                if not uploaded_file or not uploaded_file.filename:
                    continue

                filename = secure_filename(uploaded_file.filename) or uploaded_file.filename
                if required_filenames:
                    stem = os.path.splitext(filename)[0].lower()
                    if stem not in required_filenames:
                        flash(
                            "Please upload the exact required file name(s): " + ", ".join(sorted(required_filenames)),
                            "error",
                        )
                        return render_template(
                            "client/upload.html",
                            username=session.get("user_email"),
                            initial_title=initial_title,
                            initial_document_date=initial_document_date,
                            required_filenames=sorted(required_filenames),
                            submission_status=submission_status,
                        ), 400

                content_type = uploaded_file.mimetype or ""
                if not is_allowed_submission_file(filename, content_type):
                    flash(
                        "Unsupported file type. Please upload a PDF, Word, or Excel document. PNG/JPG images are not accepted for submission.",
                        "error",
                    )
                    return render_template(
                        "client/upload.html",
                        username=session.get("user_email"),
                        initial_title=initial_title,
                        initial_document_date=initial_document_date,
                        required_filenames=sorted(required_filenames),
                        submission_status=submission_status,
                    ), 400

                file_size = get_uploaded_file_size(uploaded_file)
                if file_size > MAX_SUBMISSION_FILE_SIZE:
                    flash(
                        "File size exceeds the 50MB limit per file. Please upload a smaller file.",
                        "error",
                    )
                    return render_template(
                        "client/upload.html",
                        username=session.get("user_email"),
                        initial_title=initial_title,
                        initial_document_date=initial_document_date,
                        required_filenames=sorted(required_filenames),
                        submission_status=submission_status,
                    ), 400

                uploaded_file.seek(0)
                file_data = uploaded_file.read()
                if not file_data:
                    continue

                document_id = create_document(
                    current_app.config["DATABASE"],
                    session["user_id"],
                    title,
                    description,
                    document_date,
                    filename,
                    content_type,
                    file_data,
                )
                uploaded_files.append({
                    "filename": filename,
                    "size": format_file_size(file_size),
                })
                document_text = extract_document_text(file_data, filename, content_type)
                classification = classify_document(
                    document_text,
                    title=title,
                    description=description,
                    filename=filename,
                    content_type=content_type,
                    document_bytes=file_data,
                )
                validation = validate_document(
                    document_text,
                    title=title,
                    description=description,
                    filename=filename,
                    content_type=content_type,
                    expected_period=document_date,
                    document_bytes=file_data,
                )
                update_document_results(
                    current_app.config["DATABASE"], document_id, classification, validation
                )
                if validation["validation_status"] == "Incomplete":
                    create_initial_reminder(
                        {
                            "document_id": document_id,
                            "document_title": title,
                            "bookkeeping_period": document_date[:7],
                            "validation_reasons": validation.get("reasons", []),
                            "validation_reason": validation.get("validation_reason") or validation.get("logical_error"),
                            "logical_error": validation.get("logical_error") or validation.get("validation_reason"),
                            "client_email": g.account["email"],
                        },
                        current_app.config["DATABASE"],
                    )
                saved_count += 1

        if saved_count == 0:
            flash("Please choose at least one file to upload.", "error")
            return render_template(
                "client/upload.html",
                username=session.get("user_email"),
                initial_title=initial_title,
                initial_document_date=initial_document_date,
                submission_status=submission_status,
            ), 400

        flash(f"{saved_count} document file(s) submitted successfully.", "success")
        session["upload_success"] = {
            "count": saved_count,
            "file": uploaded_files[0] if uploaded_files else None,
            "uploaded_label": upload_time.strftime("%d %B %Y, %I:%M %p").lstrip("0"),
        }
        return redirect(url_for("client.upload"))

    upload_success = session.pop("upload_success", None)
    return render_template(
        "client/upload.html",
        username=session.get("user_email"),
        initial_title=initial_title,
        initial_document_date=initial_document_date,
        required_filenames=sorted(required_filenames),
        submission_status=submission_status,
        upload_success=upload_success,
    )


@client_bp.route("/notifications")
def notifications():
    redirect_response = require_client()
    if redirect_response:
        return redirect_response

    process_due_reminders(current_app.config["DATABASE"])
    return render_template(
        "client/notifications.html",
        username=session.get("user_email"),
        **list_client_notifications(current_app.config["DATABASE"], session["user_id"]),
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
        account_update_url=url_for("auth.update_account"),
        notifications_url=url_for("client.notifications"),
        submissions_url=url_for("client.upload"),
        username=session.get("user_name") or session.get("user_email"),
    )
