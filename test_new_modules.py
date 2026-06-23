import os
import tempfile
import unittest
from datetime import datetime, timedelta

import database
import main


class NewModulesTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_NAME = self.db_path
        database.init_db()
        database.create_user("member", "member@example.com", "Password1")
        self.member = database.get_user_by_email("member@example.com")
        database.mark_user_verified(self.member["id"])
        self.member = database.get_user_by_email("member@example.com")
        main.app.config.update(TESTING=True)
        self.client = main.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def login_member(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = self.member["id"]

    def login_admin(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_username"] = "jira"

    def test_voting_event_creation_validation_and_duplicate_vote_prevention(self):
        now = datetime.utcnow().replace(microsecond=0)
        with self.assertRaisesRegex(ValueError, "future"):
            database.create_voting_event("Past", "", ["A", "B"], now - timedelta(days=1), now + timedelta(days=1))
        event_id = database.create_voting_event(
            "Board Election",
            "Choose a candidate",
            ["A", "B"],
            now + timedelta(seconds=1),
            now + timedelta(days=1),
            "jira",
            {"membership_status": "verified"},
        )
        conn = database.get_connection()
        conn.execute("UPDATE voting_events SET start_at = ? WHERE id = ?", ((now - timedelta(minutes=1)).isoformat(timespec="seconds"), event_id))
        option_id = conn.execute("SELECT id FROM voting_options WHERE event_id = ? LIMIT 1", (event_id,)).fetchone()["id"]
        conn.commit()
        conn.close()

        self.assertTrue(database.verify_vote_eligibility(event_id, self.member["id"])["eligible"])
        database.cast_vote(event_id, option_id, self.member["id"], "secret")
        with self.assertRaisesRegex(ValueError, "already voted"):
            database.cast_vote(event_id, option_id, self.member["id"], "secret")
        self.assertEqual(database.get_voting_results(event_id)["total_votes"], 1)

    def test_voting_api_restricts_results_for_member_before_close(self):
        now = datetime.utcnow().replace(microsecond=0)
        event_id = database.create_voting_event("Open Vote", "", ["A", "B"], now + timedelta(seconds=1), now + timedelta(days=1), "jira")
        conn = database.get_connection()
        conn.execute("UPDATE voting_events SET start_at = ? WHERE id = ?", ((now - timedelta(minutes=1)).isoformat(timespec="seconds"), event_id))
        conn.commit()
        conn.close()
        self.login_member()
        self.assertEqual(self.client.get(f"/api/voting/events/{event_id}/results").status_code, 403)

    def test_whatsapp_import_parser_and_analytics(self):
        text = "\n".join([
            "6/20/26, 9:01 AM - Alex: Hello team",
            "6/20/26, 9:03 AM - Sam: <Media omitted>",
            "6/21/26, 10:10 AM - Alex: Update",
            "6/21/26, 10:11 AM - Messages and calls are end-to-end encrypted.",
        ])
        messages = main.parse_whatsapp_export(text, "chat.txt")
        self.assertEqual(len(messages), 3)
        database.store_whatsapp_messages(messages)
        analytics = database.whatsapp_analytics()
        self.assertEqual(analytics["top_participants"][0]["label"], "Alex")
        self.assertTrue(any(row["label"] == "media" for row in analytics["media_types"]))

    def test_meeting_scheduling_attendance_and_minutes(self):
        meeting_at = datetime.utcnow().replace(microsecond=0) + timedelta(days=2)
        meeting_id = database.create_meeting("Planning", "", meeting_at, "Room 1", "Agenda", [], "jira")
        with self.assertRaisesRegex(ValueError, "already scheduled"):
            database.create_meeting("Conflict", "", meeting_at + timedelta(minutes=10), "Room 1", "", [], "jira")
        database.record_attendance(meeting_id, self.member["id"], "present")
        database.add_meeting_minutes(meeting_id, "Minutes", "Decisions recorded", uploaded_by="jira")
        self.assertEqual(database.meeting_attendance_summary()[0]["present"], 1)

    def test_financial_report_budget_and_bug_workflow(self):
        database.create_transaction("2026-06-01", "income", "Dues", 500, "Member dues", "jira")
        database.create_transaction("2026-06-02", "expense", "Venue", 100, "Room", "jira")
        database.upsert_budget("Venue", 120, "2026")
        report = database.financial_report()
        self.assertEqual(report["net_balance"], 400)
        self.assertEqual(report["budgets"][0]["spent"], 100)

        bug_id = database.create_bug_report("Broken export", "High", "Click export", "CSV", "Error", "member")
        database.update_bug_status(bug_id, "Verified", "Regression passed")
        self.assertEqual(database.list_bug_reports()[0]["status"], "Verified")


if __name__ == "__main__":
    unittest.main()
