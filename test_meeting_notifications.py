import os
import tempfile
import unittest
from datetime import datetime, timedelta

import database
import main


class MeetingNotificationsTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_NAME = self.db_path
        database.init_db()
        main.app.config.update(TESTING=True)
        self.client = main.app.test_client()
        self.now = datetime.utcnow().replace(microsecond=0)
        database.create_user("member", "member@example.com", "Password1")
        self.member = database.get_user_by_email("member@example.com")
        database.mark_user_verified(self.member["id"])
        self.member = database.get_user_by_email("member@example.com")

    def tearDown(self):
        os.remove(self.db_path)

    def login_admin(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_username"] = "jira"

    def test_meeting_creation_schedules_before_meeting_reminders(self):
        meeting_at = self.now + timedelta(days=3)

        meeting_id = database.create_meeting("Board Prep", "", meeting_at, "Room 2", "Agenda", [], "jira")
        notifications = database.list_notifications(recipient_id=self.member["id"])
        reminders = [item for item in notifications if item["template_key"] == "meeting_reminder"]

        self.assertEqual(len(reminders), 2)
        self.assertEqual({item["metadata"]["meeting_id"] for item in reminders}, {meeting_id})
        self.assertEqual(
            {item["scheduled_for"] for item in reminders},
            {
                (meeting_at - timedelta(days=1)).isoformat(timespec="seconds"),
                (meeting_at - timedelta(hours=1)).isoformat(timespec="seconds"),
            },
        )
        self.assertTrue(all(item["status"] == "scheduled" for item in reminders))

    def test_due_meeting_reminders_are_marked_sent(self):
        meeting_at = self.now + timedelta(days=2)
        database.create_meeting("Training", "", meeting_at, "Lab", "Agenda", [], "jira")

        result = database.process_due_notifications(self.now + timedelta(days=1, minutes=1))
        reminders = [
            item for item in database.list_notifications(recipient_id=self.member["id"])
            if item["template_key"] == "meeting_reminder"
        ]
        sent_reminders = [item for item in reminders if item["status"] == "sent"]
        scheduled_reminders = [item for item in reminders if item["status"] == "scheduled"]

        self.assertEqual(result["count"], 1)
        self.assertEqual(len(sent_reminders), 1)
        self.assertEqual(len(scheduled_reminders), 1)
        self.assertIsNotNone(sent_reminders[0]["sent_at"])

    def test_due_notifications_api_requires_admin_and_records_status(self):
        meeting_at = self.now + timedelta(days=2)
        database.create_meeting("Committee", "", meeting_at, "Room 1", "Agenda", [], "jira")

        member_response = self.client.post("/api/notifications/process-due")
        self.login_admin()
        admin_response = self.client.post("/api/notifications/process-due")

        self.assertEqual(member_response.status_code, 302)
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(admin_response.get_json()["count"], 0)


if __name__ == "__main__":
    unittest.main()
