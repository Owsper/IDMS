import os
import tempfile
import unittest
from datetime import datetime, timedelta

import database
import main


class MeetingAttendanceTrackingTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_NAME = self.db_path
        database.init_db()
        main.app.config.update(TESTING=True)
        self.client = main.app.test_client()
        self.now = datetime.utcnow().replace(microsecond=0)
        database.create_user("alice", "alice@example.com", "Password1")
        database.create_user("bob", "bob@example.com", "Password1")
        self.alice = database.get_user_by_email("alice@example.com")
        self.bob = database.get_user_by_email("bob@example.com")
        self.meeting_id = database.create_meeting(
            "Attendance Review",
            "",
            self.now + timedelta(days=2),
            "Room 1",
            "Participation",
            [],
            "jira",
        )

    def tearDown(self):
        os.remove(self.db_path)

    def login_admin(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_username"] = "jira"

    def login_member(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = self.alice["id"]

    def test_record_attendance_updates_status_and_audit_fields(self):
        database.record_attendance(self.meeting_id, self.alice["id"], "present", "admin")
        database.record_attendance(self.meeting_id, self.alice["id"], "excused", "admin-two")

        records = database.meeting_attendance_report(meeting_id=self.meeting_id)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "excused")
        self.assertEqual(records[0]["recorded_by"], "admin-two")
        self.assertEqual(records[0]["member"], self.alice["username"])

    def test_attendance_summary_counts_all_statuses_and_rate(self):
        database.record_attendance(self.meeting_id, self.alice["id"], "present", "jira")
        database.record_attendance(self.meeting_id, self.bob["id"], "absent", "jira")

        summary = database.meeting_attendance_summary()[0]

        self.assertEqual(summary["label"], "Attendance Review")
        self.assertEqual(summary["present"], 1)
        self.assertEqual(summary["absent"], 1)
        self.assertEqual(summary["excused"], 0)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["attendance_rate"], 50.0)

    def test_admin_attendance_api_returns_summary_and_records(self):
        database.record_attendance(self.meeting_id, self.alice["id"], "present", "jira")
        self.login_admin()

        response = self.client.get("/api/meetings/attendance", query_string={"meeting_id": self.meeting_id})
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["records"][0]["meeting"], "Attendance Review")
        self.assertEqual(payload["records"][0]["status"], "present")
        self.assertEqual(payload["summary"][0]["present"], 1)

    def test_attendance_api_and_csv_are_admin_only(self):
        self.login_member()
        denied = self.client.get("/api/meetings/attendance")
        self.assertEqual(denied.status_code, 403)

        self.login_admin()
        database.record_attendance(self.meeting_id, self.alice["id"], "present", "jira")
        csv_response = self.client.get("/api/meetings/attendance.csv")

        self.assertEqual(csv_response.status_code, 200)
        self.assertIn(b"meeting,meeting_at,member,email,status,recorded_by,recorded_at", csv_response.data)
        self.assertIn(b"Attendance Review", csv_response.data)


if __name__ == "__main__":
    unittest.main()
