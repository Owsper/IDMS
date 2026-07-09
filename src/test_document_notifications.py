import os
import tempfile
import unittest
from io import BytesIO

import database
import main


class DocumentNotificationsTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.upload_dir = tempfile.TemporaryDirectory()
        database.DB_NAME = self.db_path
        database.init_db()
        main.app.config.update(TESTING=True, UPLOAD_FOLDER=self.upload_dir.name)
        self.client = main.app.test_client()
        self.member = self.create_member("member", "member@example.com")
        self.opted_out = self.create_member("quiet", "quiet@example.com", notification_opt_in=0)

    def tearDown(self):
        self.upload_dir.cleanup()
        os.remove(self.db_path)

    def create_member(self, username, email, notification_opt_in=1):
        database.create_user(username, email, "Password1")
        user = database.get_user_by_email(email)
        database.mark_user_verified(user["id"])
        conn = database.get_connection()
        conn.execute(
            "UPDATE users_data SET notification_opt_in = ? WHERE id = ?",
            (notification_opt_in, user["id"]),
        )
        conn.commit()
        conn.close()
        return database.get_user_by_email(email)

    def login_admin(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_username"] = "jira"

    def login_member(self, user_id):
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = user_id

    def post_document_upload(self, filename="minutes.pdf"):
        return self.client.post(
            "/import-files",
            data={
                "category": "General",
                "files": (BytesIO(b"approved document"), filename),
            },
            content_type="multipart/form-data",
        )

    def test_admin_approved_upload_notifies_opted_in_members(self):
        self.login_admin()

        response = self.post_document_upload()
        member_notifications = database.list_notifications(recipient_id=self.member["id"])
        quiet_notifications = database.list_notifications(recipient_id=self.opted_out["id"])

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Uploaded and approved", response.data)
        self.assertEqual(len(member_notifications), 1)
        self.assertEqual(member_notifications[0]["template_key"], "document_uploaded")
        self.assertEqual(member_notifications[0]["category"], "document")
        self.assertEqual(member_notifications[0]["status"], "sent")
        self.assertEqual(member_notifications[0]["metadata"]["title"], "minutes.pdf")
        self.assertEqual(quiet_notifications, [])

    def test_member_pending_upload_does_not_trigger_document_notification(self):
        self.login_member(self.member["id"])

        response = self.post_document_upload("draft.pdf")
        notifications = database.list_notifications(recipient_id=self.member["id"])

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"pending approval", response.data)
        self.assertEqual(notifications, [])

    def test_profile_updates_document_notification_preference(self):
        self.login_member(self.member["id"])

        response = self.client.post(
            "/profile",
            data={
                "full_name": "Member One",
                "username": self.member["username"],
                "email": self.member["email"],
                "team_role": "Developer",
                "profile_picture": "",
                "skills": "",
                "bio": "",
                "notification_opt_in": "0",
            },
        )
        updated = database.get_user_by_email(self.member["email"])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(updated["notification_opt_in"], 0)


if __name__ == "__main__":
    unittest.main()
