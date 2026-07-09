import os
import tempfile
import unittest
from datetime import datetime, timedelta
from io import BytesIO

import database
import main


class MeetingMinutesStorageTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.upload_dir = tempfile.TemporaryDirectory()
        database.DB_NAME = self.db_path
        database.init_db()
        main.app.config.update(
            TESTING=True,
            UPLOAD_FOLDER=self.upload_dir.name,
            MEETING_MINUTES_FOLDER=os.path.join(self.upload_dir.name, "meeting_minutes"),
        )
        os.makedirs(main.app.config["MEETING_MINUTES_FOLDER"], exist_ok=True)
        self.client = main.app.test_client()
        self.now = datetime.utcnow().replace(microsecond=0)
        self.meeting_id = database.create_meeting(
            "Minutes Review",
            "",
            self.now + timedelta(days=2),
            "Room 1",
            "Minutes",
            [],
            "jira",
        )

    def tearDown(self):
        self.upload_dir.cleanup()
        os.remove(self.db_path)

    def login_admin(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_username"] = "jira"

    def login_member(self):
        database.create_user("member", "member@example.com", "Password1")
        member = database.get_user_by_email("member@example.com")
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = member["id"]

    def test_text_minutes_are_linked_to_meeting(self):
        minutes_id = database.add_meeting_minutes(self.meeting_id, "Decisions", "Approved agenda", uploaded_by="jira")

        minutes = database.list_meeting_minutes(meeting_id=self.meeting_id)

        self.assertEqual(minutes[0]["id"], minutes_id)
        self.assertEqual(minutes[0]["meeting_title"], "Minutes Review")
        self.assertEqual(minutes[0]["content"], "Approved agenda")
        self.assertEqual(minutes[0]["stored_filename"], "")

    def test_minutes_upload_page_stores_document_metadata(self):
        self.login_admin()

        response = self.client.post(
            "/meetings",
            data={
                "action": "minutes",
                "meeting_id": str(self.meeting_id),
                "title": "Uploaded Minutes",
                "content": "",
                "minutes_file": (BytesIO(b"meeting notes"), "minutes.txt"),
            },
            content_type="multipart/form-data",
        )
        minutes = database.list_meeting_minutes(meeting_id=self.meeting_id)
        stored_path = os.path.join(main.app.config["MEETING_MINUTES_FOLDER"], minutes[0]["stored_filename"])

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Minutes saved", response.data)
        self.assertEqual(minutes[0]["original_filename"], "minutes.txt")
        self.assertEqual(minutes[0]["size"], len(b"meeting notes"))
        self.assertTrue(os.path.exists(stored_path))

    def test_minutes_api_and_download_retrieve_stored_minutes(self):
        self.login_admin()
        upload = main.save_meeting_minutes_upload(type("Upload", (), {
            "filename": "minutes.txt",
            "mimetype": "text/plain",
            "read": lambda self: b"downloadable minutes",
        })())
        minutes_id = database.add_meeting_minutes(
            self.meeting_id,
            "Downloadable",
            "",
            uploaded_by="jira",
            **upload,
        )

        api_response = self.client.get("/api/meetings/minutes", query_string={"meeting_id": self.meeting_id})
        download_response = self.client.get(f"/meetings/minutes/{minutes_id}/download")

        self.assertEqual(api_response.status_code, 200)
        self.assertEqual(api_response.get_json()["minutes"][0]["title"], "Downloadable")
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response.data, b"downloadable minutes")
        download_response.close()

    def test_non_admin_cannot_upload_minutes(self):
        self.login_member()

        response = self.client.post(
            "/meetings",
            data={
                "action": "minutes",
                "meeting_id": str(self.meeting_id),
                "title": "Nope",
                "content": "Member edit",
            },
        )

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
