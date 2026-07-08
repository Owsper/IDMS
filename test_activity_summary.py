import os
import tempfile
import unittest
from datetime import datetime, timedelta

import database
import main


class ActivitySummaryTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_NAME = self.db_path
        database.init_db()
        main.app.config.update(TESTING=True)
        self.client = main.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def login_admin(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_username"] = "jira"

    def seed_activity(self):
        now = datetime.utcnow().replace(microsecond=0)
        database.create_meeting("Planning", "", now + timedelta(days=2), "Room 1", "Agenda", [], "jira")
        database.create_voting_event("Board Vote", "", ["A", "B"], now + timedelta(days=1), now + timedelta(days=2), "jira")
        database.save_upload_metadata(None, "guide.pdf", "guide.pdf", "application/pdf", 100, "abc", approved=0)
        database.log_activity("Documents", "Document uploaded", "guide.pdf", actor_name="jira")
        database.create_transaction("2026-07-08", "income", "Dues", 50, "Member dues", "jira")

    def test_activity_summary_collects_data_reports_and_recent_feed(self):
        self.seed_activity()

        summary = database.activity_summary("weekly")

        self.assertEqual(summary["period"], "weekly")
        self.assertEqual(summary["stats"]["meetings"], 1)
        self.assertEqual(summary["stats"]["votes"], 1)
        self.assertEqual(summary["stats"]["documents"], 1)
        self.assertEqual(summary["stats"]["transactions"], 1)
        self.assertTrue(any(item["module"] == "Documents" for item in summary["modules"]))
        self.assertTrue(any("Core activity" in item for item in summary["highlights"]))
        self.assertEqual(len(summary["widgets"]), 4)
        self.assertGreaterEqual(len(summary["feed"]), 4)
        self.assertTrue(summary["timeline"])

    def test_activity_summary_api_requires_admin_and_returns_widgets(self):
        self.seed_activity()

        self.assertEqual(self.client.get("/api/admin/activity-summary").status_code, 302)

        self.login_admin()
        response = self.client.get("/api/admin/activity-summary?period=weekly")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["period"], "weekly")
        self.assertIn("widgets", data)
        self.assertEqual(data["widgets"][0]["label"], "Meetings")

    def test_activity_summary_page_and_dashboard_widgets_render(self):
        self.seed_activity()
        self.login_admin()

        page = self.client.get("/activity-summary?period=weekly").get_data(as_text=True)
        dashboard = self.client.get("/dashboard").get_data(as_text=True)

        self.assertIn("Summary Report", page)
        self.assertIn("Module Breakdown", page)
        self.assertIn("Recent Activities", page)
        self.assertIn('aria-label="Activity summary"', dashboard)
        self.assertIn("Voting Events", dashboard)


if __name__ == "__main__":
    unittest.main()
