"""Read-only dashboard data from the application's document database."""

import json
from contextlib import closing
from datetime import date, datetime

from app.agents.reminder_agent import document_reminder
from app.models.documents import (
    document_category, document_validation_status, get_connection,
    is_bookkeeping_ready, needs_document_approval,
)
from app.time import singapore_today, to_singapore


def get_admin_period_options(database_path, today=None):
    """Share the dashboard's recent and stored bookkeeping months."""
    today = today or singapore_today()
    recent_month_values = []
    current = date(today.year, today.month, 1)
    for _ in range(12):
        recent_month_values.append(current.strftime("%Y-%m"))
        year = current.year
        month = current.month - 1
        if month == 0:
            year -= 1
            month = 12
        current = date(year, month, 1)

    with closing(get_connection(database_path)) as connection:
        stored_periods = connection.execute(
            "SELECT DISTINCT substr(document_date, 1, 7) FROM documents"
        ).fetchall()
        months = set(recent_month_values)
        for row in stored_periods:
            try:
                parsed = datetime.strptime(row[0] or "", "%Y-%m")
            except ValueError:
                continue
            months.add(parsed.strftime("%Y-%m"))

        ordered_months = sorted(months, reverse=True)
        priority_months = recent_month_values[:]
        for month in ordered_months:
            if month not in set(priority_months):
                priority_months.append(month)
        period_options = [{"value": "all", "label": "All dates"}] + [
            {"value": month, "label": datetime.strptime(month, "%Y-%m").strftime("%B %Y")}
            for month in priority_months
        ]
    return period_options


def get_admin_dashboard_data(database_path, period="all", today=None):
    today = today or singapore_today()
    period_options = get_admin_period_options(database_path, today)
    if period not in {option["value"] for option in period_options}:
        period = "all"

    with closing(get_connection(database_path)) as connection:
        total_clients = connection.execute(
            "SELECT COUNT(*) FROM users WHERE account_type = 'client'"
        ).fetchone()[0]
        rows = connection.execute(
            """
            SELECT d.id, d.user_id, d.title, d.filename, d.document_date, d.created_at,
                   d.document_type, d.ai_document_type, d.classification_status,
                   d.validation_status, d.validation_reasons, d.reviewed_by,
                   COALESCE(NULLIF(TRIM(u.full_name), ''), u.email, 'Unknown client') AS client
            FROM documents d
            LEFT JOIN users u ON u.id = d.user_id
            WHERE (? = 'all' OR substr(d.document_date, 1, 7) = ?)
            ORDER BY d.created_at DESC, d.id DESC
            """, (period, period),
        ).fetchall()
        reminders = connection.execute(
            """
                        SELECT n.created_at, n.title, n.next_reminder_date, n.reminder_count,
                                     d.title AS document_title,
                                     COALESCE(NULLIF(TRIM(u.full_name), ''), u.email, 'Unknown client') AS client
                        FROM notifications n
            JOIN documents d ON d.id = n.document_id
                        JOIN users u ON u.id = d.user_id
            WHERE n.status != 'resolved' AND lower(trim(d.validation_status)) = 'incomplete'
              AND (? = 'all' OR substr(d.document_date, 1, 7) = ?)
                        ORDER BY n.next_reminder_date IS NULL, n.next_reminder_date ASC, n.created_at DESC
                        """, (period, period),
        ).fetchall()

    documents = []
    attention = []
    counts = {"Invoice": 0, "Receipt": 0, "Bank Statement": 0, "Other": 0}
    for row in rows:
        document = dict(row)
        category = document_category(row)
        document["type"] = category if category in counts else "Other"
        counts[document["type"]] += 1
        validation = document_validation_status(row["validation_status"])
        bookkept = is_bookkeeping_ready(row)
        document["status"] = "Bookkept" if bookkept else "Under Review"
        try:
            document["date"] = to_singapore(row["created_at"]).strftime("%d %b %Y")
        except (AttributeError, ValueError):
            document["date"] = "Date not recorded"
        document["filename"] = row["filename"] or row["title"]
        if not bookkept:
            try:
                reasons = json.loads(row["validation_reasons"] or "[]")
            except (TypeError, ValueError):
                reasons = []
            if not isinstance(reasons, list):
                reasons = []
            reasons = [reason.replace("_", " ") for reason in reasons if isinstance(reason, str) and reason.strip()]
            document["reason"] = ", ".join(reasons) if validation == "Incomplete" and reasons else (
                "Validation failed" if validation == "Incomplete" else "Pending validation"
            )
            if validation == "Complete":
                document["reason"] = "Awaiting approval" if needs_document_approval(row) else "Pending classification"
            attention.append(document)
        documents.append(document)

    submitted = len(documents)
    complete = submitted - len(attention)
    # Match the portal's saved-reminder deadline rule without sending reminders.
    deadlines = [document_reminder(row["created_at"], today) for row in reminders]
    deadline = min((item for item in deadlines if item), key=lambda item: item["deadline"], default=None)
    days_left = (date.fromisoformat(deadline["deadline"]) - today).days if deadline else None
    reminder_preview = [
        {
            "client": row["client"],
            "document_title": row["document_title"] or row["title"] or "Document reminder",
            "next_reminder_date": row["next_reminder_date"],
            "reminder_count": int(row["reminder_count"] or 0),
        }
        for row in reminders[:3]
    ]
    invoice_end = counts["Invoice"] / submitted * 100 if submitted else 0
    receipt_end = invoice_end + (counts["Receipt"] / submitted * 100 if submitted else 0)
    bank_end = receipt_end + (counts["Bank Statement"] / submitted * 100 if submitted else 0)
    return {
        "period_options": period_options,
        "selected_period": period,
        "selected_period_label": next(option["label"] for option in period_options if option["value"] == period),
        "total_clients": total_clients,
        "submitted_documents": submitted,
        "bookkept_documents": complete,
        "under_review": len(attention),
        "bookkeeping_percentage": round(complete / submitted * 100) if submitted else 0,
        "invoice_count": counts["Invoice"], "receipt_count": counts["Receipt"],
        "bank_statement_count": counts["Bank Statement"], "other_count": counts["Other"],
        "donut_background": (
            f"conic-gradient(#448ef7 0% {invoice_end}%, #5fcfa6 {invoice_end}% {receipt_end}%, "
            f"#f6b932 {receipt_end}% {bank_end}%, #a9b5c9 {bank_end}% 100%)"
        ) if submitted else "#e7edf5",
        "recent_submissions": documents, "attention_documents": attention,
        "deadline": deadline, "days_left": days_left,
        "active_followups": len(reminders),
        "total_reminder_emails": sum(int(row["reminder_count"] or 0) for row in reminders),
        "reminder_preview": reminder_preview,
    }
