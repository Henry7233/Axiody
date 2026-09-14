from datetime import datetime

from app.agents.reminder_agent import document_reminder
from app.models.documents import (
    document_filename_stem,
    document_validation_status,
    get_connection,
    validation_messages,
)
from app.time import SINGAPORE_TZ, to_singapore


def _timestamp(value):
    try:
        return to_singapore(value or "")
    except ValueError:
        return datetime.min.replace(tzinfo=SINGAPORE_TZ)


def list_client_notifications(database_path, user_id, today=None):
    """Group files by validation result and show saved reminders separately."""
    connection = get_connection(database_path)
    try:
        rows = connection.execute(
            """
            SELECT d.id, d.title, d.filename, d.document_date, d.created_at,
                   d.validation_status, d.validation_reasons,
                   n.id AS reminder_id, n.title AS reminder_title, n.message AS reminder_message,
                   n.created_at AS reminder_created_at, n.last_reminder_sent
            FROM documents d
            LEFT JOIN notifications n ON n.id = (
                SELECT reminder.id FROM notifications reminder
                JOIN documents original ON original.id = reminder.document_id
                WHERE original.user_id = d.user_id AND original.title = d.title
                  AND filename_stem(original.filename) = filename_stem(d.filename)
                  AND original.id <= d.id AND reminder.status != 'resolved'
                ORDER BY reminder.id DESC LIMIT 1
            )
            WHERE d.user_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM documents newer
                  WHERE newer.user_id = d.user_id AND newer.title = d.title
                    AND filename_stem(newer.filename) = filename_stem(d.filename)
                    AND newer.id > d.id
              )
            ORDER BY d.created_at DESC, d.id DESC
            """,
            (user_id,),
        ).fetchall()
    finally:
        connection.close()

    groups = {}
    for row in rows:
        period = (row["document_date"] or "")[:7]
        try:
            period_label = datetime.strptime(period, "%Y-%m").strftime("%B %Y")
        except ValueError:
            period_label = "Period not recorded"
        status = document_validation_status(row["validation_status"])
        group = groups.setdefault((row["title"], period, status), {
            "id": f'validation-{row["id"]}', "title": row["title"], "period_label": period_label,
            "files": [], "reminders": [], "deadlines": [],
            "updated": _timestamp(row["created_at"]),
        })
        reasons = validation_messages(row["validation_reasons"]) if status == "Incomplete" else []
        has_validation_feedback = bool(reasons)
        if status == "Incomplete" and not reasons:
            reasons = ["This file is incomplete, but no detailed validation feedback was saved. Please review and resubmit it."]
        group["files"].append({"filename": row["filename"], "document_date": row["document_date"], "status": status, "reasons": reasons,
                               "has_validation_feedback": has_validation_feedback})
        group["updated"] = max(group["updated"], _timestamp(row["created_at"]))
        if status != "Incomplete" or row["reminder_id"] is None:
            continue
        # A validation failure alone is not a reminder event. Only saved active
        # notifications create deadline cards; their date anchors the agent rule.
        reminder = document_reminder(row["reminder_created_at"], today)
        if reminder:
            group["deadlines"].append(reminder)
        deadline_group = groups.setdefault((row["title"], period, "deadlines"), {
            "id": f'reminder-{row["reminder_id"]}', "title": row["title"],
            "period_label": period_label, "category": "deadlines",
            "files": [], "reminders": [], "deadlines": [],
            "updated": _timestamp(row["reminder_created_at"]),
        })
        deadline_group["files"].append({"filename": row["filename"], "document_date": row["document_date"], "status": status, "reasons": []})
        if reminder:
            deadline_group["deadlines"].append(reminder)
        if row["reminder_message"]:
            message = {"title": row["reminder_title"], "message": row["reminder_message"]}
            if message not in deadline_group["reminders"]:
                deadline_group["reminders"].append(message)
        deadline_group["updated"] = max(deadline_group["updated"], _timestamp(row["last_reminder_sent"]), _timestamp(row["reminder_created_at"]))

    notifications = list(groups.values())
    for group in notifications:
        group["required_filenames"] = list(dict.fromkeys(
            document_filename_stem(file["filename"]) for file in group["files"]
        ))
        document_dates = {file["document_date"] for file in group["files"]}
        group["upload_date"] = next(iter(document_dates)) if len(document_dates) == 1 else ""
        is_reminder = group.get("category") == "deadlines"
        group["incomplete_count"] = 0 if is_reminder else sum(file["status"] == "Incomplete" for file in group["files"])
        group["pending_count"] = sum(file["status"] == "Pending validation" for file in group["files"])
        complete = len(group["files"]) - group["incomplete_count"] - group["pending_count"]
        group["deadline"] = min(group["deadlines"], key=lambda item: item["deadline"]) if group["deadlines"] else None
        if is_reminder:
            group.update(status=group["deadline"]["kind"] if group["deadline"] else "Reminder",
                         color="blue", message=group["deadline"]["message"] if group["deadline"] else "You have a saved reminder for these documents. Review the reminder details below.")
        elif group["incomplete_count"]:
            group.update(status="Incomplete", color="red", category="changes",
                         message=f'{group["incomplete_count"]} file(s) need changes. Review the feedback below and upload corrected copies.')
        elif group["pending_count"]:
            group.update(status="Pending validation", color="blue", category="pending",
                         message=f'{group["pending_count"]} file(s) are awaiting validation. Results will appear here when available.')
        else:
            group.update(status="Complete", color="green", category="successful",
                         message=f'All {complete} file(s) have passed validation. No changes are needed.')
        group["created_at"] = group["updated"].isoformat()
        group["created_label"] = group["updated"].strftime("%b %d, %Y, %H:%M SGT")
    notifications.sort(key=lambda group: group["updated"], reverse=True)
    reminders = [group for group in notifications if group["category"] == "deadlines"]
    deadlines = [group["deadline"] for group in reminders if group["deadline"]]
    return {
        "notifications": notifications,
        "complete_count": sum(group["status"] == "Complete" for group in notifications),
        "changes_count": sum(group["incomplete_count"] > 0 for group in notifications),
        "files_to_change": sum(group["incomplete_count"] for group in notifications),
        "deadline_count": len(reminders),
        "next_deadline": min(deadlines, key=lambda item: item["deadline"]) if deadlines else None,
    }
