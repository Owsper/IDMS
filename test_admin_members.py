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
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE users_data
               SET full_name = 'Alice Developer', role = 'Participant',
                   team_role = 'Developer', is_verified = 1
               WHERE email = 'alice@example.com'"""
        )
        cursor.execute(
            """UPDATE users_data
               SET full_name = 'Bob Designer', role = 'Mentor',
                   team_role = 'Designer', is_verified = 0
               WHERE email = 'bob@example.com'"""
        )
        # Imported member records are merged into the same users_data table.
        cursor.execute(
            """INSERT INTO users_data
               (username, email, password_hash, full_name, role, team_role, is_verified)
               VALUES ('imported-lead', 'imported@example.com', 'imported-hash',
                       'Imported Lead', 'Mentor', 'Lead', 1)"""
        )
        conn.commit()
        conn.close()
        main.app.config["TESTING"] = True
        self.client = main.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def login_admin(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_username"] = "jira"

    def test_members_page_requires_admin(self):
        response = self.client.get("/admin/members")
        self.assertEqual(response.status_code, 302)

        with self.client.session_transaction() as session:
            session["user_id"] = database.get_user_by_email("alice@example.com")["id"]
        self.assertEqual(self.client.get("/admin/members").status_code, 403)

    def test_admin_can_search_members(self):
        self.login_admin()
        response = self.client.get("/admin/members?q=alice")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"alice@example.com", response.data)
        self.assertNotIn(b"bob@example.com", response.data)

    def test_admin_can_search_member_by_id(self):
        self.login_admin()
        member_id = database.get_user_by_email("imported@example.com")["id"]
        response = self.client.get(f"/admin/members?q={member_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"imported@example.com", response.data)
        self.assertNotIn(b"alice@example.com", response.data)

    def test_search_api_filters_imported_members(self):
        self.login_admin()
        response = self.client.get(
            "/api/admin/members?role=Mentor&team_role=Lead&verified=verified"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["members"][0]["email"], "imported@example.com")

    def test_search_api_is_paginated_and_admin_only(self):
        self.assertEqual(self.client.get("/api/admin/members").status_code, 302)
        self.login_admin()
        response = self.client.get("/api/admin/members?per_page=1&page=2")
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload["members"]), 1)
        self.assertEqual(payload["pagination"]["total"], 3)
        self.assertEqual(payload["pagination"]["pages"], 3)


if __name__ == "__main__":
    unittest.main()
