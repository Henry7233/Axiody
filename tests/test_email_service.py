import smtplib
import unittest
from unittest.mock import patch

from app.services.email_servie import EmailConfigError, send_email


class BrokenSmtp:
    def __init__(self, *args, **kwargs):
        raise ConnectionResetError("reset")


class UnsupportedTlsSmtp:
    def __init__(self, *args, **kwargs):
        pass

    def ehlo(self):
        return 250, b"ok"

    def starttls(self):
        raise smtplib.SMTPNotSupportedError("STARTTLS unavailable")

    def quit(self):
        return 221, b"bye"


class WorkingSmtp:
    logins = []
    sent = 0

    def __init__(self, *args, **kwargs):
        self.args = args

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        return 250, b"ok"

    def starttls(self):
        return 220, b"ready"

    def login(self, username, password):
        self.logins.append((username, password))

    def send_message(self, message):
        type(self).sent += 1

    def quit(self):
        return 221, b"bye"


class DisconnectOnQuitSmtp(WorkingSmtp):
    def quit(self):
        raise smtplib.SMTPServerDisconnected("closed after send")


class EmailServiceTest(unittest.TestCase):
    def setUp(self):
        WorkingSmtp.logins = []
        WorkingSmtp.sent = 0
        DisconnectOnQuitSmtp.logins = []
        DisconnectOnQuitSmtp.sent = 0

    def test_requires_mail_settings(self):
        with self.assertRaises(EmailConfigError):
            send_email({}, "client@example.com", "Subject", "Body")

    def test_gmail_prefers_starttls_even_if_env_uses_ssl(self):
        config = {
            "MAIL_SERVER": "smtp.gmail.com",
            "MAIL_PORT": 465,
            "MAIL_USE_SSL": True,
            "MAIL_USE_TLS": False,
            "MAIL_USERNAME": "axiody@example.com",
            "MAIL_PASSWORD": "abcd efgh ijkl mnop",
        }

        with patch.object(smtplib, "SMTP", WorkingSmtp):
            send_email(config, "client@example.com", "Subject", "Body")

        self.assertEqual(WorkingSmtp.logins, [("axiody@example.com", "abcdefghijklmnop")])
        self.assertEqual(WorkingSmtp.sent, 1)

    def test_gmail_starttls_connection_failure_falls_back_to_ssl(self):
        config = {
            "MAIL_SERVER": "smtp.gmail.com",
            "MAIL_PORT": 587,
            "MAIL_USE_SSL": False,
            "MAIL_USE_TLS": True,
            "MAIL_USERNAME": "axiody@example.com",
            "MAIL_PASSWORD": "abcdefghijklmnop",
        }

        with patch.object(smtplib, "SMTP", BrokenSmtp), patch.object(smtplib, "SMTP_SSL", WorkingSmtp):
            send_email(config, "client@example.com", "Subject", "Body")

        self.assertEqual(WorkingSmtp.logins, [("axiody@example.com", "abcdefghijklmnop")])
        self.assertEqual(WorkingSmtp.sent, 1)

    def test_gmail_starttls_protocol_failure_falls_back_to_ssl(self):
        config = {
            "MAIL_SERVER": "smtp.gmail.com",
            "MAIL_PORT": 587,
            "MAIL_USE_SSL": False,
            "MAIL_USE_TLS": True,
            "MAIL_USERNAME": "axiody@example.com",
            "MAIL_PASSWORD": "abcdefghijklmnop",
        }

        with patch.object(smtplib, "SMTP", UnsupportedTlsSmtp), patch.object(smtplib, "SMTP_SSL", WorkingSmtp):
            send_email(config, "client@example.com", "Subject", "Body")

        self.assertEqual(WorkingSmtp.logins, [("axiody@example.com", "abcdefghijklmnop")])
        self.assertEqual(WorkingSmtp.sent, 1)

    def test_disconnect_after_successful_send_is_not_reported_as_failure(self):
        config = {
            "MAIL_SERVER": "smtp.example.com",
            "MAIL_PORT": 465,
            "MAIL_USE_SSL": True,
            "MAIL_USE_TLS": False,
            "MAIL_USERNAME": "axiody@example.com",
            "MAIL_PASSWORD": "abcdefghijklmnop",
        }

        with patch.object(smtplib, "SMTP_SSL", DisconnectOnQuitSmtp):
            send_email(config, "client@example.com", "Subject", "Body")

        self.assertEqual(DisconnectOnQuitSmtp.sent, 1)


if __name__ == "__main__":
    unittest.main()
