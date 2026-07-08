# IDMS Technical Documentation

Published: 2026-07-08

## Architecture

IDMS is a Flask application backed by SQLite and server-rendered HTML templates.

Primary layers:

- `main.py`: Flask app setup, authentication decorators, request parsing, routes, API endpoints, file download responses, and CSV exports.
- `database.py`: SQLite schema creation, migrations, validation, persistence helpers, reporting queries, and activity logging.
- `frontend/pages/`: Jinja HTML templates for browser-facing pages.
- `secure_uploads/`: Runtime storage for uploaded files and meeting minutes.
- `test_*.py`: `unittest` regression suite using temporary SQLite databases.
- `documentation/`: user, testing, and technical documentation.

Request flow:

1. Browser or API client sends a form or JSON request to a Flask route.
2. Route enforces `login_required` and, where needed, `admin_required`.
3. Route normalizes request data and calls a `database.py` helper.
4. Helper validates input, reads/writes SQLite, and logs activity when relevant.
5. Route returns rendered HTML, JSON, file download, or CSV download.

## Runtime Configuration

Configuration is loaded from environment variables and optional `.env` values.

Important settings:

- `PEXEL_SECRET_KEY`: Flask and token signing secret.
- `PEXEL_EMAIL_DELIVERY_MODE`: Email delivery mode.
- `PEXEL_EMAIL_FROM_ADDRESS`, `PEXEL_EMAIL_FROM_NAME`: Sender identity.
- `PEXEL_SMTP_HOST`, `PEXEL_SMTP_PORT`, `PEXEL_SMTP_USERNAME`, `PEXEL_SMTP_PASSWORD`: SMTP configuration.
- `PEXEL_SMTP_USE_TLS`, `PEXEL_SMTP_USE_SSL`: SMTP transport options.
- `PEXEL_EMAIL_TIMEOUT`: Email timeout in seconds.

Upload limits and folders are configured in `main.py`:

- `MAX_CONTENT_LENGTH`: 16 MB request limit.
- `PER_FILE_MAX_SIZE`: 5 MB per uploaded file.
- `UPLOAD_FOLDER`: `secure_uploads`.
- `MEETING_MINUTES_FOLDER`: `secure_uploads/meeting_minutes`.
- `IMPORT_FOLDER`: `secure_uploads/imports`.

## Database Schema

Schema is initialized in `database.init_db()` and evolved with `add_column_if_missing()`.

Core tables:

- `users_data`: member accounts, profile details, verification, notification preference.
- `auth_email_links`: registration verification and password reset links.
- `uploads`: uploaded documents and approval/category state.
- `document_categories`: category catalog for document organization.
- `document_downloads`: secure download audit records.
- `document_title_search`: FTS5 virtual table for document title search.
- `import_jobs`, `import_rows`, `import_changes`: admin import validation, merge, and rollback state.
- `activity_log`: cross-module activity feed used by Activity Summary.
- `voting_events`, `voting_options`, `votes`, `eligibility_audit`: voting workflow.
- `whatsapp_messages`: imported WhatsApp chat messages and analytics source.
- `notifications`: in-app/email notification history and scheduled notifications.
- `meetings`, `meeting_attendance`, `meeting_minutes`: meeting schedule, attendance, and files.
- `financial_transactions`, `budgets`, `budget_categories`, `budget_alerts`: finance reporting and budget monitoring.
- `bug_reports`: defect reporting, priority, assignment, fix notes, and verification details.

Notable indexes:

- User lookup indexes on email, username, role, verification, and profile fields.
- Upload indexes for approval/category/title queries.
- Meeting indexes by date and type.
- Finance indexes by transaction date, type, and category.
- Bug index by status and priority.

## Authentication and Authorization

Decorators:

- `login_required`: requires either a member session or admin session.
- `admin_required`: requires an admin session.

Admin accounts are configured as demo username/password lists in `main.py`. Member authentication uses bcrypt password hashes stored in `users_data.password_hash`.

Email verification and password reset links are signed with `itsdangerous.URLSafeTimedSerializer`.

## Public Pages

- `GET /`: home page.
- `GET|POST /register`: create member account and verification email.
- `GET /verify-email/<token>`: verify registration email.
- `GET|POST /login`: member or demo admin login.
- `GET|POST /forgot-password`: request password reset.
- `GET|POST /reset-password/<token>`: complete password reset.
- `GET /logout`: clear session.

## Member Pages

- `GET /dashboard`: dashboard.
- `GET|POST /profile`: profile management.
- `GET|POST /import-files`: legacy upload/import page.
- `GET /files`: approved document browser.
- `GET /files/<file_id>/download`: secure file download.
- `GET|POST /voting`: voting page and vote casting.
- `GET|POST /meetings`: meeting browser and admin meeting management.
- `GET /notifications`: notification center.
- `GET|POST /bugs`: defect reporting and admin status workflow.
- `GET /help`: help hub.
- `GET /user-manual`: in-app user manual.

