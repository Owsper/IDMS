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
            priority="Critical",
            module="Finance",
            environment="Test",
            build_version="2026.07",
            reproducibility="Always",
            assigned_to="dev1",
        )

        database.update_bug_status(bug_id, "Fixed", "CSV route repaired", fix_notes="Added report export rows")
        database.update_bug_status(bug_id, "Verified", "Regression test passed", verified_by="jira")
        bug = database.list_bug_reports()[0]

        self.assertEqual(bug["status"], "Verified")
        self.assertEqual(bug["priority"], "Critical")
        self.assertEqual(bug["module"], "Finance")
        self.assertEqual(bug["assigned_to"], "dev1")
        self.assertEqual(bug["verified_by"], "jira")
        self.assertEqual(bug["resolution_notes"], "Regression test passed")

    def test_defect_validation_rejects_invalid_statuses_and_severities(self):
        with self.assertRaisesRegex(ValueError, "severity"):
            database.create_bug_report("Bad", "Urgent", "Steps", "Expected", "Actual", "tester")

        bug_id = database.create_bug_report("Bad status", "Medium", "Steps", "Expected", "Actual", "tester")
        with self.assertRaisesRegex(ValueError, "bug status"):
            database.update_bug_status(bug_id, "Closed")
        with self.assertRaisesRegex(ValueError, "Fix notes"):
            database.update_bug_status(bug_id, "Fixed")
        with self.assertRaisesRegex(ValueError, "Verification notes"):
            database.update_bug_status(bug_id, "Verified")

    def test_bug_tracker_routes_document_defects_and_restrict_verification(self):
        self.login_member()
        create_response = self.client.post(
            "/bugs",
            data={
                "action": "create",
                "title": "Login message typo",
                "severity": "Low",
                "priority": "Low",
                "module": "Authentication",
                "environment": "Local",
                "build_version": "2026.07",
                "reproducibility": "Sometimes",
                "assigned_to": "dev2",
                "steps": "Open Login",
                "expected": "Clear message",
                "actual": "Typo",
            },
            follow_redirects=False,
        )
        self.assertEqual(create_response.status_code, 200)
        bug = database.list_bug_reports()[0]
        self.assertEqual(bug["reporter"], "tester")
        self.assertEqual(bug["module"], "Authentication")
        self.assertEqual(bug["assigned_to"], "dev2")

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

    def test_bug_tracker_summary_counts_priority_and_resolution_states(self):
        database.create_bug_report("Critical open", "Critical", "Steps", "Expected", "Actual", "tester", priority="Critical")
        fixed_id = database.create_bug_report("High fixed", "High", "Steps", "Expected", "Actual", "tester", priority="High")
        database.update_bug_status(fixed_id, "Fixed", "Patched", fix_notes="Code changed")

        summary = database.bug_tracker_summary()

        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["open"], 1)
        self.assertEqual(summary["fixed"], 1)
        self.assertEqual(summary["critical_priority"], 1)
        self.assertEqual(summary["high_priority"], 1)


if __name__ == "__main__":
    unittest.main()
