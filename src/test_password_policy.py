import os
import tempfile
import unittest
from urllib.parse import urlparse
from unittest.mock import patch

import database
import main


class RegistrationPasswordPolicyTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_NAME = self.db_path
        database.init_db()
        main.app.config["TESTING"] = True
        main.app.config["EMAIL_DELIVERY_MODE"] = "test"
        self.client = main.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def register(self, password, email="new@example.com", confirm_password=None):
        confirm_password = password if confirm_password is None else confirm_password
        return self.client.post(
            "/register",
            data={
                "username": "new-member",
                "email": email,
                "password": password,
                "confirm_password": confirm_password,
            },
        )

    def test_registration_rejects_weak_password(self):
        response = self.register("test")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"at least 8 characters", response.data)
        self.assertIsNone(database.get_user_by_email("new@example.com"))

    def test_password_policy_error_preserves_non_password_fields_only(self):
        response = self.register("weakpass")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'value="new-member"', response.data)
        self.assertIn(b'value="new@example.com"', response.data)
        self.assertNotIn(b'value="weakpass"', response.data)

    def test_password_mismatch_preserves_non_password_fields_only(self):
        response = self.register("StrongPass1", confirm_password="DifferentPass1")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Passwords do not match.", response.data)
        self.assertIn(b'value="new-member"', response.data)
        self.assertIn(b'value="new@example.com"', response.data)
        self.assertNotIn(b'value="StrongPass1"', response.data)
        self.assertNotIn(b'value="DifferentPass1"', response.data)

    def test_registration_accepts_policy_compliant_password(self):
        with patch.object(main, "send_transactional_email", return_value={"sent": True, "detail": "sent"}):
            response = self.register("StrongPass1")
        user = database.get_user_by_email("new@example.com")
        links = database.list_auth_email_links("email_sent")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/check-email")
        check_email_response = self.client.get("/check-email")
        self.assertIn(b"Check your email", check_email_response.data)
        self.assertIn(b"new@example.com", check_email_response.data)
        self.assertNotIn(b"/verify-email/", response.data)
        self.assertIsNotNone(user)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["purpose"], "registration_verification")
        self.assertEqual(links[0]["user_id"], user["id"])

    def test_registration_verification_requires_emailed_link_record(self):
        database.create_user("direct-user", "direct@example.com", "StrongPass1")
        user = database.get_user_by_email("direct@example.com")
        token = main.generate_verification_token("direct@example.com")

        response = self.client.get(f"/verify-email/{token}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid verification link", response.data)
        self.assertEqual(database.get_user_by_email("direct@example.com")["is_verified"], 0)

    def test_registration_verification_accepts_emailed_link(self):
        with patch.object(main, "send_transactional_email", return_value={"sent": True, "detail": "sent"}):
            self.register("StrongPass1")
        link = database.list_auth_email_links("email_sent")[0]["link"]

        response = self.client.get(urlparse(link).path)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Email verified successfully", response.data)
        self.assertIn(b'content="4; url=/login"', response.data)
        self.assertIn(b"window.location.href = \"/login\"", response.data)
        self.assertEqual(database.get_user_by_email("new@example.com")["is_verified"], 1)

    def test_registration_reports_email_delivery_failure_without_showing_link(self):
        with patch.object(main, "send_transactional_email", return_value={"sent": False, "detail": "not configured"}):
            response = self.register("StrongPass1")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"could not send a verification email", response.data)
        self.assertNotIn(b"/verify-email/", response.data)
        self.assertIsNone(database.get_user_by_email("new@example.com"))
        self.assertEqual(len(database.list_auth_email_links("email_failed")), 0)

    def test_registration_rejects_invalid_email_without_storing_user(self):
        with patch.object(main, "send_transactional_email") as send_email:
            response = self.register("StrongPass1", email="not-an-email")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Please enter a valid email address.", response.data)
        self.assertIsNone(database.get_user_by_email("not-an-email"))
        self.assertEqual(database.list_auth_email_links(), [])
        send_email.assert_not_called()

    def test_policy_requires_uppercase_lowercase_and_number(self):
        self.assertIsNotNone(main.password_policy_error("lowercase1"))
        self.assertIsNotNone(main.password_policy_error("UPPERCASE1"))
        self.assertIsNotNone(main.password_policy_error("NoNumbers"))
        self.assertIsNone(main.password_policy_error("ValidPass1"))


if __name__ == "__main__":
    unittest.main()
