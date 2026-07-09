import io
import os
import tempfile
import unittest

import database
import main


class MemberImportTest(unittest.TestCase):
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

    def login_member(self):
        database.create_user("member", "member@example.com", "Password1")
        user = database.get_user_by_email("member@example.com")
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = user["id"]

    def upload_csv(self, csv_text):
        return self.client.post(
            "/admin/import-members",
            data={"file": (io.BytesIO(csv_text.encode("utf-8")), "members.csv")},
            content_type="multipart/form-data",
        )

    def test_admin_can_preview_and_confirm_member_import(self):
        database.create_user("existing", "existing@example.com", "Password1")
        self.login_admin()
        response = self.upload_csv(
            "first_name,last_name,username,email,phone,role,member_type,team_name\n"
            " Alice , Stone ,alice,ALICE@example.com,(555) 010-1000,Participant,Developer,Blue Team\n"
            "Missing,Email,missing,,555,Participant,Tester,QA\n"
            "Bad,Email,bad,not-an-email,555,Participant,Tester,QA\n"
            "Alice,Dupe,dupe,alice@example.com,555,Participant,Tester,QA\n"
            "Existing,User,existing,existing@example.com,555,Participant,Tester,QA\n"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"CSV processed", response.data)
        self.assertIn(b"alice@example.com", response.data)
        self.assertIn(b"Missing email", response.data)
        self.assertIn(b"Invalid email format", response.data)
        self.assertIn(b"Duplicate email in file", response.data)
        self.assertIn(b"Email already exists", response.data)

        batches = database.list_member_import_batches()
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]["total_rows"], 5)
        self.assertEqual(batches[0]["valid_rows"], 1)
        self.assertEqual(batches[0]["duplicate_rows"], 1)
        self.assertEqual(batches[0]["existing_rows"], 1)
        self.assertEqual(batches[0]["error_rows"], 4)

        confirm = self.client.post(f"/admin/import-members/{batches[0]['id']}/confirm")
        self.assertEqual(confirm.status_code, 302)
        imported = database.get_user_by_email("alice@example.com")
        self.assertIsNotNone(imported)
        self.assertEqual(imported["full_name"], "Alice Stone")
        self.assertEqual(imported["team_role"], "Developer")
        self.assertEqual(imported["role"], "Participant")
        self.assertNotIn("TempPass", imported["password_hash"])

    def test_member_import_requires_admin(self):
        response = self.client.get("/admin/import-members")
        self.assertEqual(response.status_code, 302)

        self.login_member()
        response = self.upload_csv(
            "first_name,last_name,email\n"
            "Alice,Stone,alice@example.com\n"
        )
        self.assertEqual(response.status_code, 403)

    def test_import_members_rejects_non_csv_upload(self):
        self.login_admin()
        response = self.client.post(
            "/admin/import-members",
            data={"file": (io.BytesIO(b"not csv"), "members.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"CSV files only", response.data)


if __name__ == "__main__":
    unittest.main()