## Admin Pages

- `GET|POST /admin/document-categories`: document category management.
- `GET /admin/members`: member administration.
- `GET /admin/import-data`: admin import workflow.
- `GET|POST /financial`: finance, reports, transactions, and budgets.
- `GET|POST /whatsapp-analytics`: WhatsApp import and analytics.
- `GET /activity-summary`: activity reporting.
- `GET /developer-guide`: technical guide page.

## API Endpoints

Admin/member APIs:

- `GET /api/documents`: document search and filtering.
- `POST /api/voting/events`: create voting event.
- `POST /api/voting/votes`: cast vote.
- `GET /api/voting/events/<event_id>/eligibility`: eligibility check.
- `GET /api/voting/events/<event_id>/results`: results JSON.
- `GET /api/voting/events/<event_id>/results.csv`: results CSV.
- `POST /api/whatsapp/import`: import chat export.
- `GET /api/whatsapp/analytics`: analytics JSON.
- `GET /api/notifications`: notifications JSON.
- `POST /api/notifications/process-due`: process scheduled notifications.
- `GET /api/meetings`: meeting list and calendar days.
- `POST /api/meetings`: create meeting.
- `GET /api/meetings/attendance`: attendance summary/report JSON.
- `GET /api/meetings/attendance.csv`: attendance CSV.
- `GET /api/meetings/minutes`: minutes list.
- `GET /api/financial/transactions`: recent transactions.
- `POST /api/financial/transactions`: create financial transaction.
- `GET /api/financial/budgets`: budget status and categories.
- `POST /api/financial/budgets`: create or update budget.
- `POST /api/financial/budget-alerts`: generate budget alerts.
- `GET /api/financial/report`: finance report JSON.
- `GET /api/financial/report.csv`: finance report CSV.
- `GET /api/admin/activity-summary`: activity summary JSON.
- `GET /api/admin/member-stats`: member statistics.
- `GET /api/admin/member-growth`: member growth history.
- `GET /api/admin/members`: member search and filters.
- `POST /api/admin/import/upload`: upload import file.
- `POST /api/admin/import/validate`: validate import mapping.
- `PATCH /api/admin/import/<job_id>/rows/<row_id>`: correct import row.
- `POST /api/admin/import/merge`: merge import rows.
- `GET /api/admin/import/history`: import history.
- `POST /api/admin/import/<job_id>/rollback`: rollback import.

## Validation Rules

Examples of important validation:

- Passwords must satisfy length, uppercase, lowercase, and digit requirements.
- Voting events require future start/end windows and at least two options.
- Votes are unique per event/member.
- Document categories are unique case-insensitively.
- Meeting dates must be future dates and cannot conflict within the configured window.
- Financial transactions require `YYYY-MM-DD`, positive amount, type `income` or `expense`, and a category.
- Budgets require positive amounts and warning threshold lower than critical threshold.
- Bug reports require valid severity, priority, reproducibility, title, steps, expected, and actual behavior.
- Bug fixes require fix notes before `Fixed`; verification notes before `Verified`.

## Reporting

Generated reports:

- Voting results JSON/CSV.
- WhatsApp analytics by participant, day, weekday, hour, and media type.
- Meeting attendance summary/report JSON/CSV.
- Finance reports with totals, monthly net, expense categories, budget status, summaries, and CSV sections.
- Activity Summary with widgets, highlights, module breakdown, timeline, and recent feed.
- Bug tracker summary by status and priority.

## File Handling

Uploads use `werkzeug.utils.secure_filename`, UUID-based stored names, size limits, extension allow lists, and restricted file permissions where supported. Downloads use `send_from_directory` with private cache controls and download audit logging.

## Testing

Run all tests:

```powershell
python -m unittest
```

Test design:

- Each suite uses a temporary SQLite database.
- `database.DB_NAME` is redirected in test setup.
- Flask routes are tested with `main.app.test_client()`.
- Tests cover happy paths, validation failures, authorization, duplicate prevention, exports, reports, notifications, and bug verification.

## Maintenance Checklist

When adding a feature:

1. Add or migrate schema in `database.init_db()`.
2. Add validation in `database.py`, not only in route code.
3. Keep route handlers thin and use helper functions for persistence.
4. Add activity logging for admin-visible workflows.
5. Protect admin features with `admin_required`.
6. Add focused `unittest` coverage.
7. Update `documentation/user_manual.md` for user-facing behavior.
8. Update this technical guide for schema, routes, or API changes.
9. Run `python -m unittest`.

## Review Notes

This document was reviewed against `main.py`, `database.py`, `frontend/pages`, and the current test suite on 2026-07-08.

