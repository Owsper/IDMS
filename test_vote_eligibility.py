import os
import tempfile
import unittest
from datetime import datetime, timedelta

import database
import main


class VoteEligibilityTest(unittest.TestCase):
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

    def login_member(self, user_id):
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = user_id

    def login_admin(self):
        with self.client.session_transaction() as session:
            session.clear()
            session["admin_username"] = "jira"

    def create_member(self, username, email, verified=True, role="Participant", team_role="Developer"):
        database.create_user(username, email, "Password1")
        user = database.get_user_by_email(email)
        if verified:
            database.mark_user_verified(user["id"])
        conn = database.get_connection()
        conn.execute(
            "UPDATE users_data SET role = ?, team_role = ? WHERE id = ?",
            (role, team_role, user["id"]),
        )
        conn.commit()
        conn.close()
        return database.get_user_by_email(email)

    def create_event(self, eligibility=None, active=True):
        event_id = database.create_voting_event(
            "Eligibility Vote",
            "",
            ["Yes", "No"],
            self.now + timedelta(minutes=5),
            self.now + timedelta(days=1),
            "jira",
            eligibility or {"membership_status": "verified"},
        )
        if active:
            conn = database.get_connection()
            conn.execute(
                "UPDATE voting_events SET start_at = ? WHERE id = ?",
                ((self.now - timedelta(minutes=5)).isoformat(timespec="seconds"), event_id),
            )
            conn.commit()
            conn.close()
        return event_id

    def first_option_id(self, event_id):
        conn = database.get_connection()
        option_id = conn.execute(
            "SELECT id FROM voting_options WHERE event_id = ? ORDER BY position LIMIT 1",
            (event_id,),
        ).fetchone()["id"]
        conn.close()
        return option_id

    def test_eligibility_rules_are_validated_when_event_is_created(self):
        with self.assertRaisesRegex(ValueError, "verified or any"):
            self.create_event({"membership_status": "unknown"})
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            self.create_event({"membership_status": "verified", "min_membership_days": -1})
        with self.assertRaisesRegex(ValueError, "Allowed roles"):
            self.create_event({"allowed_roles": {"role": "Admin"}})

    def test_unverified_member_is_blocked_and_audited(self):
        member = self.create_member("pending", "pending@example.com", verified=False)
        event_id = self.create_event({"membership_status": "verified"})
        option_id = self.first_option_id(event_id)

        with self.assertRaisesRegex(ValueError, "Only verified members"):
            database.cast_vote(event_id, option_id, member["id"], "secret")

        audit = database.get_eligibility_audit(limit=1)[0]
        self.assertEqual(audit["event_id"], event_id)
        self.assertEqual(audit["user_id"], member["id"])
        self.assertEqual(audit["eligible"], 0)
        self.assertIn("Only verified", audit["reason"])

    def test_role_and_membership_age_rules_block_unauthorized_members(self):
        member = self.create_member("member", "member@example.com", role="Participant", team_role="Developer")
        role_event_id = self.create_event({
            "membership_status": "verified",
            "allowed_roles": ["Admin"],
        })
        age_event_id = self.create_event({
            "membership_status": "verified",
            "min_membership_days": 30,
        })

        role_check = database.verify_vote_eligibility(role_event_id, member["id"])
        age_check = database.verify_vote_eligibility(age_event_id, member["id"])

        self.assertFalse(role_check["eligible"])
        self.assertIn("role", role_check["reason"])
        self.assertEqual(role_check["rule"]["allowed_roles"], ["Admin"])
        self.assertFalse(age_check["eligible"])
        self.assertIn("30 days", age_check["reason"])

    def test_member_can_check_eligibility_via_api(self):
        member = self.create_member("member", "member@example.com")
        event_id = self.create_event({"membership_status": "verified", "allowed_roles": "Participant"})
        self.login_member(member["id"])

        response = self.client.get(f"/api/voting/events/{event_id}/eligibility")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["eligible"])
        self.assertEqual(payload["rule"]["membership_status"], "verified")
        self.assertEqual(payload["rule"]["allowed_roles"], ["Participant"])

    def test_api_blocks_admin_and_invalid_option_votes(self):
        member = self.create_member("member", "member@example.com")
        event_id = self.create_event()
        self.login_admin()
        admin_response = self.client.post(
            "/api/voting/votes",
            json={"event_id": event_id, "option_id": self.first_option_id(event_id)},
        )
        self.assertEqual(admin_response.status_code, 403)

        self.login_member(member["id"])
        bad_option = self.client.post(
            "/api/voting/votes",
            json={"event_id": event_id, "option_id": 999},
        )
        audit = database.get_eligibility_audit(limit=1)[0]

        self.assertEqual(bad_option.status_code, 400)
        self.assertIn("valid voting option", bad_option.get_json()["error"])
        self.assertEqual(audit["eligible"], 0)
        self.assertIn("Selected option", audit["reason"])


if __name__ == "__main__":
    unittest.main()
