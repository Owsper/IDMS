import os
import tempfile
import unittest
from datetime import datetime, timedelta

import database
import main


class EventNotificationsTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_NAME = self.db_path
        database.init_db()
        main.app.config.update(TESTING=True)
        self.client = main.app.test_client()
        self.now = datetime.utcnow().replace(microsecond=0)

    def tearDown(self):
        os.remove(self.db_path)

    def login_admin(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_username"] = "jira"

    def login_member(self, user_id):
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = user_id

    def create_member(self, username, email, verified=True):
        database.create_user(username, email, "Password1")
        user = database.get_user_by_email(email)
        if verified:
            database.mark_user_verified(user["id"])
        return database.get_user_by_email(email)

    def test_notification_template_rendering_requires_values(self):
        rendered = database.render_notification_template(
            "meeting_scheduled",
            {"title": "Planning", "meeting_at": "2026-07-10T10:00:00", "location": "Room 1"},
        )

        self.assertEqual(rendered["category"], "meeting")
        self.assertIn("Planning", rendered["title"])
        with self.assertRaisesRegex(ValueError, "Missing"):
            database.render_notification_template("meeting_scheduled", {"title": "Planning"})

    def test_voting_event_triggers_targeted_verified_notifications(self):
        verified = self.create_member("verified", "verified@example.com", verified=True)
        pending = self.create_member("pending", "pending@example.com", verified=False)

        database.create_voting_event(
            "Board Vote",
            "",
            ["A", "B"],
            self.now + timedelta(days=1),
            self.now + timedelta(days=2),
            "jira",
            {"membership_status": "verified"},
        )
        notifications = database.list_notifications()

        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["recipient_id"], verified["id"])
        self.assertNotEqual(notifications[0]["recipient_id"], pending["id"])
        self.assertEqual(notifications[0]["template_key"], "voting_opened")
        self.assertEqual(notifications[0]["status"], "sent")

    def test_meeting_scheduling_creates_scheduled_reminder_history(self):
        member = self.create_member("member", "member@example.com")
        meeting_at = self.now + timedelta(days=3)

        database.create_meeting("Planning", "", meeting_at, "Room 1", "Agenda", [], "jira")
        notifications = database.list_notifications(recipient_id=member["id"])
        scheduled_notice = next(item for item in notifications if item["template_key"] == "meeting_scheduled")

        self.assertEqual(scheduled_notice["category"], "meeting")
        self.assertEqual(scheduled_notice["status"], "scheduled")
        self.assertEqual(scheduled_notice["scheduled_for"], meeting_at.isoformat(timespec="seconds"))

    def test_manual_event_reminder_form_and_api_history(self):
        member = self.create_member("member", "member@example.com")
        self.login_admin()

        response = self.client.post(
            "/notifications",
            data={
                "title": "Ceremony Reminder",
                "body": "Starts soon",
                "channel": "in-app",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Notification queued", response.data)

        self.login_member(member["id"])
        api = self.client.get("/api/notifications")
        payload = api.get_json()

        self.assertEqual(api.status_code, 200)
        self.assertEqual(payload["notifications"][0]["title"], "Ceremony Reminder")
        self.assertEqual(payload["notifications"][0]["recipient_id"], member["id"])

    def test_member_sees_only_their_notifications_and_broadcasts(self):
        member_a = self.create_member("member-a", "a@example.com")
        member_b = self.create_member("member-b", "b@example.com")
        database.create_notification("event", "Broadcast", "Everyone")
        database.create_notification("event", "Private A", "Only A", recipient_id=member_a["id"])
        database.create_notification("event", "Private B", "Only B", recipient_id=member_b["id"])

        self.login_member(member_a["id"])
        payload = self.client.get("/api/notifications").get_json()
        titles = [item["title"] for item in payload["notifications"]]

        self.assertIn("Broadcast", titles)
        self.assertIn("Private A", titles)
        self.assertNotIn("Private B", titles)


if __name__ == "__main__":
    unittest.main()
