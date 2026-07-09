import io
import os
import tempfile
import unittest
from unittest.mock import patch

import database
import main


class TeamsFlowTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database.DB_NAME = self.db_path
        database.init_db()
        database.create_user("owner", "owner@example.com", "StrongPass1")
        database.create_user("artist", "artist@example.com", "StrongPass1")
        self.owner = database.get_user_by_email("owner@example.com")
        self.artist = database.get_user_by_email("artist@example.com")
        database.mark_user_verified(self.owner["id"])
        database.mark_user_verified(self.artist["id"])
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users_data SET full_name = 'Owner Dev', team_role = 'Developer' WHERE id = ?",
            (self.owner["id"],),
        )
        cursor.execute(
            "UPDATE users_data SET full_name = 'Pixel Artist', team_role = 'Artist', skills = 'pixel art' WHERE id = ?",
            (self.artist["id"],),
        )
        conn.commit()
        conn.close()
        main.app.config.update(TESTING=True, EMAIL_DELIVERY_MODE="test")
        self.previous_team_files_folder = main.app.config["TEAM_FILES_FOLDER"]
        self.team_files_dir = tempfile.TemporaryDirectory()
        main.app.config["TEAM_FILES_FOLDER"] = self.team_files_dir.name
        self.client = main.app.test_client()

    def tearDown(self):
        main.app.config["TEAM_FILES_FOLDER"] = self.previous_team_files_folder
        self.team_files_dir.cleanup()
        os.remove(self.db_path)

    def login(self, user_id):
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = user_id

    def test_dashboard_create_team_action_links_to_teams_page(self):
        self.login(self.owner["id"])

        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'href="/teams"', response.data)
        self.assertIn(b'href="/join-team"', response.data)
        self.assertIn(b">Teams<", response.data)
        self.assertIn(b'id="sidebarContentPanel"', response.data)
        self.assertIn(b"showSidebarContent", response.data)
        self.assertIn(b"sidebar-frame-active", response.data)
        self.assertIn(b".sidebar-content-panel .profile-header", response.data)
        self.assertIn(b"scopeCssBlock", response.data)
        self.assertIn(b"scopedPageStyles", response.data)
        self.assertIn(b"removePageBackgroundDeclarations", response.data)
        self.assertIn(b"sidebarContentPanel.replaceChildren(scopedStyles, extracted)", response.data)
        self.assertNotIn(b"<iframe", response.data)

    def test_admin_pages_use_consistent_dashboard_background(self):
        self.login(self.owner["id"])
        conn = database.get_connection()
        conn.execute("UPDATE users_data SET role = 'Admin' WHERE id = ?", (self.owner["id"],))
        conn.commit()
        conn.close()
        with self.client.session_transaction() as session:
            session["admin_username"] = "owner@example.com"

        for path in ("/bugs", "/help", "/user-manual", "/developer-guide", "/notifications", "/activity-summary"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"radial-gradient(circle at 78% 4%,rgba(6,182,212,.12),transparent 24%)", response.data)

    def test_create_team_page_does_not_show_team_chat(self):
        self.login(self.owner["id"])

        response = self.client.get("/teams")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Create Team", response.data)
        self.assertNotIn(b"Team Chat", response.data)
        self.assertNotIn(b"Team Files", response.data)

    def test_user_can_create_team_invite_member_and_invitee_accepts(self):
        self.login(self.owner["id"])
        response = self.client.post(
            "/teams",
            data={
                "action": "create_team",
                "team_name": "Parallel Pixels",
                "description": "Jam squad",
            },
        )
        self.assertEqual(response.status_code, 302)
        teams = database.list_user_teams(self.owner["id"])
        self.assertEqual(len(teams), 1)
        team = teams[0]
        self.assertEqual(team["name"], "Parallel Pixels")
        self.assertEqual(database.get_dashboard_stats(self.owner["id"])["teams_joined"], 1)

        page_response = self.client.get(f"/teams/{team['id']}")
        self.assertEqual(page_response.status_code, 200)
        self.assertIn(b'id="memberSearch"', page_response.data)
        self.assertIn(b'name="member_search"', page_response.data)
        self.assertNotIn(b'id="memberSearch" disabled', page_response.data)

        search_response = self.client.get("/api/teams/member-search?q=pixel")
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.get_json()["members"][0]["email"], "artist@example.com")

        with patch.object(main, "send_transactional_email", return_value={"sent": True, "detail": "sent"}) as send_email:
            invite_response = self.client.post(
                f"/teams/{team['id']}",
                data={
                    "action": "invite_member",
                    "invitee_id": str(self.artist["id"]),
                },
            )

        self.assertEqual(invite_response.status_code, 200)
        self.assertIn(b"Invite sent to artist@example.com", invite_response.data)
        invites = database.list_team_invites_for_user(self.artist["id"], "pending")
        self.assertEqual(len(invites), 1)
        self.assertIn("/team-invite/", invites[0]["invite_link"])
        send_email.assert_called_once()

        self.login(self.artist["id"])
        accept_response = self.client.get(f"/team-invite/{invites[0]['token']}")

        self.assertEqual(accept_response.status_code, 200)
        self.assertIn(b"You joined Parallel Pixels", accept_response.data)
        self.assertEqual(database.get_dashboard_stats(self.artist["id"])["teams_joined"], 1)
        self.assertEqual(len(database.get_team_members(team["id"])), 2)

        dashboard_response = self.client.get("/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn(b"Parallel Pixels", dashboard_response.data)
        self.assertIn(f"/teams/{team['id']}".encode(), dashboard_response.data)

    def test_team_members_can_post_messages_and_upload_files(self):
        team_id = database.create_team(self.owner["id"], "Asset Forge", "Build assets")
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO team_members (team_id, user_id, role, status) VALUES (?, ?, 'Member', 'active')",
            (team_id, self.artist["id"]),
        )
        conn.commit()
        conn.close()
        self.login(self.artist["id"])

        message_response = self.client.post(
            f"/teams/{team_id}",
            data={
                "action": "post_message",
                "message": "I uploaded the first concept sheet.",
            },
        )
        self.assertEqual(message_response.status_code, 302)
        page_response = self.client.get(f"/teams/{team_id}")
        self.assertIn(b"I uploaded the first concept sheet.", page_response.data)
        self.assertIn(b"Team Chat", page_response.data)
        self.assertIn(b'class="chat-row own"', page_response.data)
        self.assertIn(b"Press Ctrl+Enter to send", page_response.data)

        upload_response = self.client.post(
            f"/teams/{team_id}",
            data={
                "action": "upload_file",
                "team_file": (io.BytesIO(b"concept notes"), "concept.txt"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(upload_response.status_code, 302)
        files = database.list_team_files(team_id)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["original_filename"], "concept.txt")

        download_response = self.client.get(f"/team-files/{files[0]['id']}")
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response.data, b"concept notes")
        download_response.close()

    def test_member_can_leave_team_but_cannot_delete_it(self):
        team_id = database.create_team(self.owner["id"], "Leave Squad", "Temporary team")
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO team_members (team_id, user_id, role, status) VALUES (?, ?, 'Member', 'active')",
            (team_id, self.artist["id"]),
        )
        conn.commit()
        conn.close()
        self.login(self.artist["id"])

        page_response = self.client.get(f"/teams/{team_id}")
        self.assertEqual(page_response.status_code, 200)
        self.assertIn(b"Leave Team", page_response.data)
        self.assertIn(b"Leave this team? You will lose access to its chat and files.", page_response.data)
        self.assertNotIn(b"Delete Team", page_response.data)

        delete_response = self.client.post(
            f"/teams/{team_id}",
            data={"action": "delete_team"},
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertIn(b"Only the team creator or a team leader can delete this team.", delete_response.data)
        self.assertIsNotNone(database.get_team(team_id))

        leave_response = self.client.post(
            f"/teams/{team_id}",
            data={"action": "leave_team"},
        )
        self.assertEqual(leave_response.status_code, 302)
        self.assertFalse(database.user_is_team_member(team_id, self.artist["id"]))
        self.assertEqual(database.get_dashboard_stats(self.artist["id"])["teams_joined"], 0)

    def test_team_leader_can_delete_team(self):
        team_id = database.create_team(self.owner["id"], "Leader Ops", "Leader managed")
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO team_members (team_id, user_id, role, status) VALUES (?, ?, 'Leader', 'active')",
            (team_id, self.artist["id"]),
        )
        conn.commit()
        conn.close()
        self.login(self.artist["id"])

        page_response = self.client.get(f"/teams/{team_id}")
        self.assertEqual(page_response.status_code, 200)
        self.assertIn(b"Delete Team", page_response.data)
        self.assertIn(b"Delete this team permanently? This removes team chat, invites, members, and files.", page_response.data)
        self.assertIn(b"Leave Team", page_response.data)
        self.assertIn(b"Leave this team? You will lose access to its chat and files.", page_response.data)

        delete_response = self.client.post(
            f"/teams/{team_id}",
            data={"action": "delete_team"},
        )
        self.assertEqual(delete_response.status_code, 302)
        self.assertIsNone(database.get_team(team_id))
        self.assertEqual(database.get_team_members(team_id), [])

    def test_user_can_find_team_by_name_only_and_join(self):
        team_id = database.create_team(self.owner["id"], "Only Name Match", "No searchable keyword here")
        self.login(self.artist["id"])

        page_response = self.client.get("/join-team")
        self.assertEqual(page_response.status_code, 200)
        self.assertIn(b"Join Team", page_response.data)
        self.assertIn(b'id="teamSearch"', page_response.data)
        self.assertIn(b"Only team names are searched.", page_response.data)

        by_name_response = self.client.get("/api/teams/search?q=name")
        self.assertEqual(by_name_response.status_code, 200)
        by_name_payload = by_name_response.get_json()
        self.assertEqual(by_name_payload["teams"][0]["name"], "Only Name Match")

        by_description_response = self.client.get("/api/teams/search?q=keyword")
        self.assertEqual(by_description_response.status_code, 200)
        self.assertEqual(by_description_response.get_json()["teams"], [])

        join_response = self.client.post(
            "/join-team",
            data={"team_id": str(team_id)},
        )
        self.assertEqual(join_response.status_code, 302)
        self.assertEqual(database.get_dashboard_stats(self.artist["id"])["teams_joined"], 1)
        self.assertEqual(len(database.get_team_members(team_id)), 2)

        joined_search_response = self.client.get("/api/teams/search?q=name")
        self.assertEqual(joined_search_response.get_json()["teams"], [])


if __name__ == "__main__":
    unittest.main()
