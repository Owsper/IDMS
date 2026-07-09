import csv
import os
import tempfile
import unittest

import database
import main


class ImportValidationTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.import_dir = tempfile.TemporaryDirectory()
        self.original_import_folder = main.app.config["IMPORT_FOLDER"]
        database.DB_NAME = self.db_path
        database.init_db()
        main.app.config.update(TESTING=True, IMPORT_FOLDER=self.import_dir.name)
        self.client = main.app.test_client()

    def tearDown(self):
        main.app.config["IMPORT_FOLDER"] = self.original_import_folder
        self.import_dir.cleanup()
        os.remove(self.db_path)

    def login_admin(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_username"] = "jira"

    def create_csv_job(self, rows):
        stored_filename = f"import-{len(os.listdir(self.import_dir.name))}.csv"
        file_path = os.path.join(self.import_dir.name, stored_filename)
        with open(file_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return database.create_import_job(
            "jira", "members.csv", stored_filename, "users_data", ".csv", os.path.getsize(file_path)
        )

    def validate(self, job_id, mapping=None, duplicate_key="email"):
        return self.client.post(
            "/api/admin/import/validate",
            json={
                "job_id": job_id,
                "mapping": mapping or {
                    "id": "id",
                    "username": "username",
                    "email": "email",
                    "password_hash": "password_hash",
                },
                "duplicate_key": duplicate_key,
            },
        )

    def test_validation_reports_valid_and_invalid_rows_with_field_errors(self):
        self.login_admin()
        job_id = self.create_csv_job([
            {
                "id": "101",
                "username": "valid-user",
                "email": "valid@example.com",
                "password_hash": "hash",
            },
            {
                "id": "not-a-number",
                "username": "",
                "email": "not-an-email",
                "password_hash": "",
            },
        ])

        response = self.validate(job_id)
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["counts"], {
            "total": 2, "valid": 1, "invalid": 1, "duplicate": 0, "conflict": 0
        })
        errors = payload["invalid_rows"][0]["errors"]
        self.assertIn("username is required", errors)
        self.assertIn("password_hash is required", errors)
        self.assertIn("email must be a valid address", errors)
        self.assertIn("id must match INTEGER", errors)

        persisted = database.get_import_rows(job_id)
        self.assertEqual([row["status"] for row in persisted], ["valid", "invalid"])
        self.assertEqual(persisted[1]["errors"], errors)

    def test_validation_distinguishes_duplicates_from_conflicts(self):
        database.create_user("existing", "existing@example.com", "Password1")
        existing = database.get_user_by_email("existing@example.com")
        self.login_admin()
        job_id = self.create_csv_job([
            {
                "username": existing["username"],
                "email": existing["email"],
                "password_hash": existing["password_hash"],
            },
            {
                "username": "changed-name",
                "email": existing["email"],
                "password_hash": "changed-hash",
            },
        ])

        response = self.validate(job_id, mapping={
            "username": "username",
            "email": "email",
            "password_hash": "password_hash",
        })
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["counts"]["duplicate"], 1)
        self.assertEqual(payload["counts"]["conflict"], 1)
        self.assertEqual(
            [row["status"] for row in payload["conflicts"]],
            ["duplicate", "conflict"],
        )

    def test_invalid_row_can_be_corrected_and_revalidated(self):
        self.login_admin()
        job_id = self.create_csv_job([
            {"username": "member", "email": "bad-email", "password_hash": "hash"}
        ])
        validation = self.validate(job_id, mapping={
            "username": "username",
            "email": "email",
            "password_hash": "password_hash",
        }).get_json()
        row_id = validation["invalid_rows"][0]["id"]

        response = self.client.patch(
            f"/api/admin/import/{job_id}/rows/{row_id}",
            json={"mapped_data": {
                "username": "member",
                "email": "member@example.com",
                "password_hash": "hash",
            }},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["row"]["status"], "valid")
        self.assertEqual(payload["row"]["errors"], [])
        self.assertEqual(payload["counts"]["invalid"], 0)
        self.assertEqual(payload["counts"]["valid"], 1)

    def test_validation_endpoint_requires_an_admin(self):
        job_id = self.create_csv_job([
            {"username": "member", "email": "member@example.com", "password_hash": "hash"}
        ])

        response = self.validate(job_id, mapping={
            "username": "username",
            "email": "email",
            "password_hash": "password_hash",
        })

        self.assertEqual(response.status_code, 302)


if __name__ == "__main__":
    unittest.main()
