from datetime import date, datetime

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from app.agents.classification_agent import classify_document, extract_document_text
from app.agents.reminder_agent import resolve_replaced_document_reminders
from app.models.documents import create_document, update_document_classification


client_bp = Blueprint("client", __name__, url_prefix="/client")


# Shared by the dashboard preview and its all-records overlay.
DOCUMENT_CATEGORIES = [
    {"id": "sales-revenue-records", "name": "Sales & Revenue Records", "icon": "chart", "documents": ["Sales invoices", "Payment receipts", "Bank transaction proof"]},
    {"id": "business-expenses", "name": "Business Expenses", "icon": "cart", "documents": ["Expense invoices", "Expense receipts", "Payment proof"]},
    {"id": "bank-reconciliation", "name": "Bank Reconciliation", "icon": "bank", "documents": ["Bank statements", "Transaction records", "Reconciliation reports"]},
]


def bookkeeping_periods():
    today = date.today()
    periods = []
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

    account = g.account
    try:
        member_since = datetime.fromisoformat(account["created_at"]).strftime("%b %Y")
    except (TypeError, ValueError):
        member_since = "Not provided"

    return render_template(
        "client/dashboard.html", account=account, member_since=member_since,
        periods=periods, selected_period=selected_period, categories=DOCUMENT_CATEGORIES,
        period_label=next(period["label"] for period in periods if period["value"] == selected_period),
        username=account["full_name"] or account["email"],
    )


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

    if request.method == "POST":
        titles = request.form.getlist("title")
        descriptions = request.form.getlist("description")
        document_dates = request.form.getlist("document_date")
        saved_count = 0

        for index, title in enumerate(titles, start=1):
            description = descriptions[index - 1] if index <= len(descriptions) else ""
            document_date = document_dates[index - 1] if index <= len(document_dates) else ""
            files = request.files.getlist(f"document_files_{index}")

            if not title.strip() or not document_date:
                continue

            resolve_replaced_document_reminders(
                session["user_id"],
                title,
                document_date,
                current_app.config["DATABASE"],
            )

            for uploaded_file in files:
                if not uploaded_file or not uploaded_file.filename:
                    continue

                file_data = uploaded_file.read()
                if not file_data:
                    continue

                filename = secure_filename(uploaded_file.filename) or uploaded_file.filename
                content_type = uploaded_file.mimetype or ""
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
                document_text = extract_document_text(file_data, filename, content_type)
                classification = classify_document(
                    document_text,
                    title=title,
                    description=description,
                    filename=filename,
                    content_type=content_type,
                    document_bytes=file_data,
                )
                update_document_classification(
                    current_app.config["DATABASE"], document_id, classification
                )
                saved_count += 1

        if saved_count == 0:
            flash("Please choose at least one file to upload.", "error")
            return render_template("client/upload.html", username=session.get("user_email")), 400

        flash(f"{saved_count} document file(s) submitted successfully.", "success")
        return redirect(url_for("client.upload"))

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
        account_update_url=url_for("auth.update_account"),
        notifications_url=url_for("client.notifications"),
        submissions_url=url_for("client.upload"),
        username=session.get("user_name") or session.get("user_email"),
    )
