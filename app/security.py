import secrets

from flask import abort, request, session


def csrf_token():
    # Reuse one unpredictable form token per session to prevent forged submissions.
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def validate_csrf():
    # Require the submitted token to match the session token. compare_digest avoids
    # revealing how much of the token matched through comparison timing.
    token = session.get("csrf_token")
    if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
        abort(400, description="Invalid form token. Reload the page and try again.")
