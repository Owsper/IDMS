import os
import tempfile
import unittest

import database
import main


class UserDocumentationTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_NAME = self.db_path
        database.init_db()
        database.create_user("reader", "reader@example.com", "Password1")
        self.reader = database.get_user_by_email("reader@example.com")
        database.mark_user_verified(self.reader["id"])
        main.app.config.update(TESTING=True)
        self.client = main.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def login_member(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = self.reader["id"]

    def test_help_page_links_to_published_manual_and_feature_reference(self):
        self.login_member()

        response = self.client.get("/help")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Open Manual", body)
        self.assertIn("Feature Reference", body)
        self.assertIn("documentation/user_manual.md", body)

    def test_user_manual_page_documents_core_workflows(self):
        self.login_member()

        response = self.client.get("/user-manual")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Getting Started", body)
        self.assertIn("Finance", body)
        self.assertIn("Activity Summary", body)
        self.assertIn("Bug Tracking", body)

    def test_documentation_artifacts_are_published(self):
        manual_path = os.path.join("documentation", "user_manual.md")
        screenshots_path = os.path.join("documentation", "screenshots.md")

        self.assertTrue(os.path.exists(manual_path))
        self.assertTrue(os.path.exists(screenshots_path))

        with open(manual_path, encoding="utf-8") as handle:
            manual = handle.read()
        with open(screenshots_path, encoding="utf-8") as handle:
            screenshots = handle.read()

        self.assertIn("IDMS User Manual", manual)
        self.assertIn("Bug Tracking", manual)
        self.assertIn("Screenshot Index", screenshots)
        self.assertIn("10-bug-tracking.png", screenshots)


if __name__ == "__main__":
    unittest.main()
