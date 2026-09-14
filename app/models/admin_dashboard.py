"""Read-only dashboard data from the application's document database."""

import json
from contextlib import closing
from datetime import date, datetime

from app.agents.reminder_agent import document_reminder
from app.models.documents import document_validation_status, get_connection


def get_admin_dashboard_data(database_path, period="all", today=None):
    today = today or date.today()
    with closing(get_connection(database_path)) as connection:
        stored_periods = connection.execute(
            "SELECT DISTINCT substr(document_date, 1, 7) FROM documents"
        ).fetchall()
        months = {today.strftime("%Y-%m")}
        for row in stored_periods:
            try:
                parsed = datetime.strptime(row[0] or "", "%Y-%m")
            except ValueError:
                continue
            months.add(parsed.strftime("%Y-%m"))
        period_options = [{"value": "all", "label": "All dates"}] + [
            {"value": month, "label": datetime.strptime(month, "%Y-%m").strftime("%B %Y")}
            for month in sorted(months, reverse=True)
        ]
        if period not in {option["value"] for option in period_options}:
            period = "all"

        total_clients = connection.execute(
            "SELECT COUNT(*) FROM users WHERE account_type = 'client'"
        ).fetchone()[0]
        rows = connection.execute(
            """
            SELECT d.id, d.user_id, d.title, d.filename, d.document_date, d.created_at,
                   d.document_type, d.ai_document_type, d.classification_status,
                   d.validation_status, d.validation_reasons,
                   COALESCE(NULLIF(TRIM(u.full_name), ''), u.email, 'Unknown client') AS client
            FROM documents d
            LEFT JOIN users u ON u.id = d.user_id
            WHERE (? = 'all' OR substr(d.document_date, 1, 7) = ?)
            ORDER BY d.created_at DESC, d.id DESC
            """, (period, period),
        ).fetchall()
        reminders = connection.execute(
            """
            SELECT n.created_at FROM notifications n
            JOIN documents d ON d.id = n.document_id
            WHERE n.status != 'resolved' AND lower(trim(d.validation_status)) = 'incomplete'
              AND (? = 'all' OR substr(d.document_date, 1, 7) = ?)
            """, (period, period),
        ).fetchall()

    documents = []
    attention = []
    counts = {"Invoice": 0, "Receipt": 0, "Bank Statement": 0, "Other": 0}
    type_labels = {"invoice": "Invoice", "receipt": "Receipt", "bank statement": "Bank Statement"}
    for row in rows:
        document = dict(row)
        stored_type = (row["document_type"] or "").strip() or (row["ai_document_type"] or "").strip()
        document["type"] = type_labels.get(stored_type.lower().replace("_", " "), "Other")
        counts[document["type"]] += 1
        validation = document_validation_status(row["validation_status"])
        document["status"] = "Bookkept" if validation == "Complete" else "Under Review"
        try:
            document["date"] = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")).strftime("%d %b %Y")
        except (AttributeError, ValueError):
            document["date"] = "Date not recorded"
        document["filename"] = row["filename"] or row["title"]
        if validation != "Complete":
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
            attention.append(document)
        documents.append(document)

    submitted = len(documents)
    complete = submitted - len(attention)
    # Match the portal's saved-reminder deadline rule without sending reminders.
    deadlines = [document_reminder(row["created_at"], today) for row in reminders]
    deadline = min((item for item in deadlines if item), key=lambda item: item["deadline"], default=None)
    days_left = (date.fromisoformat(deadline["deadline"]) - today).days if deadline else None
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
    }
