from email.message import EmailMessage
import smtplib

from flask import current_app


def send_email(config, recipient, subject, body, html=None):
    server = config.get("MAIL_SERVER")
    username = config.get("MAIL_USERNAME")
    password = config.get("MAIL_PASSWORD")
    sender = config.get("MAIL_DEFAULT_SENDER") or username
    port = int(config.get("MAIL_PORT") or 587)

    if not server or not username or not password or not sender:
        raise RuntimeError("Email settings are not configured.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")

    if config.get("MAIL_USE_SSL"):
        with smtplib.SMTP_SSL(server, port, timeout=20) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(server, port, timeout=20) as smtp:
        if config.get("MAIL_USE_TLS"):
            smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(message)


def send_account_update_otp(config, recipient, code, expiry_minutes):
    body = (
        "Your AXIODY account verification code is:\n\n"
        f"{code}\n\n"
        f"This code expires in {expiry_minutes} minutes. "
        "If you did not request this account change, you can ignore this email."
    )
    html = current_app.jinja_env.get_template("otp_email.html").render(
        otp=code,
        expiry_minutes=expiry_minutes,
        logo_url=config.get("MAIL_LOGO_URL", ""),
    )
    send_email(config, recipient, "Your AXIODY verification code", body, html=html)
