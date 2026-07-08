import os
import tempfile
import unittest

import database
import main


class SystemTestingWorkflowTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_NAME = self.db_path
        database.init_db()
        database.create_user("tester", "tester@example.com", "Password1")
        self.tester = database.get_user_by_email("tester@example.com")
        database.mark_user_verified(self.tester["id"])
        main.app.config.update(TESTING=True)
        self.client = main.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def login_member(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = self.tester["id"]

    def login_admin(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_username"] = "jira"

    def test_defect_documentation_and_fix_verification_workflow(self):
        bug_id = database.create_bug_report(
            "Export button fails",
            "High",
            "Open Finance and click Export CSV",
            "CSV downloads",
            "500 error",
            "tester",
        )

        database.update_bug_status(bug_id, "Fixed", "CSV route repaired")
        database.update_bug_status(bug_id, "Verified", "Regression test passed")
        bug = database.list_bug_reports()[0]

        self.assertEqual(bug["status"], "Verified")
        self.assertEqual(bug["resolution_notes"], "Regression test passed")

    def test_defect_validation_rejects_invalid_statuses_and_severities(self):
        with self.assertRaisesRegex(ValueError, "severity"):
            database.create_bug_report("Bad", "Urgent", "Steps", "Expected", "Actual", "tester")

        bug_id = database.create_bug_report("Bad status", "Medium", "Steps", "Expected", "Actual", "tester")
        with self.assertRaisesRegex(ValueError, "bug status"):
            database.update_bug_status(bug_id, "Closed")

    def test_bug_tracker_routes_document_defects_and_restrict_verification(self):
        self.login_member()
        create_response = self.client.post(
            "/bugs",
            data={
                "action": "create",
                "title": "Login message typo",
                "severity": "Low",
                "steps": "Open Login",
                "expected": "Clear message",
                "actual": "Typo",
            },
            follow_redirects=False,
        )
        self.assertEqual(create_response.status_code, 200)
        bug = database.list_bug_reports()[0]
        self.assertEqual(bug["reporter"], "tester")

        member_update = self.client.post(
            "/bugs",
            data={"action": "status", "bug_id": bug["id"], "status": "Verified", "resolution_notes": "Checked"},
        )
        self.assertEqual(member_update.status_code, 403)

        self.login_admin()
        admin_update = self.client.post(
            "/bugs",
            data={"action": "status", "bug_id": bug["id"], "status": "Verified", "resolution_notes": "Checked"},
        )
        self.assertEqual(admin_update.status_code, 200)
        self.assertEqual(database.list_bug_reports()[0]["status"], "Verified")


if __name__ == "__main__":
    unittest.main()
