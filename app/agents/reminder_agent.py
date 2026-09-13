from datetime import date, datetime, timedelta
from flask import current_app

from app.models.documents import get_connection
from app.services.email_servie import send_email


REMINDER_INTERVAL_DAYS = 5
REMINDER_DAY = 25


def _database_path(database_path=None):
    if database_path is not None:
        return database_path
    return current_app.config["DATABASE"]


def _get_connection(database_path):
    return get_connection(database_path)


def _deadline(today):
    return date(today.year, today.month, REMINDER_DAY)


def _next_reminder(today):
    next_date = today + timedelta(days=REMINDER_INTERVAL_DAYS)
    return next_date.isoformat() if next_date < _deadline(today) else None


def document_reminder(created_at, today=None):
    """Describe the submission's deadline for the portal without sending email."""
    today = today or date.today()
    try:
        submitted = date.fromisoformat((created_at or "")[:10])
    except ValueError:
        return None
    deadline = _deadline(submitted)
    label = deadline.strftime("%b %d, %Y")
    if today > deadline:
        message = f"The submission deadline was {label}. Please upload the outstanding corrections."
        kind = "Deadline passed"
    elif today == deadline:
        message = "Your submission deadline is today. Please upload the outstanding corrections."
        kind = "Due today"
    else:
        message = f"Please upload the outstanding corrections by {label}."
        kind = "Deadline reminder"
    return {"deadline": deadline.isoformat(), "deadline_label": label, "kind": kind, "message": message}


def _message(validation_data, deadline):
    document_title = validation_data.get("document_title") or "Your document"
    reasons = validation_data.get("validation_reasons") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    reason = validation_data.get("validation_reason") or ", ".join(
        reason.replace("_", " ") for reason in reasons if reason
    ) or "The document is missing required information."
    period = validation_data.get("bookkeeping_period")
    period_text = f" for {period}" if period else ""
    message = (
        f"{document_title}{period_text} is incomplete. {reason} "
        f"Please correct or resubmit it before {deadline.strftime('%B %d')}."
    )
    return "Incomplete Document Submission", message


def create_initial_reminder(validation_data, database_path=None, mail_config=None):
    """Persist and immediately deliver a reminder from validation output."""
    database_path = _database_path(database_path)
    document_id = validation_data.get("document_id")
    if not document_id:
        return {"success": False, "message": "document_id is required."}

    today = date.today()
    deadline = _deadline(today)
    if today >= deadline:
        return {
            "success": False,
            "message": "Reminder deadline has already been reached.",
        }

    email_sent = False
    email_error = ""
    connection = _get_connection(database_path)
    try:
        document = connection.execute(
            "SELECT id, title FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if not document:
            return {"success": False, "message": "Document not found."}

        active = connection.execute(
            """
            SELECT id FROM notifications
            WHERE document_id = ? AND status != 'resolved'
            LIMIT 1
            """,
            (document_id,),
        ).fetchone()
        if active:
            return {
                "success": False,
                "message": "Active notification already exists.",
                "notification_id": active["id"],
            }

        data = dict(validation_data)
        data.setdefault("document_title", document["title"])
        title, message = _message(data, deadline)
        cursor = connection.execute(
            """
            INSERT INTO notifications (
                document_id, title, message, status, last_reminder_sent,
                next_reminder_date, reminder_count
            ) VALUES (?, ?, ?, 'unread', ?, ?, 1)
            """,
            (
                document_id,
                title,
                message,
                date.today().isoformat(),
                _next_reminder(today),
            ),
        )
        connection.commit()
        notification_id = cursor.lastrowid
    finally:
        connection.close()

    recipient = validation_data.get("client_email")
    if recipient:
        try:
            send_email(mail_config or current_app.config, recipient, title, message)
            email_sent = True
        except Exception as error:
            email_error = str(error)
            current_app.logger.warning(
                "Reminder notification %s was saved, but email delivery failed: %s",
                notification_id,
                error,
            )

    return {
        "success": True,
        "notification_id": notification_id,
        "email_sent": email_sent,
        "email_error": email_error,
        "message": "Initial reminder created.",
    }


def process_due_reminders(database_path=None, mail_config=None, today=None):
    """Send due reminders every five days until the 25th of the month."""
    database_path = _database_path(database_path)
    today = today or date.today()
    connection = _get_connection(database_path)
    sent = 0
    resolved = 0
    try:
        rows = connection.execute(
            """
            SELECT n.id, n.title, n.message, n.next_reminder_date,
                   (
                       SELECT latest.validation_status FROM documents latest
                       WHERE latest.user_id = d.user_id AND latest.title = d.title
                         AND latest.document_date = d.document_date
                         AND filename_stem(latest.filename) = filename_stem(d.filename)
                       ORDER BY latest.id DESC LIMIT 1
                   ) AS validation_status, u.email
            FROM notifications n
            JOIN documents d ON d.id = n.document_id
            JOIN users u ON u.id = d.user_id
            WHERE n.status != 'resolved'
            """
        ).fetchall()

        for row in rows:
            status = (row["validation_status"] or "").lower()
            if status in {"success", "complete", "completed"}:
                connection.execute(
                    "UPDATE notifications SET status = 'resolved', next_reminder_date = NULL WHERE id = ?",
                    (row["id"],),
                )
                resolved += 1
                continue

            next_date = row["next_reminder_date"]
            if today >= _deadline(today) or not next_date:
                connection.execute(
                    "UPDATE notifications SET next_reminder_date = NULL WHERE id = ?",
                    (row["id"],),
                )
                continue

            if today < datetime.strptime(next_date, "%Y-%m-%d").date():
                continue

            try:
                send_email(
                    mail_config or current_app.config,
                    row["email"],
                    row["title"],
                    row["message"],
                )
            except Exception as error:
                current_app.logger.warning(
                    "Due reminder %s email delivery failed: %s",
                    row["id"],
                    error,
                )
                continue
            connection.execute(
                """
                UPDATE notifications
                SET last_reminder_sent = ?, next_reminder_date = ?,
                    reminder_count = reminder_count + 1
                WHERE id = ?
                """,
                (today.isoformat(), _next_reminder(today), row["id"]),
            )
            sent += 1

        connection.commit()
    finally:
        connection.close()
    return {"success": True, "sent": sent, "resolved": resolved}


def resolve_notification(document_id, database_path=None):
    """Stop all active reminders for a document after a replacement upload."""
    database_path = _database_path(database_path)
    connection = _get_connection(database_path)
    try:
        connection.execute(
            """
            UPDATE notifications
            SET status = 'resolved', next_reminder_date = NULL
            WHERE document_id = ? AND status != 'resolved'
            """,
            (document_id,),
        )
        connection.commit()
    finally:
        connection.close()
    return {"success": True, "message": "Notification resolved."}


def resolve_replaced_document_reminders(
    user_id, title, document_date, database_path=None
):
    """Stop reminders for an older submission replaced by a new upload."""
    database_path = _database_path(database_path)
    connection = _get_connection(database_path)
    try:
        connection.execute(
            """
            UPDATE notifications
            SET status = 'resolved', next_reminder_date = NULL
            WHERE status != 'resolved'
              AND document_id IN (
                  SELECT id FROM documents
                  WHERE user_id = ? AND title = ? AND document_date = ?
              )
            """,
            (user_id, title.strip(), document_date),
        )
        connection.commit()
    finally:
        connection.close()
    return {"success": True, "message": "Replaced document reminders resolved."}
