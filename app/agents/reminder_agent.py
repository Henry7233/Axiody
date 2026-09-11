import sqlite3
from datetime import date, datetime, timedelta


DATABASE = "database.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def create_initial_reminder(document_id):
    """
    Create the first notification immediately
    when a document is INCOMPLETE.
    """

    conn = get_db_connection()

    document = conn.execute(
        """
        SELECT *
        FROM documents
        WHERE id = ?
        """,
        (document_id,)
    ).fetchone()

    if not document:
        conn.close()

        return {
            "success": False,
            "message": "Document not found."
        }

    # Only process incomplete documents
    if document["validation_status"] != "INCOMPLETE":
        conn.close()

        return {
            "success": False,
            "message": "Document is not incomplete."
        }

    # Prevent duplicate active notification
    existing_notification = conn.execute(
        """
        SELECT *
        FROM notifications
        WHERE document_id = ?
          AND status != 'resolved'
        """,
        (document_id,)
    ).fetchone()

    if existing_notification:
        conn.close()

        return {
            "success": False,
            "message": "Active notification already exists."
        }

    today = date.today()

    deadline = date(
        today.year,
        today.month,
        25
    )

    # Do not start reminder cycle on/after 25th
    if today >= deadline:
        conn.close()

        return {
            "success": False,
            "message": "Reminder deadline has already been reached."
        }

    title = "Incomplete Document Submission"

    validation_reason = (
        document["validation_reason"]
        if document["validation_reason"]
        else "The document did not pass validation."
    )

    document_title = (
        document["title"]
        if document["title"]
        else "your document"
    )

    message = (
        f"{document_title} is incomplete. "
        f"{validation_reason} "
        f"Please correct or resubmit the document before the 25th."
    )

    next_reminder = today + timedelta(days=3)

    # If +3 days is already on/after the 25th,
    # don't schedule another normal reminder
    if next_reminder >= deadline:
        next_reminder_value = None
    else:
        next_reminder_value = next_reminder.isoformat()

    cursor = conn.execute(
        """
        INSERT INTO notifications (
            document_id,
            title,
            message,
            status,
            last_reminder_sent,
            next_reminder_date,
            reminder_count,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            document_id,
            title,
            message,
            "unread",
            today.isoformat(),
            next_reminder_value,
            1
        )
    )

    notification_id = cursor.lastrowid

    conn.commit()
    conn.close()

    # Temporary output
    send_notification(
        document_id=document_id,
        title=title,
        message=message
    )

    return {
        "success": True,
        "notification_id": notification_id,
        "message": "Initial reminder created and sent."
    }


def process_due_reminders():
    """
    Check all active notifications.

    If:
    - document is still INCOMPLETE
    - today >= next_reminder_date
    - today is before the 25th

    then send another reminder.
    """

    conn = get_db_connection()

    today = date.today()

    notifications = conn.execute(
        """
        SELECT
            n.id AS notification_id,
            n.document_id,
            n.title,
            n.message,
            n.status,
            n.last_reminder_sent,
            n.next_reminder_date,
            n.reminder_count,
            d.validation_status,
            d.validation_reason,
            d.title AS document_title
        FROM notifications n
        JOIN documents d
            ON n.document_id = d.id
        WHERE n.status != 'resolved'
        """
    ).fetchall()

    for notification in notifications:

        document_id = notification["document_id"]

        # Stop reminders if document is complete
        if notification["validation_status"] == "COMPLETE":

            conn.execute(
                """
                UPDATE notifications
                SET status = 'resolved',
                    next_reminder_date = NULL
                WHERE id = ?
                """,
                (notification["notification_id"],)
            )

            continue

        # Only remind incomplete documents
        if notification["validation_status"] != "INCOMPLETE":
            continue

        deadline = date(
            today.year,
            today.month,
            25
        )

        # Stop once the 25th is reached
        if today >= deadline:

            conn.execute(
                """
                UPDATE notifications
                SET next_reminder_date = NULL
                WHERE id = ?
                """,
                (notification["notification_id"],)
            )

            continue

        # No next reminder scheduled
        if not notification["next_reminder_date"]:
            continue

        next_reminder_date = datetime.strptime(
            notification["next_reminder_date"],
            "%Y-%m-%d"
        ).date()

        # Not due yet
        if today < next_reminder_date:
            continue

        # Send reminder
        send_notification(
            document_id=document_id,
            title=notification["title"],
            message=notification["message"]
        )

        new_next_reminder = today + timedelta(days=3)

        # Do not schedule after the 25th
        if new_next_reminder >= deadline:
            next_reminder_value = None
        else:
            next_reminder_value = new_next_reminder.isoformat()

        conn.execute(
            """
            UPDATE notifications
            SET last_reminder_sent = ?,
                next_reminder_date = ?,
                reminder_count = reminder_count + 1
            WHERE id = ?
            """,
            (
                today.isoformat(),
                next_reminder_value,
                notification["notification_id"]
            )
        )

    conn.commit()
    conn.close()


def resolve_notification(document_id):
    """
    Manually resolve a reminder when the document
    becomes COMPLETE.
    """

    conn = get_db_connection()

    conn.execute(
        """
        UPDATE notifications
        SET status = 'resolved',
            next_reminder_date = NULL
        WHERE document_id = ?
          AND status != 'resolved'
        """,
        (document_id,)
    )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Notification resolved."
    }


def send_notification(document_id, title, message):
    """
    Temporary notification sender.

    Later you can replace this with:
    - Website notification
    - Gmail SMTP email
    - Both
    """

    print("\n==============================")
    print("REMINDER SENT")
    print("==============================")
    print(f"Document ID: {document_id}")
    print(f"Title: {title}")
    print(f"Message: {message}")
    print("==============================\n")