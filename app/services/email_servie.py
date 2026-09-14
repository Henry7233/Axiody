from email.message import EmailMessage
import smtplib
from datetime import date, datetime
from pathlib import Path

from flask import current_app


class EmailConfigError(RuntimeError):
    """Raised when required SMTP settings are missing."""


class EmailConnectionError(RuntimeError):
    """Raised when all configured SMTP connection attempts fail."""


def _enabled(value):
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _smtp_modes(config):
    server = (config.get("MAIL_SERVER") or "").strip().lower()
    port = int(config.get("MAIL_PORT") or 587)
    use_ssl = _enabled(config.get("MAIL_USE_SSL"))
    use_tls = _enabled(config.get("MAIL_USE_TLS"))

    if server == "smtp.gmail.com":
        gmail_modes = [(587, False, True), (465, True, False)]
        configured = (port, use_ssl, use_tls)
        return [configured] + [mode for mode in gmail_modes if mode != configured] if configured[0] not in {465, 587} else gmail_modes

    modes = [(port, use_ssl, use_tls)]
    return modes


def _send_with_mode(server, port, use_ssl, use_tls, username, password, message):
    smtp = None
    if use_ssl:
        try:
            smtp = smtplib.SMTP_SSL(server, port, timeout=20)
            smtp.login(username, password)
            smtp.send_message(message)
            return
        finally:
            if smtp is not None:
                try:
                    smtp.quit()
                except (smtplib.SMTPServerDisconnected, TimeoutError, OSError):
                    pass

    try:
        smtp = smtplib.SMTP(server, port, timeout=20)
        smtp.ehlo()
        if use_tls:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(username, password)
        smtp.send_message(message)
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except (smtplib.SMTPServerDisconnected, TimeoutError, OSError):
                pass


def send_email(config, recipient, subject, body, html=None, inline_images=None):
    server = (config.get("MAIL_SERVER") or "").strip()
    username = (config.get("MAIL_USERNAME") or "").strip()
    password = "".join((config.get("MAIL_PASSWORD") or "").split())
    sender = (config.get("MAIL_DEFAULT_SENDER") or username).strip()

    if not server or not username or not password or not sender:
        raise EmailConfigError("Email settings are not configured.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")
        html_part = message.get_body(preferencelist=("html",))
        for image in inline_images or ():
            html_part.add_related(
                image["content"],
                maintype=image["maintype"],
                subtype=image["subtype"],
                cid=image["cid"],
                filename=image.get("filename"),
            )

    connection_errors = []
    for port, use_ssl, use_tls in _smtp_modes(config):
        try:
            _send_with_mode(server, port, use_ssl, use_tls, username, password, message)
            return
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused):
            raise
        except (smtplib.SMTPException, TimeoutError, OSError) as error:
            connection_errors.append(f"{server}:{port} {'SSL' if use_ssl else 'STARTTLS' if use_tls else 'plain'} failed: {error}")
            continue

    detail = "; ".join(connection_errors) or "No SMTP connection attempts were made."
    raise EmailConnectionError(detail)


def send_account_update_otp(config, recipient, code, expiry_minutes):
    body = (
        "Your AXIODY account verification code is:\n\n"
        f"{code}\n\n"
        f"This code expires in {expiry_minutes} minutes. "
        "If you did not request this account change, you can ignore this email."
    )
    html = current_app.jinja_env.get_template("auth/otp_email.html").render(
        otp=code,
        expiry_minutes=expiry_minutes,
        logo_url=config.get("MAIL_LOGO_URL", ""),
        password_reset=False,
    )
    send_email(config, recipient, "Your AXIODY verification code", body, html=html)


def send_password_reset_otp(config, recipient, code, expiry_minutes):
    body = (
        "Your AXIODY password reset code is:\n\n"
        f"{code}\n\n"
        f"This code expires in {expiry_minutes} minutes. "
        "If you did not request a password reset, you can ignore this email."
    )
    html = current_app.jinja_env.get_template("auth/otp_email.html").render(
        otp=code,
        expiry_minutes=expiry_minutes,
        logo_url=config.get("MAIL_LOGO_URL", ""),
        password_reset=True,
    )
    send_email(config, recipient, "Your AXIODY password reset code", body, html=html)


def send_reminder_email(config, recipient, subject, body, reminder=None):
    """Send a document reminder using the branded HTML template and text body."""
    reminder = reminder or {}
    deadline_value = reminder.get("deadline")
    if isinstance(deadline_value, datetime):
        deadline = deadline_value
    elif isinstance(deadline_value, date):
        deadline = deadline_value
    else:
        deadline = date.today()

    issue = reminder.get("issue") or body
    period = reminder.get("bookkeeping_period") or "the selected period"
    axiody_url = (config.get("AXIODY_URL") or "").strip().rstrip("/")
    logo_path = Path(current_app.static_folder) / "images" / "axiody-logo.svg"
    logo_content = logo_path.read_bytes()
    html = current_app.jinja_env.get_template("auth/reminder_email.html").render(
        logo_url="cid:axiody-logo",
        company_name=reminder.get("company_name") or "your account",
        bookkeeping_period=period,
        issue_sentence=reminder.get("issue_sentence") or f"was flagged because {issue}",
        issue=issue,
        deadline=deadline.strftime("%B %d, %Y"),
        deadline_day=deadline.strftime("%A"),
        deadline_short=deadline.strftime("%B %d"),
        axiody_url=f"{axiody_url}/login.html" if axiody_url else "/login.html",
        help_url=config.get("HELP_URL", config.get("AXIODY_URL", "")),
    )
    send_email(
        config,
        recipient,
        subject,
        body,
        html=html,
        inline_images=(
            {
                "content": logo_content,
                "maintype": "image",
                "subtype": "svg+xml",
                "cid": "axiody-logo",
                "filename": "axiody-logo.svg",
            },
        ),
    )
