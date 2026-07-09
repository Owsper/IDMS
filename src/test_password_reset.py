import os
import tempfile
import unittest
from urllib.parse import urlparse
from unittest.mock import patch

import database
import main


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args = None
        self.sent_message = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def starttls(self, context=None):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.sent_message = message


class TransactionalEmailDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.previous_config = {
            "EMAIL_DELIVERY_MODE": main.app.config.get("EMAIL_DELIVERY_MODE"),
            "EMAIL_FROM_ADDRESS": main.app.config.get("EMAIL_FROM_ADDRESS"),
            "EMAIL_FROM_NAME": main.app.config.get("EMAIL_FROM_NAME"),
            "SMTP_HOST": main.app.config.get("SMTP_HOST"),
            "SMTP_PORT": main.app.config.get("SMTP_PORT"),
            "SMTP_USERNAME": main.app.config.get("SMTP_USERNAME"),
            "SMTP_PASSWORD": main.app.config.get("SMTP_PASSWORD"),
            "SMTP_USE_TLS": main.app.config.get("SMTP_USE_TLS"),
            "SMTP_USE_SSL": main.app.config.get("SMTP_USE_SSL"),
        }
        FakeSMTP.instances = []

    def tearDown(self):
        main.app.config.update(self.previous_config)

    def test_smtp_delivery_sends_email(self):
        main.app.config.update(
            EMAIL_DELIVERY_MODE="smtp",
            EMAIL_FROM_ADDRESS="noreply@example.com",
            EMAIL_FROM_NAME="Pexel",
            SMTP_HOST="smtp.example.com",
            SMTP_PORT=587,
            SMTP_USERNAME="smtp-user",
            SMTP_PASSWORD="smtp-password",
            SMTP_USE_TLS=True,
            SMTP_USE_SSL=False,
        )

        with patch("smtplib.SMTP", FakeSMTP):
            result = main.send_transactional_email(
                "member@example.com",
                "Verify your Pexel account",
                "Text body",
                "<p>HTML body</p>",
            )

        smtp = FakeSMTP.instances[0]
        message = smtp.sent_message

        self.assertTrue(result["sent"])
        self.assertEqual(result["provider"], "smtp")
        self.assertEqual(smtp.host, "smtp.example.com")
        self.assertEqual(smtp.port, 587)
        self.assertTrue(smtp.started_tls)
        self.assertEqual(smtp.login_args, ("smtp-user", "smtp-password"))
        self.assertEqual(message["From"], "Pexel <noreply@example.com>")
        self.assertEqual(message["To"], "member@example.com")
        self.assertEqual(message["Subject"], "Verify your Pexel account")
        self.assertIn("Text body", message.get_body(preferencelist=("plain",)).get_content())
        self.assertIn("<p>HTML body</p>", message.get_body(preferencelist=("html",)).get_content())

    def test_smtp_delivery_requires_host_and_sender(self):
        main.app.config.update(
            EMAIL_DELIVERY_MODE="smtp",
            SMTP_HOST="",
            EMAIL_FROM_ADDRESS="",
        )

        result = main.send_transactional_email("member@example.com", "Subject", "Text", "<p>HTML</p>")

        self.assertFalse(result["sent"])
        self.assertEqual(result["provider"], "smtp")
        self.assertIn("PEXEL_SMTP_HOST", result["detail"])


class PasswordResetFlowTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_NAME = self.db_path
        database.init_db()
        database.create_user("reset-user", "reset@example.com", "old-password")
        user = database.get_user_by_email("reset@example.com")
        database.mark_user_verified(user["id"])

        main.app.config.update(TESTING=True, EMAIL_DELIVERY_MODE="test")
        self.client = main.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def test_member_can_request_and_complete_password_reset(self):
        with patch.object(main, "send_transactional_email", return_value={"sent": True, "detail": "sent"}):
            response = self.client.post(
                "/forgot-password",
                data={"email": "reset@example.com"},
            )
        links = database.list_auth_email_links("email_sent")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"If an account exists", response.data)
        self.assertNotIn(b"/reset-password/", response.data)
        self.assertEqual(len(links), 1)
        reset_path = urlparse(links[0]["link"]).path

        response = self.client.post(
            reset_path,
            data={"password": "NewPassword1", "confirm_password": "NewPassword1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Your password has been reset", response.data)
        self.assertIsNone(database.user_login("reset@example.com", "old-password"))
        self.assertIsNotNone(database.user_login("reset@example.com", "NewPassword1"))

        # Changing the password invalidates the signed link after its first use.
        self.assertEqual(self.client.get(reset_path).status_code, 400)

    def test_unknown_email_uses_the_same_public_response(self):
        with patch.object(main, "send_transactional_email") as send_email:
            response = self.client.post(
                "/forgot-password",
                data={"email": "unknown@example.com"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"If an account exists", response.data)
        send_email.assert_not_called()
        self.assertEqual(database.list_auth_email_links("email_sent"), [])

    def test_password_reset_link_is_emailed_to_user(self):
        with patch.object(main, "send_transactional_email", return_value={"sent": True, "detail": "sent"}) as send_email:
            response = self.client.post(
                "/forgot-password",
                data={"email": "reset@example.com"},
            )

        links = database.list_auth_email_links("email_sent")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"If an account exists", response.data)
        self.assertNotIn(b"/reset-password/", response.data)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["purpose"], "password_reset")
        self.assertIn("/reset-password/", links[0]["link"])
        send_email.assert_called_once()
        self.assertEqual(send_email.call_args.args[0], "reset@example.com")

    def test_password_reset_delivery_failure_still_hides_link(self):
        with patch.object(main, "send_transactional_email", return_value={"sent": False, "detail": "not configured"}):
            response = self.client.post(
                "/forgot-password",
                data={"email": "reset@example.com"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"If an account exists", response.data)
        self.assertNotIn(b"/reset-password/", response.data)
        self.assertEqual(len(database.list_auth_email_links("email_failed")), 1)

    def test_direct_reset_token_without_emailed_link_is_rejected(self):
        user = database.get_user_by_email("reset@example.com")
        token = main.generate_password_reset_token(user)
        response = self.client.get(f"/reset-password/{token}")

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"invalid or has already been used", response.data)

    def test_reset_form_has_show_password_buttons(self):
        with patch.object(main, "send_transactional_email", return_value={"sent": True, "detail": "sent"}):
            self.client.post(
                "/forgot-password",
                data={"email": "reset@example.com"},
            )
        reset_path = urlparse(database.list_auth_email_links("email_sent")[0]["link"]).path

        response = self.client.get(reset_path)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="password" type="password"', response.data)
        self.assertIn(b'id="confirm_password" type="password"', response.data)
        self.assertIn(b"togglePassword()", response.data)
        self.assertIn(b"toggleConfirmPassword()", response.data)

    def test_new_password_is_validated(self):
        with patch.object(main, "send_transactional_email", return_value={"sent": True, "detail": "sent"}):
            self.client.post(
                "/forgot-password",
                data={"email": "reset@example.com"},
            )
        reset_path = urlparse(database.list_auth_email_links("email_sent")[0]["link"]).path
        response = self.client.post(
            reset_path,
            data={"password": "short", "confirm_password": "short"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"at least 8 characters", response.data)


if __name__ == "__main__":
    unittest.main()
