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
        self.assertIn(b"normalizeLoadedPageActions", response.data)
        self.assertIn(b'form.setAttribute("action", pageUrl)', response.data)
        self.assertIn(b"sidebarContentPanel.replaceChildren(scopedStyles, extracted)", response.data)
        self.assertNotIn(b"<iframe", response.data)

    def test_user_bug_support_report_notifies_admin(self):
        self.login(self.artist["id"])

        dashboard_response = self.client.get("/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn(b"Report Bug / Support", dashboard_response.data)
        self.assertIn(b'href="/bugs"', dashboard_response.data)

        report_response = self.client.post(
            "/bugs",
            data={
                "action": "create",
                "title": "Sidebar button failed",
                "severity": "Medium",
                "priority": "High",
                "module": "Dashboard",
                "environment": "Chrome",
                "build_version": "local",
                "reproducibility": "Always",
                "steps": "Click the sidebar support button.",
                "expected": "Support form opens.",
                "actual": "Nothing happens.",
            },
        )
        self.assertEqual(report_response.status_code, 200)
        self.assertIn(b"Pending", report_response.data)

        bugs = database.list_bug_reports()
        self.assertEqual(len(bugs), 1)
        self.assertEqual(bugs[0]["status"], "Pending")
        self.assertEqual(bugs[0]["title"], "Sidebar button failed")

        notifications = database.list_notifications()
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["category"], "bug")
        self.assertEqual(notifications[0]["metadata"]["bug_id"], bugs[0]["id"])
        self.assertIn("Sidebar button failed", notifications[0]["title"])

        self.login(self.owner["id"])
        conn = database.get_connection()
        conn.execute("UPDATE users_data SET role = 'Admin' WHERE id = ?", (self.owner["id"],))
        conn.commit()
        conn.close()
        with self.client.session_transaction() as session:
            session["admin_username"] = "owner@example.com"

        notification_response = self.client.get("/notifications")
        self.assertEqual(notification_response.status_code, 200)
        self.assertIn(b"New bug/support report: Sidebar button failed", notification_response.data)

        fixed_response = self.client.post(
            "/bugs",
            data={
                "action": "status",
                "bug_id": str(bugs[0]["id"]),
                "status": "Fixed",
                "assigned_to": "Owner Dev",
                "fix_notes": "Restored the sidebar action.",
                "resolution_notes": "Fixed in dashboard navigation.",
            },
        )
        self.assertEqual(fixed_response.status_code, 200)
        self.assertEqual(database.list_bug_reports()[0]["status"], "Fixed")

    def test_dashboard_post_bug_form_fallback_avoids_method_not_allowed(self):
        self.login(self.artist["id"])

        response = self.client.post(
            "/dashboard",
            data={
                "action": "create",
                "title": "Injected form fallback",
                "severity": "Low",
                "priority": "Low",
                "module": "Dashboard",
                "environment": "Browser",
                "build_version": "local",
                "reproducibility": "Sometimes",
                "steps": "Submit the injected bug form.",
                "expected": "Report is saved.",
                "actual": "Dashboard accepted the fallback post.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard#/bugs", response.headers["Location"])
        bugs = database.list_bug_reports()
        self.assertEqual(len(bugs), 1)
        self.assertEqual(bugs[0]["title"], "Injected form fallback")

    def test_admin_dashboard_shows_total_teams(self):
        database.create_team(self.owner["id"], "Admin Visible Team", "Count me")
        self.login(self.owner["id"])
        conn = database.get_connection()
        conn.execute("UPDATE users_data SET role = 'Admin' WHERE id = ?", (self.owner["id"],))
        conn.commit()
        conn.close()
        with self.client.session_transaction() as session:
            session["admin_username"] = "owner@example.com"

        stats = database.get_member_statistics()
        self.assertEqual(stats["total_teams"], 1)

        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Total Teams", response.data)
        self.assertIn(b'data-member-stat="total_teams">1</div>', response.data)

        api_response = self.client.get("/api/admin/member-stats")
        self.assertEqual(api_response.status_code, 200)
        self.assertEqual(api_response.get_json()["total_teams"], 1)

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
        self.assertIn(b'data-stat="member_count">2</strong>', page_response.data)
        self.assertIn(b'data-stat="message_count">1</strong>', page_response.data)
        self.assertIn(b'data-stat="unread_message_count">0</strong>', page_response.data)
        self.assertIn(b"chat-row own", page_response.data)
        self.assertIn(b'id="fileToggle"', page_response.data)
        self.assertIn(b'id="fileChoice"', page_response.data)
        self.assertIn(b'Use + to attach a file.', page_response.data)
        self.assertNotIn(b"<h2>Your Teams</h2>", page_response.data)
        self.assertNotIn(b"<h2>Team Files</h2>", page_response.data)
        self.assertNotIn(b"Peak Chat Hour", page_response.data)
        self.assertNotIn(b"Most Active", page_response.data)
        self.assertNotIn(b"Least Active", page_response.data)
        notifications = database.list_notifications(recipient_id=self.owner["id"])
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["category"], "team_message")
        self.assertEqual(notifications[0]["metadata"]["team_id"], team_id)
        self.assertEqual(notifications[0]["metadata"]["sender_id"], self.artist["id"])
        self.assertEqual(database.list_notifications(recipient_id=self.artist["id"]), [])

        self.login(self.owner["id"])
        owner_notifications = self.client.get("/api/notifications").get_json()["notifications"]
        self.assertEqual(len(owner_notifications), 1)
        self.assertIn("New message in Asset Forge", owner_notifications[0]["title"])
        owner_status = self.client.get(f"/api/teams/{team_id}/status").get_json()
        self.assertEqual(owner_status["analytics"]["unread_message_count"], 0)
        self.assertEqual(owner_status["messages"][-1]["message"], "I uploaded the first concept sheet.")
        self.assertTrue(owner_status["messages"][-1]["is_unread"])
        self.assertEqual(self.client.get("/api/notifications").get_json()["notifications"], [])
        owner_page_response = self.client.get(f"/teams/{team_id}")
        self.assertIn(b'data-stat="unread_message_count">0</strong>', owner_page_response.data)
        self.assertIn(b"Peak Chat Hour", owner_page_response.data)
        self.assertIn(b"Most Active", owner_page_response.data)
        self.assertIn(b"Least Active", owner_page_response.data)
        self.assertIn(b"Pixel Artist", owner_page_response.data)
        self.assertIn(b"Owner Dev", owner_page_response.data)
        self.assertNotIn(b"New message in Asset Forge", self.client.get("/notifications").data)

        reply_response = self.client.post(
            f"/teams/{team_id}",
            data={
                "action": "post_message",
                "message": "Looks good from owner.",
            },
        )
        self.assertEqual(reply_response.status_code, 302)
        self.login(self.artist["id"])
        artist_notifications = self.client.get("/api/notifications").get_json()["notifications"]
        self.assertEqual(len(artist_notifications), 1)
        self.assertEqual(artist_notifications[0]["metadata"]["sender_id"], self.owner["id"])
        artist_status = self.client.get(f"/api/teams/{team_id}/status").get_json()
        self.assertEqual(artist_status["analytics"]["unread_message_count"], 0)
        self.assertEqual(artist_status["messages"][-1]["message"], "Looks good from owner.")
        self.assertTrue(artist_status["messages"][-1]["is_unread"])
        self.assertEqual(self.client.get("/api/notifications").get_json()["notifications"], [])
        artist_page_response = self.client.get(f"/teams/{team_id}")
        self.assertIn(b"Looks good from owner.", artist_page_response.data)
        self.assertIn(b'data-stat="unread_message_count">0</strong>', artist_page_response.data)

        upload_response = self.client.post(
            f"/teams/{team_id}",
            data={
                "action": "upload_file",
                "team_file": (io.BytesIO(b"PK zip bytes"), "build.zip"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(upload_response.status_code, 302)
        files = database.list_team_files(team_id)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["original_filename"], "build.zip")
        messages = database.list_team_messages(team_id)
        self.assertEqual(messages[-1]["file_id"], files[0]["id"])
        self.assertEqual(messages[-1]["attachment_name"], "build.zip")
        upload_page_response = self.client.get(f"/teams/{team_id}")
        self.assertIn(b"Uploaded build.zip", upload_page_response.data)
        self.assertIn(b"build.zip", upload_page_response.data)
        self.assertIn(f"/team-files/{files[0]['id']}".encode(), upload_page_response.data)

        download_response = self.client.get(f"/team-files/{files[0]['id']}")
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response.data, b"PK zip bytes")
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
        conn = database.get_connection()
        membership = conn.execute(
            "SELECT status FROM team_members WHERE team_id = ? AND user_id = ?",
            (team_id, self.artist["id"]),
        ).fetchone()
        conn.close()
        self.assertEqual(membership["status"], "left")

        rejoin_response = self.client.post(
            "/join-team",
            data={"team_id": str(team_id)},
        )
        self.assertEqual(rejoin_response.status_code, 302)
        self.assertTrue(database.user_is_team_member(team_id, self.artist["id"]))
        self.assertEqual(database.get_dashboard_stats(self.artist["id"])["teams_joined"], 1)
        self.assertEqual(len(database.get_team_members(team_id)), 2)

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
