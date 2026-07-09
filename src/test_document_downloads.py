import os
import tempfile
import unittest

import database
import main


class DocumentDownloadTest(unittest.TestCase):
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

    def create_document(self, original_name, stored_name, content=b"document", approved=True):
        if content is not None:
            path = os.path.join(self.upload_dir.name, stored_name)
            with open(path, "wb") as handle:
                handle.write(content)
        database.save_upload_metadata(
            user_id=self.member["id"],
            original_filename=original_name,
            stored_filename=stored_name,
            mime_type="text/plain",
            size=len(content or b""),
            sha256="test-hash",
            approved=int(approved),
            approved_by="jira" if approved else None,
        )
        conn = database.get_connection()
        row = conn.execute(
            "SELECT * FROM uploads WHERE stored_filename = ?", (stored_name,)
        ).fetchone()
        conn.close()
        return dict(row)

    def download_logs(self):
        conn = database.get_connection()
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM document_downloads ORDER BY id"
        ).fetchall()]
        conn.close()
        return rows

    def test_approved_document_downloads_with_original_filename_and_audit_log(self):
        document = self.create_document("member guide.txt", "stored-guide.txt", b"hello member")
        self.login_member()

        response = self.client.get(
            f"/files/{document['id']}/download",
            headers={"User-Agent": "IDMS-download-test"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"hello member")
        self.assertEqual(response.mimetype, "text/plain")
        self.assertIn("member guide.txt", response.headers["Content-Disposition"])
        logs = self.download_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["upload_id"], document["id"])
        self.assertEqual(logs[0]["user_id"], self.member["id"])
        self.assertIsNone(logs[0]["admin_username"])
        self.assertEqual(logs[0]["ip_address"], "127.0.0.1")
        self.assertEqual(logs[0]["user_agent"], "IDMS-download-test")
        self.assertIsNotNone(logs[0]["downloaded_at"])
        response.close()

    def test_download_requires_authentication(self):
        document = self.create_document("guide.txt", "stored.txt")

        response = self.client.get(f"/files/{document['id']}/download")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.download_logs(), [])
        response.close()

    def test_unapproved_and_missing_documents_are_not_downloaded_or_logged(self):
        pending = self.create_document("pending.txt", "pending.txt", approved=False)
        missing = self.create_document("missing.txt", "missing.txt", content=None, approved=True)
        self.login_member()

        pending_response = self.client.get(f"/files/{pending['id']}/download")
        missing_response = self.client.get(f"/files/{missing['id']}/download")

        self.assertEqual(pending_response.status_code, 404)
        self.assertEqual(missing_response.status_code, 404)
        self.assertEqual(self.download_logs(), [])
        pending_response.close()
        missing_response.close()

    def test_documents_page_lists_only_approved_files(self):
        self.create_document("approved.txt", "approved.txt", approved=True)
        self.create_document("pending.txt", "pending.txt", approved=False)
        self.login_member()

        response = self.client.get("/files")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"approved.txt", response.data)
        self.assertNotIn(b"pending.txt", response.data)
        response.close()

    def test_range_request_returns_partial_content_and_is_logged(self):
        document = self.create_document("large.txt", "large.txt", b"0123456789")
        self.login_member()

        response = self.client.get(
            f"/files/{document['id']}/download",
            headers={"Range": "bytes=2-5"},
        )

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.data, b"2345")
        self.assertEqual(response.headers["Content-Range"], "bytes 2-5/10")
        self.assertEqual(len(self.download_logs()), 1)
        response.close()

    def test_conditional_and_head_requests_reuse_file_without_extra_download_logs(self):
        document = self.create_document("cached.txt", "cached.txt", b"cache me")
        self.login_member()

        first = self.client.get(f"/files/{document['id']}/download")
        etag = first.headers["ETag"]

        self.assertEqual(first.status_code, 200)
        self.assertIn("private", first.headers["Cache-Control"])
        self.assertIn("max-age=3600", first.headers["Cache-Control"])
        self.assertIn("Cookie", first.headers["Vary"])
        first.close()

        cached = self.client.get(
            f"/files/{document['id']}/download",
            headers={"If-None-Match": etag},
        )
        head = self.client.head(f"/files/{document['id']}/download")

        self.assertEqual(cached.status_code, 304)
        self.assertEqual(cached.data, b"")
        self.assertEqual(head.status_code, 200)
        self.assertEqual(head.data, b"")
        self.assertEqual(len(self.download_logs()), 1)
        cached.close()
        head.close()


if __name__ == "__main__":
    unittest.main()
