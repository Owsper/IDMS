import os
import tempfile
import unittest
from urllib.parse import urlparse
from unittest.mock import patch

import database
import main


class PasswordResetFlowTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_NAME = self.db_path
        database.init_db()
        database.create_user("reset-user", "reset@example.com", "old-password")
        user = database.get_user_by_email("reset@example.com")
        database.mark_user_verified(user["id"])

        main.app.config.update(TESTING=True, MAIL_SUPPRESS_SEND=True)
        self.client = main.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def test_member_can_request_and_complete_password_reset(self):
        with patch.object(main.mail, "send") as send:
            response = self.client.post(
                "/forgot-password",
                data={"email": "reset@example.com"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"If an account exists", response.data)
        send.assert_called_once()
        message = send.call_args.args[0]

        reset_url = next(
            line for line in message.body.splitlines()
            if "/reset-password/" in line
        )
        reset_path = urlparse(reset_url).path

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
        with patch.object(main.mail, "send") as send:
            response = self.client.post(
                "/forgot-password",
                data={"email": "unknown@example.com"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"If an account exists", response.data)
        send.assert_not_called()

    def test_new_password_is_validated(self):
        user = database.get_user_by_email("reset@example.com")
        token = main.generate_password_reset_token(user)
        response = self.client.post(
            f"/reset-password/{token}",
            data={"password": "short", "confirm_password": "short"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"at least 8 characters", response.data)


if __name__ == "__main__":
    unittest.main()
