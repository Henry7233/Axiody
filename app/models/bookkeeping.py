"""Shared file listings for the bookkeeping page and its Excel export."""

from contextlib import closing

from app.models.documents import get_connection, normalize_document_type
from app.time import to_singapore


def _file_size(size_bytes):
    if size_bytes is None:
        return "0 KB"
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


def _display_dates(value):
    if not value:
        return "", ""
    try:
        parsed = to_singapore(value)
    except ValueError:
        return value, value
    hour = parsed.strftime("%I").lstrip("0") or "12"
    return (
        parsed.strftime("%b %d").replace(" 0", " "),
        f"{parsed.strftime('%b %d,')} {hour}:{parsed.strftime('%M')} {parsed.strftime('%p')}",
    )


def _category_for(document_type, ai_document_type):
    normalized_type = normalize_document_type(document_type or ai_document_type or "Other")
    return {
        "Invoice": "invoices",
        "Receipt": "receipts",
        "Bank Statement": "statements",
        "Other": "others",
    }.get(normalized_type, "others")


def get_bookkeeping_groups(database_path, period):
    # Keep the page's existing upload-month filter while grouping by stored type.
    with closing(get_connection(database_path)) as connection:
        rows = connection.execute(
            """
                  SELECT d.id, d.title, d.document_type, d.ai_document_type,
                        d.filename AS name, d.file_size AS size_bytes,
                   d.created_at,
                   COALESCE(NULLIF(TRIM(u.full_name), ''), u.email) AS submitted_by
            FROM documents d JOIN users u ON u.id = d.user_id
            WHERE substr(d.created_at, 1, 7) = ?
            ORDER BY d.created_at DESC, d.id DESC
            """, (period,),
        ).fetchall()
    grouped = {
        "invoices": {"label": "Invoices", "files": []},
        "receipts": {"label": "Receipts", "files": []},
        "statements": {"label": "Bank Statements", "files": []},
        "others": {"label": "Others", "files": []},
    }
    for row in rows:
        display_date, submitted_at = _display_dates(row["created_at"])
        category = _category_for(row["document_type"], row["ai_document_type"])
        grouped[category]["files"].append({
            "id": row["id"], "name": row["name"], "size": _file_size(row["size_bytes"]),
            "date": display_date, "submittedBy": row["submitted_by"] or row["name"],
            "submittedAt": submitted_at,
        })
    return grouped
