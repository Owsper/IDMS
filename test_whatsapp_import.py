import io
import os
import tempfile
import unittest

import database
import main


class WhatsAppImportTest(unittest.TestCase):
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

    def test_parser_handles_supported_formats_multiline_and_media(self):
        export = "\n".join([
            "[12/31/2025, 9:15 PM] Alice: Hello team",
            "this wraps onto another line",
            "31/12/2025, 21:17 - Bob: <Media omitted>",
            "31/12/2025, 21:19 - Bob: image omitted",
            "31/12/2025, 21:20 - Alice: This message was deleted",
            "31/12/2025, 21:21 - Messages and calls are end-to-end encrypted.",
        ])

        messages = main.parse_whatsapp_export(export, "chat.txt")

        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["sender"], "Alice")
        self.assertEqual(messages[0]["sent_at"], "2025-12-31T21:15:00")
        self.assertEqual(messages[0]["message"], "Hello team\nthis wraps onto another line")
        self.assertEqual(messages[0]["media_type"], "text")
        self.assertEqual(messages[1]["media_type"], "media")
        self.assertEqual(messages[2]["media_type"], "image")
        self.assertEqual(messages[2]["source_filename"], "chat.txt")

    def test_store_imported_messages_and_returns_analytics(self):
        messages = main.parse_whatsapp_export(
            "13/02/2026, 08:05 - Alice: Morning\n"
            "13/02/2026, 08:06 - Bob: audio omitted",
            "chat.txt",
        )

        imported = database.store_whatsapp_messages(messages)
        stored = database.list_whatsapp_messages()
        analytics = database.whatsapp_analytics()

        self.assertEqual(imported, 2)
        self.assertEqual([row["sender"] for row in stored], ["Alice", "Bob"])
        self.assertEqual(analytics["per_day"], [{"label": "2026-02-13", "count": 2}])
        self.assertEqual(analytics["media_types"], [
            {"label": "audio", "count": 1},
            {"label": "text", "count": 1},
        ])
        self.assertEqual(analytics["summary"]["total_messages"], 2)
        self.assertEqual(analytics["summary"]["participant_count"], 2)
        self.assertEqual(analytics["summary"]["average_messages_per_participant"], 1.0)
        self.assertEqual(analytics["busiest_day"], {"label": "2026-02-13", "count": 2})
        self.assertEqual(analytics["busiest_hour"], {"label": "08", "count": 2})
        self.assertEqual(analytics["most_active_participant"]["label"], "Alice")
        self.assertEqual(analytics["active_participants"][0]["message_count"], 1)
        self.assertEqual(analytics["active_participants"][0]["average_per_active_day"], 1.0)
        self.assertEqual(len(analytics["recent_messages"]), 2)

    def test_api_import_requires_admin_and_stores_messages(self):
        export = b"01/02/2026, 08:05 - Alice: Morning"

        unauthenticated = self.client.post(
            "/api/whatsapp/import",
            data={"file": (io.BytesIO(export), "chat.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(unauthenticated.status_code, 302)

        self.login_admin()
        response = self.client.post(
            "/api/whatsapp/import",
            data={"file": (io.BytesIO(export), "chat.txt")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["imported"], 1)
        self.assertEqual(database.list_whatsapp_messages()[0]["message"], "Morning")

    def test_api_rejects_non_whatsapp_file(self):
        self.login_admin()

        response = self.client.post(
            "/api/whatsapp/import",
            data={"file": (io.BytesIO(b"sender,message"), "chat.csv")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("must be .txt", response.get_json()["error"])

    def test_analytics_api_requires_admin_and_returns_metrics(self):
        messages = main.parse_whatsapp_export(
            "13/02/2026, 08:05 - Alice: Morning\n"
            "13/02/2026, 09:06 - Alice: Update\n"
            "14/02/2026, 10:07 - Bob: Hello",
            "chat.txt",
        )
        database.store_whatsapp_messages(messages)

        unauthenticated = self.client.get("/api/whatsapp/analytics")
        self.assertEqual(unauthenticated.status_code, 302)

        self.login_admin()
        response = self.client.get("/api/whatsapp/analytics")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["total_messages"], 3)
        self.assertEqual(payload["top_participants"][0]["label"], "Alice")
        self.assertEqual(payload["top_participants"][0]["percentage"], 66.67)
        self.assertEqual(payload["active_participants"][0]["active_days"], 1)
        self.assertTrue(any(row["label"] == "Friday" for row in payload["weekdays"]))


if __name__ == "__main__":
    unittest.main()
