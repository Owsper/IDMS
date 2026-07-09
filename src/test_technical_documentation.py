import os
import tempfile
import unittest

import database
import main


class TechnicalDocumentationTest(unittest.TestCase):
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

    def test_developer_guide_requires_admin_and_documents_architecture(self):
        self.assertEqual(self.client.get("/developer-guide").status_code, 302)

        self.login_admin()
        response = self.client.get("/developer-guide")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Published Technical Documentation", body)
        self.assertIn("Architecture", body)
        self.assertIn("Database Schema", body)
        self.assertIn("Maintenance Checklist", body)

    def test_technical_documentation_artifact_covers_schema_and_apis(self):
        path = os.path.join("documentation", "technical_documentation.md")

        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as handle:
            content = handle.read()

        self.assertIn("IDMS Technical Documentation", content)
        self.assertIn("Database Schema", content)
        self.assertIn("API Endpoints", content)
        self.assertIn("financial_transactions", content)
        self.assertIn("/api/financial/report", content)
        self.assertIn("Maintenance Checklist", content)


if __name__ == "__main__":
    unittest.main()
