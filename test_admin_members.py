import os
import tempfile
import unittest

import database
import main


class AdminMembersTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_NAME = self.db_path
        database.init_db()
        database.create_user("alice-dev", "alice@example.com", "password123")
        database.create_user("bob-design", "bob@example.com", "password123")
        main.app.config["TESTING"] = True
        self.client = main.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def test_members_page_requires_admin(self):
        response = self.client.get("/admin/members")
        self.assertEqual(response.status_code, 302)

        with self.client.session_transaction() as session:
            session["user_id"] = database.get_user_by_email("alice@example.com")["id"]
        self.assertEqual(self.client.get("/admin/members").status_code, 403)

    def test_admin_can_search_members(self):
        with self.client.session_transaction() as session:
            session["admin_username"] = "jira"
        response = self.client.get("/admin/members?q=alice")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"alice@example.com", response.data)
        self.assertNotIn(b"bob@example.com", response.data)


if __name__ == "__main__":
    unittest.main()
