import io
import os
import tempfile
import unittest

import database
import main


class DocumentCategorizationTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.upload_dir = tempfile.TemporaryDirectory()
        self.original_upload_folder = main.app.config["UPLOAD_FOLDER"]
        database.DB_NAME = self.db_path
        database.init_db()
        database.create_user("member", "member@example.com", "Password1")
        self.member = database.get_user_by_email("member@example.com")
        main.app.config.update(TESTING=True, UPLOAD_FOLDER=self.upload_dir.name)
        self.client = main.app.test_client()

    def tearDown(self):
        main.app.config["UPLOAD_FOLDER"] = self.original_upload_folder
        self.upload_dir.cleanup()
        os.remove(self.db_path)

    def login_member(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = self.member["id"]

    def login_admin(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_username"] = "jira"

    def create_document(self, title="Document.pdf", category="General", approved=True):
        stored_name = f"stored-{title.lower().replace(' ', '-')}"
        database.save_upload_metadata(
            user_id=self.member["id"],
            original_filename=title,
            stored_filename=stored_name,
            mime_type="application/pdf",
            size=100,
            sha256=f"hash-{stored_name}",
            approved=int(approved),
            approved_by="jira" if approved else None,
            category=category,
        )
        conn = database.get_connection()
        document = dict(conn.execute(
            "SELECT * FROM uploads WHERE stored_filename = ?", (stored_name,)
        ).fetchone())
        conn.close()
        return document

    def category(self, name):
        return next(
            category for category in database.get_document_categories(include_inactive=True)
            if category["name"] == name
        )

    def test_database_seeds_categories_and_links_uploads_by_category_id(self):
        categories = database.get_document_categories(include_inactive=True)
        expected_names = [name for name, _ in database.DEFAULT_DOCUMENT_CATEGORIES]

        self.assertEqual({category["name"] for category in categories}, set(expected_names))
        self.assertTrue(all(category["is_active"] for category in categories))
        self.assertTrue(all(category["is_system"] for category in categories))

        document = self.create_document(category="Reports")
        self.assertEqual(document["category_id"], self.category("Reports")["id"])
        self.assertEqual(document["category"], "Reports")

    def test_management_page_is_admin_only_and_supports_custom_category_crud(self):
        self.assertEqual(self.client.get("/admin/document-categories").status_code, 302)
        self.login_member()
        self.assertEqual(self.client.get("/admin/document-categories").status_code, 403)
        self.login_admin()

        created = self.client.post("/admin/document-categories", data={
            "action": "create",
            "name": "Training",
            "description": "Training resources",
        })
        duplicate = self.client.post("/admin/document-categories", data={
            "action": "create",
            "name": "training",
            "description": "Duplicate",
        })
        training = self.category("Training")
        updated = self.client.post("/admin/document-categories", data={
            "action": "update",
            "category_id": training["id"],
            "name": "Learning",
            "description": "Learning resources",
            "is_active": "1",
        })
        learning = self.category("Learning")
        deactivated = self.client.post("/admin/document-categories", data={
            "action": "update",
            "category_id": learning["id"],
            "name": "Learning",
            "description": "Learning resources",
        })

        self.assertIn(b"Created category Training", created.data)
        self.assertIn(b"already exists", duplicate.data)
        self.assertIn(b"Updated category Learning", updated.data)
        self.assertIn(b"Updated category Learning", deactivated.data)
        self.assertFalse(self.category("Learning")["is_active"])
        self.assertNotIn("Learning", main.active_document_category_names())
        created.close()
        duplicate.close()
        updated.close()
        deactivated.close()

    def test_category_safety_rules_protect_system_and_in_use_categories(self):
        general = self.category("General")
        policies = self.category("Policies")
        custom_id = database.create_document_category("Training", "Training resources")
        self.create_document(category="Training")

        with self.assertRaisesRegex(ValueError, "must remain active"):
            database.update_document_category(general["id"], "General", "", False)
        with self.assertRaisesRegex(ValueError, "Built-in category names"):
            database.update_document_category(policies["id"], "Rules", "", True)
        with self.assertRaisesRegex(ValueError, "must remain active"):
            database.update_document_category(custom_id, "Training", "", False)

    def test_admin_can_assign_existing_document_to_an_active_category(self):
        document = self.create_document("Existing Guide.pdf", "General", approved=False)
        training_id = database.create_document_category("Training", "Training resources")
        inactive_id = database.create_document_category("Archive", "Old resources")
        database.update_document_category(inactive_id, "Archive", "Old resources", False)
        self.login_admin()

        response = self.client.post("/admin/document-categories", data={
            "action": "assign",
            "upload_id": document["id"],
            "category_id": training_id,
        })
        updated = database.get_upload_by_id(document["id"])

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Assigned Existing Guide.pdf to Training", response.data)
        self.assertEqual(updated["category_id"], training_id)
        self.assertEqual(updated["category"], "Training")
        with self.assertRaisesRegex(ValueError, "active document category"):
            database.assign_document_category(document["id"], inactive_id)
        response.close()

    def test_custom_category_flows_from_upload_to_case_insensitive_search_filter(self):
        database.create_document_category("Training", "Training resources")
        self.login_admin()

        upload = self.client.post(
            "/import-files",
            data={
                "category": "Training",
                "files": (io.BytesIO(b"training guide"), "Training Guide.txt"),
            },
            content_type="multipart/form-data",
        )
        search = self.client.get("/api/documents?q=train&category=training")
        payload = search.get_json()
        document = database.get_approved_uploads()[0]

        self.assertEqual(upload.status_code, 200)
        self.assertIn(b"Uploaded and approved 1 files", upload.data)
        self.assertEqual(document["category"], "Training")
        self.assertEqual(payload["category"], "Training")
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["documents"][0]["category"], "Training")
        upload.close()
        search.close()


if __name__ == "__main__":
    unittest.main()
