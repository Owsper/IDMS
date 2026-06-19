import os
import tempfile
import unittest

import database
import main


class DocumentSearchTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_NAME = self.db_path
        database.init_db()
        database.create_user("searcher", "searcher@example.com", "Password1")
        self.member = database.get_user_by_email("searcher@example.com")
        main.app.config["TESTING"] = True
        self.client = main.app.test_client()

    def tearDown(self):
        os.remove(self.db_path)

    def login_member(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = self.member["id"]

    def create_document(self, title, category="General", approved=True):
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
        row = conn.execute(
            "SELECT * FROM uploads WHERE stored_filename = ?", (stored_name,)
        ).fetchone()
        conn.close()
        return dict(row)

    def test_search_page_requires_login_and_shows_approved_documents_and_filters(self):
        self.create_document("Member Guide.pdf", "Guides")
        self.create_document("Hidden Report.pdf", "Reports", approved=False)

        self.assertEqual(self.client.get("/files").status_code, 302)
        self.login_member()
        response = self.client.get("/files")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Search Documents", response.data)
        self.assertIn(b'id="documentSearch"', response.data)
        self.assertIn(b'id="categoryFilter"', response.data)
        self.assertIn(b"Member Guide.pdf", response.data)
        self.assertIn(b"Guides", response.data)
        self.assertNotIn(b"Hidden Report.pdf", response.data)
        response.close()

    def test_api_searches_approved_titles_case_insensitively_and_paginates(self):
        guide = self.create_document("Member Guide.pdf", "Guides")
        policy = self.create_document("Member Policy.pdf", "Policies")
        self.create_document("Hidden Member Notes.pdf", "General", approved=False)
        self.login_member()

        first = self.client.get("/api/documents?q=MEM&page=1&per_page=1")
        second = self.client.get("/api/documents?q=MEM&page=2&per_page=1")
        guide_only = self.client.get("/api/documents?q=guid")

        first_payload = first.get_json()
        second_payload = second.get_json()
        guide_payload = guide_only.get_json()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first_payload["pagination"], {
            "page": 1, "per_page": 1, "total": 2, "pages": 2
        })
        self.assertEqual(second_payload["pagination"]["total"], 2)
        result_ids = {
            first_payload["documents"][0]["id"],
            second_payload["documents"][0]["id"],
        }
        self.assertEqual(result_ids, {guide["id"], policy["id"]})
        self.assertEqual(guide_payload["pagination"]["total"], 1)
        self.assertEqual(guide_payload["documents"][0]["title"], "Member Guide.pdf")
        self.assertNotIn("stored_filename", guide_payload["documents"][0])
        self.assertEqual(
            guide_payload["documents"][0]["download_url"],
            f"/files/{guide['id']}/download",
        )
        first.close()
        second.close()
        guide_only.close()

    def test_api_combines_title_and_category_filters(self):
        self.create_document("Member Guide.pdf", "Guides")
        policy = self.create_document("Member Policy.pdf", "Policies")
        self.create_document("Annual Policy.pdf", "Policies")
        self.login_member()

        response = self.client.get("/api/documents?q=member&category=Policies")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["query"], "member")
        self.assertEqual(payload["category"], "Policies")
        self.assertEqual(payload["categories"], list(main.DOCUMENT_CATEGORIES))
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["documents"][0]["id"], policy["id"])
        response.close()

    def test_api_rejects_unauthorized_and_invalid_search_requests(self):
        self.assertEqual(self.client.get("/api/documents?q=guide").status_code, 302)
        self.login_member()

        invalid_category = self.client.get("/api/documents?category=Unknown")
        invalid_page = self.client.get("/api/documents?page=not-a-number")
        long_query = self.client.get(f"/api/documents?q={'x' * 151}")

        self.assertEqual(invalid_category.status_code, 400)
        self.assertEqual(invalid_page.status_code, 400)
        self.assertEqual(long_query.status_code, 400)
        invalid_category.close()
        invalid_page.close()
        long_query.close()

    def test_full_text_index_tracks_title_updates_and_deletes(self):
        document = self.create_document("Old Handbook.pdf", "Guides")
        self.assertEqual(database.search_approved_documents("old")["total"], 1)

        conn = database.get_connection()
        conn.execute(
            "UPDATE uploads SET original_filename = ? WHERE id = ?",
            ("New Handbook.pdf", document["id"]),
        )
        conn.commit()
        conn.close()

        self.assertEqual(database.search_approved_documents("old")["total"], 0)
        self.assertEqual(database.search_approved_documents("new")["total"], 1)

        conn = database.get_connection()
        conn.execute("DELETE FROM uploads WHERE id = ?", (document["id"],))
        conn.commit()
        conn.close()
        self.assertEqual(database.search_approved_documents("new")["total"], 0)


if __name__ == "__main__":
    unittest.main()
