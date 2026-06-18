import os
import tempfile
import unittest
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
        with patch.object(main.mail, "send"):
            response = self.register("StrongPass1")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Account created", response.data)
        self.assertIsNotNone(database.get_user_by_email("new@example.com"))

    def test_policy_requires_uppercase_lowercase_and_number(self):
        self.assertIsNotNone(main.password_policy_error("lowercase1"))
        self.assertIsNotNone(main.password_policy_error("UPPERCASE1"))
        self.assertIsNotNone(main.password_policy_error("NoNumbers"))
        self.assertIsNone(main.password_policy_error("ValidPass1"))


if __name__ == "__main__":
    unittest.main()
