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

    def register(self, password):
        return self.client.post(
            "/register",
            data={
                "username": "new-member",
                "email": "new@example.com",
                "password": password,
                "confirm_password": password,
            },
        )

    def test_registration_rejects_weak_password(self):
        response = self.register("test")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"at least 8 characters", response.data)
        self.assertIsNone(database.get_user_by_email("new@example.com"))

    def test_registration_accepts_policy_compliant_password(self):
        with patch.object(main, "send_transactional_email", return_value={"sent": True, "detail": "sent"}):
            response = self.register("StrongPass1")
        user = database.get_user_by_email("new@example.com")
        links = database.list_auth_email_links("email_sent")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Account created", response.data)
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
        self.assertEqual(database.get_user_by_email("new@example.com")["is_verified"], 1)

    def test_registration_reports_email_delivery_failure_without_showing_link(self):
        with patch.object(main, "send_transactional_email", return_value={"sent": False, "detail": "not configured"}):
            response = self.register("StrongPass1")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"could not be sent", response.data)
        self.assertNotIn(b"/verify-email/", response.data)
        self.assertEqual(len(database.list_auth_email_links("email_failed")), 1)

    def test_policy_requires_uppercase_lowercase_and_number(self):
        self.assertIsNotNone(main.password_policy_error("lowercase1"))
        self.assertIsNotNone(main.password_policy_error("UPPERCASE1"))
        self.assertIsNotNone(main.password_policy_error("NoNumbers"))
        self.assertIsNone(main.password_policy_error("ValidPass1"))


if __name__ == "__main__":
    unittest.main()
