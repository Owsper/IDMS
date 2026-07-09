# IDMS

IDMS is a Flask-based web application for managing members, documents, teams, team chat, voting, meetings, finance records, notifications, activity reports, WhatsApp analytics, imports, and bug reports.

The project is designed as a university/group project for frontend and agile development. It uses a Python Flask backend, server-rendered HTML pages, SQLite database storage, and local secure upload folders.

> Note: The full expansion of "IDMS" is not defined in the project folder. This README uses the project name exactly as it appears in the repository.

## Table of Contents

- [Project Overview](#project-overview)
- [Main Features](#main-features)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Setup and Installation](#setup-and-installation)
- [Running the Application](#running-the-application)
- [Testing](#testing)
- [Database and Storage](#database-and-storage)
- [Documentation](#documentation)
- [Important Notes](#important-notes)
- [Recommended README Images](#recommended-readme-images)
- [Working Instance Screenshots To Add](#working-instance-screenshots-to-add)

## Project Overview

IDMS provides a central platform for organization and member management. Instead of handling members, files, meetings, voting, finance, and communication in separate tools, IDMS brings these workflows into one web system.

The system supports two main access levels:

- **Members** can register, log in, manage their profile, view documents, join teams, use team chat, vote, view meetings, receive notifications, and submit bug reports.
- **Admins** can manage members, document categories, imports, voting events, meetings, finance records, notifications, activity summaries, and system reports.

## Main Features

### Authentication and User Management

- Member registration and login.
- Email verification and password reset support.
- Password hashing with `bcrypt`.
- Session-based access control.
- Admin-only pages and member-only pages.
- Member profile fields such as name, username, email, bio, skills, team role, notification preference, and profile image/reference.

### Dashboard and Profile

- Member dashboard with personal system statistics.
- Admin dashboard data and member/activity widgets.
- Profile update page for member information.

### Documents and File Management

- Upload and browse documents.
- Document categories managed by admins.
- Document search and filtering.
- Secure file download routes.
- Download activity logging.
- Local file storage under `secure_uploads/`.

### Teams and Team Chat

- Create and join teams.
- Invite members to a team.
- Leave teams with database membership updates.
- Team detail page with member list and team chat.
- Team chat messages with unread message tracking.
- Team message notifications for members who have not read new messages.
- Realtime/polling status updates for team unread messages and chat statistics.
- Team file attachments from the message input area.
- Team file uploads support different file types, including `.zip`, while still applying size limits.
- Team leader/owner statistics such as peak chat hour, most active member, and least active member.

### Voting

- Admin-created voting events.
- Voting options and eligibility checks.
- One-vote behavior for eligible members.
- Voting result reports and CSV export.

### Meetings

- Meeting scheduling.
- Attendance recording.
- Meeting minutes upload, storage, and download.
- Meeting notifications and attendance export.

### Finance

- Income and expense transaction recording.
- Net balance calculation.
- Expense validation so a new expense cannot exceed the available net balance.
- Budgets, budget categories, and budget alerts.
- Financial reports and CSV export.

### Notifications

- Notifications for documents, meetings, voting, budgets, and team messages.
- Read/unread notification state.
- Team chat unread notifications are cleared when the user views the relevant team channel.

### WhatsApp Analytics

- Import WhatsApp `.txt` exports.
- Analyze message counts, participants, active users, peak hours, weekdays, media usage, and recent messages.

### Activity Summary

- Activity logging for important system events.
- Admin activity summary reports and recent activity views.

### Bug Tracking

- Members can submit bug reports.
- Bug reports include workflow fields such as severity, priority, module, environment, steps to reproduce, expected result, and actual result.
- Admins can update bug status through the defect workflow.

### Admin Data Import

- Admin import workflow for structured data.
- Validation, mapping, duplicate handling, merge history, and rollback metadata are documented and tested.

## Technology Stack

| Area | Technology |
| --- | --- |
| Backend | Python, Flask |
| Frontend | HTML, CSS, JavaScript, Jinja templates |
| Database | SQLite |
| Authentication | Flask sessions, `bcrypt`, `itsdangerous` |
| File Handling | Local secure upload folders |
| Data Import | CSV/JSON/SQLite-related handling, `openpyxl` |
| Testing | Python `unittest` |
| Documentation | Markdown files in `documentation/` |

Python dependencies are listed in `requirements.txt`:

```text
bcrypt
certifi
flask
itsdangerous
openpyxl
```

## Project Structure

```text
IDMS/
|-- README.md
|-- requirements.txt
|-- main_db.db
|-- src/
|   |-- main.py
|   |-- database.py
|   `-- test_*.py
|-- frontend/
|   |-- packages.json
|   `-- pages/
|       |-- DashboardPage.html
|       |-- LoginPage.html
|       |-- RegisterPage.html
|       |-- TeamDetailPage.html
|       |-- TeamsPage.html
|       |-- FinancialPage.html
|       |-- VotingPage.html
|       |-- MeetingsPage.html
|       `-- other Jinja/HTML pages
|-- documentation/
|   |-- technical_documentation.md
|   |-- user_manual.md
|   |-- system_testing_plan.md
|   |-- screenshots.md
|   `-- admin_data_import_merge_tickets.md
`-- secure_uploads/
    |-- imports/
    |-- meeting_minutes/
    |-- team_files/
    `-- game_submissions/
```

### Important Source Files

| File | Purpose |
| --- | --- |
| `src/main.py` | Main Flask application, routes, page rendering, APIs, uploads, downloads, and session handling. |
| `src/database.py` | SQLite schema creation, migrations, database helpers, validation, reporting, notifications, teams, finance, voting, meetings, and activity logic. |
| `frontend/pages/` | Server-rendered Jinja/HTML pages for public, member, and admin screens. |
| `src/test_*.py` | Unit and regression tests for major system modules. |
| `documentation/` | User, technical, testing, screenshot, and import documentation. |

## Setup and Installation

These commands are intended for Windows PowerShell from the project root folder.

1. Create a virtual environment:

```powershell
python -m venv .venv
```

2. Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
pip install -r requirements.txt
```

4. Check that the project database exists:

```powershell
dir main_db.db
```

The project already includes `main_db.db`. The schema logic is also defined in `src/database.py`.

## Running the Application

Start the Flask application:

```powershell
python src\main.py
```

Then open the application in a browser:

```text
http://127.0.0.1:5000
```

Flask debug mode is enabled in `src/main.py` when the file is run directly.

## Testing

Run the full Python test suite:

```powershell
python -m unittest discover -s src
```

The project includes tests for:

- Authentication and password reset.
- Password policy.
- Admin member management.
- Document categories, search, notifications, and downloads.
- Data imports.
- Voting eligibility and voting results.
- WhatsApp import and analytics.
- Meeting scheduling, attendance, minutes, and notifications.
- Financial transactions and reports.
- Activity summary.
- Team workflows.
- Game/project submissions.
- Bug tracking and system testing.

The system testing plan in `documentation/system_testing_plan.md` reports a documented execution on `2026-07-08` with `101` tests passed. Run the command above again to verify the current working version.

## Database and Storage

IDMS uses SQLite for local persistence. The main database file is:

```text
main_db.db
```

The database schema and helper functions are maintained in:

```text
src/database.py
```

Major database areas include:

| Area | Tables / Purpose |
| --- | --- |
| Users and authentication | `users_data`, `auth_email_links` |
| Documents | `uploads`, `document_categories`, `document_downloads`, `document_title_search` |
| Teams | `teams`, `team_members`, `team_invites`, `team_messages`, `team_files` |
| Submissions | `submissions`, `submission_contributors`, `submission_files` |
| Voting | `voting_events`, `voting_options`, `votes`, `eligibility_audit` |
| Meetings | `meetings`, `meeting_attendance`, `meeting_minutes` |
| Finance | `financial_transactions`, `budgets`, `budget_categories`, `budget_alerts` |
| Notifications and activity | `notifications`, `activity_log` |
| Imports | `import_jobs`, `import_rows`, `import_changes` |
| Analytics and bugs | `whatsapp_messages`, `bug_reports` |

Runtime uploaded files are stored locally under:

```text
secure_uploads/
```

Important upload folders:

- `secure_uploads/imports/`
- `secure_uploads/meeting_minutes/`
- `secure_uploads/team_files/`
- `secure_uploads/game_submissions/`

## Documentation

The project contains supporting documentation:

| File | Description |
| --- | --- |
| `documentation/user_manual.md` | User-facing guide for the main system features. |
| `documentation/technical_documentation.md` | Architecture, modules, routes, database, validation, reporting, and maintenance notes. |
| `documentation/system_testing_plan.md` | Testing objective, scope, strategy, test matrix, command, and documented result. |
| `documentation/screenshots.md` | Planned screenshot checklist. |
| `documentation/admin_data_import_merge_tickets.md` | Admin import and merge-related documentation. |

## Important Notes

- The project uses local SQLite storage, not an external production database.
- Uploaded files are stored locally in `secure_uploads/`.
- Admin credentials are configured in code for the current project/demo setup.
- `.env` exists for runtime configuration such as secret keys and email settings. Do not commit real secrets.
- Actual screenshot image files were not found in the project folder at the time this README was updated.
- `documentation/documentation.md` exists but is currently empty.
- `frontend/packages.json` exists but is empty, so no frontend package workflow is documented there.
- External deployment, load testing, penetration testing, and browser visual regression testing are not documented in the project folder.

## Recommended README Images

Create a folder for README screenshots:

```text
documentation/images/
```

Use clear filenames so the screenshots are easy to understand in the final report and README.

| README Section | Suggested Image Path | What To Capture |
| --- | --- | --- |
| Project Overview | `documentation/images/home-page.png` | The public home page or first page users see. |
| Authentication and User Management | `documentation/images/login-page.png` | Login screen. |
| Authentication and User Management | `documentation/images/register-page.png` | Registration screen. |
| Dashboard and Profile | `documentation/images/member-dashboard.png` | Member dashboard after login. |
| Dashboard and Profile | `documentation/images/profile-page.png` | Profile page with editable member information. |
| Documents and File Management | `documentation/images/documents-page.png` | Documents/files page showing uploaded documents or filters. |
| Teams and Team Chat | `documentation/images/teams-page.png` | Teams list or team creation page. |
| Teams and Team Chat | `documentation/images/team-channel.png` | Team detail page showing members, chat, unread messages, and message input. |
| Teams and Team Chat | `documentation/images/team-file-attachment.png` | Team chat message box with the plus/upload attachment control. |
| Voting | `documentation/images/voting-page.png` | Voting page with available events or results. |
| Meetings | `documentation/images/meetings-page.png` | Meetings page showing scheduled meetings or attendance. |
| Finance | `documentation/images/financial-page.png` | Financial page showing transactions, net balance, budgets, or reports. |
| Notifications | `documentation/images/notifications-page.png` | Notifications page showing read/unread notifications. |
| WhatsApp Analytics | `documentation/images/whatsapp-analytics.png` | WhatsApp analytics dashboard after importing data. |
| Activity Summary | `documentation/images/activity-summary.png` | Admin activity summary page. |
| Bug Tracking | `documentation/images/bug-tracker.png` | Bug tracker page with submitted issues or workflow status. |
| Admin Features | `documentation/images/admin-members.png` | Admin members page. |
| Admin Features | `documentation/images/admin-import-data.png` | Admin import data page. |

After adding images, you can embed selected screenshots in this README using Markdown:

```md
![Team channel with chat and unread messages](documentation/images/team-channel.png)
```

## Working Instance Screenshots To Add

For the final project evidence section, capture screenshots from a running local instance at `http://127.0.0.1:5000`.

Add these working instance screenshots first because they best prove the system is functional:

1. Login page.
2. Register page.
3. Member dashboard.
4. Admin dashboard or admin members page.
5. Documents/files page.
6. Teams page.
7. Team channel page with member statistics, chat messages, unread message count, and file attachment button.
8. Notifications page showing unread/read notification behavior.
9. Voting page.
10. Meetings page.
11. Financial page showing income, expenses, net balance, and budget/report area.
12. WhatsApp analytics page.
13. Activity summary page.
14. Bug tracker page.

Place all working screenshots inside:

```text
documentation/images/
```

Then update `documentation/screenshots.md` from planned status to completed status for each screenshot that has been captured.
