import os
import tempfile
import unittest
from datetime import datetime, timedelta

import database
import main


class MeetingSchedulingTest(unittest.TestCase):
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

    def tearDown(self):
        os.remove(self.db_path)

    def login_admin(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_username"] = "jira"

    def login_member(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = self.member["id"]

    def future_at(self, days=2):
        return (self.now + timedelta(days=days)).isoformat(timespec="seconds")

    def test_admin_api_schedules_meeting_and_returns_record(self):
        self.login_admin()

        response = self.client.post("/api/meetings", json={
            "title": "Planning Session",
            "description": "Coordinate launch tasks",
            "meeting_at": self.future_at(),
            "location": "Room 1",
            "agenda": "Milestones",
            "invitees": ["Board", "Events"],
            "meeting_type": "committee",
        })
        payload = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(payload["meeting"]["title"], "Planning Session")
        self.assertEqual(payload["meeting"]["invitees"], ["Board", "Events"])
        self.assertEqual(payload["meeting"]["meeting_type"], "committee")
        self.assertEqual(database.get_meeting(payload["meeting_id"])["location"], "Room 1")

    def test_non_admin_cannot_schedule_meeting_via_api(self):
        self.login_member()

        response = self.client.post("/api/meetings", json={
            "title": "Unauthorized",
            "meeting_at": self.future_at(),
        })

        self.assertEqual(response.status_code, 403)

    def test_meeting_date_and_type_validation(self):
        self.login_admin()

        past = self.client.post("/api/meetings", json={
            "title": "Past",
            "meeting_at": (self.now - timedelta(days=1)).isoformat(timespec="seconds"),
        })
        invalid_type = self.client.post("/api/meetings", json={
            "title": "Bad Type",
            "meeting_at": self.future_at(),
            "meeting_type": "party",
        })
        very_far = self.client.post("/api/meetings", json={
            "title": "Too Far",
            "meeting_at": (self.now + timedelta(days=900)).isoformat(timespec="seconds"),
        })

        self.assertEqual(past.status_code, 400)
        self.assertIn("future", past.get_json()["error"])
        self.assertEqual(invalid_type.status_code, 400)
        self.assertIn("Meeting type", invalid_type.get_json()["error"])
        self.assertEqual(very_far.status_code, 400)
        self.assertIn("two years", very_far.get_json()["error"])

    def test_conflicting_meeting_same_location_is_rejected(self):
        meeting_at = self.now + timedelta(days=3)
        database.create_meeting("Planning", "", meeting_at, "Room 1", "Agenda", [], "jira")

        with self.assertRaisesRegex(ValueError, "already scheduled"):
            database.create_meeting("Overlap", "", meeting_at + timedelta(minutes=20), "Room 1", "", [], "jira")

    def test_meetings_api_filters_by_date_range(self):
        database.create_meeting("First", "", self.now + timedelta(days=2), "Room 1", "", [], "jira")
        database.create_meeting("Second", "", self.now + timedelta(days=8), "Room 2", "", [], "jira")
        self.login_member()

        response = self.client.get(
            "/api/meetings",
            query_string={
                "start": (self.now + timedelta(days=1)).date().isoformat(),
                "end": (self.now + timedelta(days=4)).date().isoformat(),
            },
        )
        invalid = self.client.get("/api/meetings", query_string={"start": "not-a-date"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["title"] for item in response.get_json()["meetings"]], ["First"])
        self.assertEqual(invalid.status_code, 400)

    def test_calendar_page_groups_and_filters_visible_meetings(self):
        database.create_meeting("Board Review", "Budget", self.now + timedelta(days=2), "Room 1", "Finance", ["Board"], "jira", "board")
        database.create_meeting("Training Lab", "Practice", self.now + timedelta(days=3), "Lab", "Skills", ["Members"], "jira", "training")
        self.login_member()

        response = self.client.get("/meetings", query_string={"type": "board", "q": "budget"})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Meeting Calendar", response.data)
        self.assertIn(b"Board Review", response.data)
        self.assertIn(b"Board", response.data)
        self.assertNotIn(b"Training Lab", response.data)

    def test_meetings_api_calendar_filters_and_default_upcoming_only(self):
        future_id = database.create_meeting("Future Planning", "", self.now + timedelta(days=2), "Room 1", "", [], "jira")
        past_id = database.create_meeting("Past Planning", "", self.now + timedelta(days=3), "Room 2", "", [], "jira")
        conn = database.get_connection()
        conn.execute(
            "UPDATE meetings SET meeting_at = ? WHERE id = ?",
            ((self.now - timedelta(days=3)).isoformat(timespec="seconds"), past_id),
        )
        conn.commit()
        conn.close()
        self.login_member()

        upcoming = self.client.get("/api/meetings")
        with_past = self.client.get("/api/meetings", query_string={"include_past": "1", "q": "Planning"})
        invalid_type = self.client.get("/api/meetings", query_string={"type": "social"})

        self.assertEqual([item["id"] for item in upcoming.get_json()["meetings"]], [future_id])
        self.assertEqual(
            [item["title"] for item in with_past.get_json()["meetings"]],
            ["Past Planning", "Future Planning"],
        )
        self.assertEqual(with_past.get_json()["calendar_days"][0]["meetings"][0]["title"], "Past Planning")
        self.assertEqual(invalid_type.status_code, 400)

    def test_attendance_and_minutes_validate_references(self):
        meeting_id = database.create_meeting("Planning", "", self.now + timedelta(days=2), "Room 1", "", [], "jira")

        database.record_attendance(meeting_id, self.member["id"], "present")
        database.add_meeting_minutes(meeting_id, "Minutes", "Decisions", uploaded_by="jira")

        with self.assertRaisesRegex(ValueError, "Meeting not found"):
            database.record_attendance(999, self.member["id"], "present")
        with self.assertRaisesRegex(ValueError, "Member not found"):
            database.record_attendance(meeting_id, 999, "present")
        with self.assertRaisesRegex(ValueError, "Minutes content"):
            database.add_meeting_minutes(meeting_id, "Minutes", "")


if __name__ == "__main__":
    unittest.main()
