import os
import tempfile
import unittest
from datetime import datetime, timedelta

import database
import main


class VotingResultsTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_NAME = self.db_path
        database.init_db()
        main.app.config.update(TESTING=True)
        self.client = main.app.test_client()
        self.now = datetime.utcnow().replace(microsecond=0)

    def tearDown(self):
        os.remove(self.db_path)

    def login_admin(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_username"] = "jira"

    def login_member(self, user_id):
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = user_id

    def create_member(self, username, email):
        database.create_user(username, email, "Password1")
        user = database.get_user_by_email(email)
        database.mark_user_verified(user["id"])
        return database.get_user_by_email(email)

    def create_active_event(self):
        event_id = database.create_voting_event(
            "Council Election",
            "Choose representatives",
            ["Ada", "Grace", "Linus"],
            self.now + timedelta(minutes=5),
            self.now + timedelta(days=1),
            "jira",
            {"membership_status": "verified"},
        )
        conn = database.get_connection()
        conn.execute(
            "UPDATE voting_events SET start_at = ? WHERE id = ?",
            ((self.now - timedelta(minutes=5)).isoformat(timespec="seconds"), event_id),
        )
        options = conn.execute(
            "SELECT id, label FROM voting_options WHERE event_id = ? ORDER BY position",
            (event_id,),
        ).fetchall()
        conn.commit()
        conn.close()
        return event_id, {row["label"]: row["id"] for row in options}

    def test_results_calculate_totals_percentages_and_winner(self):
        event_id, options = self.create_active_event()
        alice = self.create_member("alice", "alice@example.com")
        bob = self.create_member("bob", "bob@example.com")
        cara = self.create_member("cara", "cara@example.com")

        database.cast_vote(event_id, options["Ada"], alice["id"], "secret")
        database.cast_vote(event_id, options["Ada"], bob["id"], "secret")
        database.cast_vote(event_id, options["Grace"], cara["id"], "secret")

        results = database.get_voting_results(event_id)

        self.assertEqual(results["total_votes"], 3)
        self.assertEqual(results["winner_labels"], ["Ada"])
        self.assertFalse(results["is_tie"])
        by_label = {option["label"]: option for option in results["options"]}
        self.assertEqual(by_label["Ada"]["votes"], 2)
        self.assertEqual(by_label["Ada"]["percentage"], 66.67)
        self.assertTrue(by_label["Ada"]["winner"])
        self.assertEqual(by_label["Linus"]["percentage"], 0)

    def test_results_api_and_csv_are_admin_only(self):
        event_id, options = self.create_active_event()
        member = self.create_member("member", "member@example.com")
        database.cast_vote(event_id, options["Grace"], member["id"], "secret")

        self.login_member(member["id"])
        self.assertEqual(self.client.get(f"/api/voting/events/{event_id}/results").status_code, 403)
        self.assertEqual(self.client.get(f"/api/voting/events/{event_id}/results.csv").status_code, 403)

        self.login_admin()
        response = self.client.get(f"/api/voting/events/{event_id}/results")
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["total_votes"], 1)
        self.assertEqual(payload["winner_labels"], ["Grace"])

        csv_response = self.client.get(f"/api/voting/events/{event_id}/results.csv")
        self.assertEqual(csv_response.status_code, 200)
        body = csv_response.data.decode("utf-8")
        self.assertIn("event_id,event_title,option_id,option_label,votes,percentage,winner,total_votes,is_tie", body)
        self.assertIn("Council Election", body)
        self.assertIn("Grace,1,100.0,yes,1,no", body)

    def test_tied_results_mark_every_leader(self):
        event_id, options = self.create_active_event()
        alice = self.create_member("alice", "alice@example.com")
        bob = self.create_member("bob", "bob@example.com")

        database.cast_vote(event_id, options["Ada"], alice["id"], "secret")
        database.cast_vote(event_id, options["Grace"], bob["id"], "secret")

        results = database.get_voting_results(event_id)

        self.assertEqual(results["winner_labels"], ["Ada", "Grace"])
        self.assertTrue(results["is_tie"])
        winners = [option["label"] for option in results["options"] if option["winner"]]
        self.assertEqual(winners, ["Ada", "Grace"])


if __name__ == "__main__":
    unittest.main()
