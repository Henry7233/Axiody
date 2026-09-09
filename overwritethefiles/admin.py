from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for

from app.models.users import add_admin_account, get_user_by_id, list_accounts_by_role, remove_admin_access
from app.models.users import decide_admin_request, list_admin_requests
from app.security import csrf_token, validate_csrf


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


# Run this guard before every admin route, including POST actions.
@admin_bp.before_request
def require_login():
    if "user_id" in session:
        # Recheck the saved role so permission changes affect existing sessions.
        user = get_user_by_id(current_app.config["DATABASE"], session["user_id"])
        if user is not None:
            # Any signed-in account can view Admin Management through /admin or
            # its page aliases. Role checks still apply to account-changing actions.
            if request.method in ("GET", "HEAD") and request.endpoint in ("admin.index", "admin.management"):
                return None
            if not user["is_admin"]:
                # Show the access-request page instead of a Forbidden error.
                # A 303 also prevents an attempted admin POST from being replayed.
                return redirect(url_for("auth.admin_access"), code=303)
            return None
        session.clear()

    flash("Please log in first.", "error")
    return redirect(url_for("auth.login"))


@admin_bp.post("/access-requests/<int:request_id>/decision")
def decide_access(request_id):
    # Validate the form token before accepting a change to another user's access.
    validate_csrf()
    decision = request.form.get("decision")
    if decision not in ("approved", "rejected"):
        abort(400, description="Choose Approve or Reject.")
    if not decide_admin_request(
        current_app.config["DATABASE"], request_id, session["user_id"], decision
    ):
        abort(409, description="This request is unavailable or has already been reviewed.")
    flash(f"Admin access request {decision}.", "success")
    # Redirect to a GET after saving so refreshing the page does not repeat the POST.
    return redirect(url_for("admin.management"), code=303)


def render_management(error=None, email="", status=200):
    access_requests = list_admin_requests(current_app.config["DATABASE"])
    return render_template(
        "admin/admin_management.html",
        admins=list_accounts_by_role(current_app.config["DATABASE"], True),
        available_accounts=list_accounts_by_role(current_app.config["DATABASE"], False),
        pending_requests=[item for item in access_requests if item["status"] == "pending" and not item["is_admin"]],
        csrf_token=csrf_token(), error=error, email=email,
        **admin_context("management"),
    ), status


@admin_bp.route("/admin_management.html")
@admin_bp.route("/management")
def management():
    return render_management()


@admin_bp.post("/admins/add")
def add_account():
    validate_csrf()
    try:
        email = add_admin_account(
            current_app.config["DATABASE"], session["user_id"],
            request.form.get("mode"), request.form.get("email", ""),
            request.form.get("password", ""),
        )
    except ValueError as error:
        return render_management(error=str(error), email=request.form.get("email", ""), status=400)
    except PermissionError:
        return redirect(url_for("auth.admin_access"), code=303)
    flash(f"Admin access added for {email}.", "success")
    return redirect(url_for("admin.management"), code=303)


@admin_bp.post("/admins/<int:user_id>/remove")
def remove_account(user_id):
    validate_csrf()
    try:
        email = remove_admin_access(current_app.config["DATABASE"], session["user_id"], user_id)
    except ValueError as error:
        return render_management(error=str(error), status=400)
    except PermissionError:
        return redirect(url_for("auth.admin_access"), code=303)
    flash(f"Admin access removed for {email}. Their account remains available.", "success")
    return redirect(url_for("admin.management"), code=303)


def admin_context(active_page):
    # Supply shared navigation links and highlight the current admin page.
    return {
        "active_page": active_page,
        "admin_nav": True,
        "home_url": url_for("admin.dashboard"),
        "profile_url": url_for("admin.settings") + "#account-information",
        "settings_url": url_for("admin.settings"),
        "username": session.get("user_name") or session.get("user_email"),
    }


@admin_bp.route("")
@admin_bp.route("/")
def index():
    # Both /admin and /admin/ open the admin account management page.
    return redirect(url_for("admin.management"))


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
