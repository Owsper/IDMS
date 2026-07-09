import io
import os
import tempfile
import unittest

import database
import main


class SubmitGameTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_NAME = self.db_path
        database.init_db()
        database.create_user("solo", "solo@example.com", "StrongPass1")
        database.create_user("artist", "artist@example.com", "StrongPass1")
        database.create_user("outsider", "outsider@example.com", "StrongPass1")
        self.solo = database.get_user_by_email("solo@example.com")
        self.artist = database.get_user_by_email("artist@example.com")
        self.outsider = database.get_user_by_email("outsider@example.com")
        database.mark_user_verified(self.solo["id"])
        database.mark_user_verified(self.artist["id"])
        database.mark_user_verified(self.outsider["id"])
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users_data SET full_name = 'Solo Dev' WHERE id = ?", (self.solo["id"],))
        cursor.execute("UPDATE users_data SET full_name = 'Pixel Artist', skills = 'pixel art' WHERE id = ?", (self.artist["id"],))
        cursor.execute("UPDATE users_data SET full_name = 'Outside Member', skills = 'music' WHERE id = ?", (self.outsider["id"],))
        conn.commit()
        conn.close()
        self.team_id = database.create_team(self.solo["id"], "Submit Squad", "Jam team")
        database.join_team(self.team_id, self.artist["id"])
        main.app.config["TESTING"] = True
        self.previous_submission_folder = main.app.config["GAME_SUBMISSIONS_FOLDER"]
        self.submission_dir = tempfile.TemporaryDirectory()
        main.app.config["GAME_SUBMISSIONS_FOLDER"] = self.submission_dir.name
        self.client = main.app.test_client()

    def tearDown(self):
        main.app.config["GAME_SUBMISSIONS_FOLDER"] = self.previous_submission_folder
        self.submission_dir.cleanup()
        os.remove(self.db_path)

    def login(self, user_id):
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = user_id

    def test_dashboard_links_to_submit_game_page(self):
        self.login(self.solo["id"])

        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'href="/submit-game"', response.data)

    def test_game_submission_limit_is_10gb(self):
        self.assertEqual(main.app.config["GAME_SUBMISSION_MAX_SIZE"], 10 * 1024 * 1024 * 1024)
        self.assertEqual(main.app.config["MAX_CONTENT_LENGTH"], main.app.config["GAME_SUBMISSION_MAX_SIZE"])
        self.assertGreater(main.app.config["GAME_SUBMISSION_MAX_SIZE"], main.app.config["PER_FILE_MAX_SIZE"])

    def test_individual_submission_stores_submitter_as_individual_contributor(self):
        self.login(self.solo["id"])

        response = self.client.post(
            "/submit-game",
            data={
                "submission_type": "individual",
                "title": "Solo Runner",
                "description": "A tiny solo game.",
                "game_files": (io.BytesIO(b"solo build"), "solo.zip"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Game submitted successfully.", response.data)
        submissions = database.list_user_submissions(self.solo["id"])
        self.assertEqual(len(submissions), 1)
        self.assertEqual(submissions[0]["submission_type"], "individual")
        self.assertEqual(submissions[0]["contributor_names"], "Solo Dev")
        self.assertEqual(submissions[0]["file_count"], 1)
        self.assertEqual(database.get_dashboard_stats(self.solo["id"])["games_submitted"], 1)

    def test_team_submission_searches_team_members_and_stores_contributor_names(self):
        self.login(self.solo["id"])

        search_response = self.client.get(
            f"/api/submissions/contributor-search?team_id={self.team_id}&q=pixel"
        )
        self.assertEqual(search_response.status_code, 200)
        members = search_response.get_json()["members"]
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["email"], "artist@example.com")

        outsider_search = self.client.get(
            f"/api/submissions/contributor-search?team_id={self.team_id}&q=outside"
        )
        self.assertEqual(outsider_search.get_json()["members"], [])

        response = self.client.post(
            "/submit-game",
            data={
                "submission_type": "team",
                "team_id": str(self.team_id),
                "contributor_ids": f"{self.solo['id']},{self.artist['id']}",
                "title": "Team Quest",
                "description": "Built together.",
                "game_files": (io.BytesIO(b"team build"), "team.zip"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Game submitted successfully.", response.data)
        submissions = database.list_user_submissions(self.solo["id"])
        team_submission = next(item for item in submissions if item["title"] == "Team Quest")
        self.assertEqual(team_submission["submission_type"], "team")
        self.assertEqual(team_submission["team_name"], "Submit Squad")
        self.assertIn("Solo Dev", team_submission["contributor_names"])
        self.assertIn("Pixel Artist", team_submission["contributor_names"])
        self.assertEqual(team_submission["file_count"], 1)
        self.assertEqual(database.get_dashboard_stats(self.artist["id"])["games_submitted"], 1)


if __name__ == "__main__":
    unittest.main()
