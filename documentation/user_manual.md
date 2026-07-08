# IDMS User Manual

Published: 2026-07-08

## Overview

IDMS is a member and organization management platform for registrations, documents, voting, meetings, notifications, financial tracking, activity reporting, imports, and bug tracking. Access to some areas depends on whether you are signed in as a member or as an administrator.

## Getting Started

1. Open the application and choose Register.
2. Enter your username, email address, and password.
3. Verify your email if verification is required.
4. Sign in and open Profile to complete your full name, role, bio, skills, and notification preference.
5. Use Dashboard as the main launch point for your available workflows.

## Dashboard

The Dashboard summarizes your current work. Members see personal participation stats. Administrators see member statistics, import status, and recent activity widgets for meetings, voting, documents, and system activity.

Use the left navigation to open Voting, Meetings, Documents, Finance, WhatsApp analytics, Notifications, Activity Summary, Bugs, Help, and Developer Guide.

## Profile

Use Profile to maintain account details:

- Full name, username, and email.
- Bio, skills, and team role.
- Notification preference.
- Profile picture URL or reference, when available.

Administrators use demo admin accounts and cannot edit those demo profile details from Profile.

## Documents

Members can upload and browse approved documents. Administrators can approve uploads, categorize documents, and manage document categories.

Common document tasks:

- Upload accepted file types from Documents.
- Search documents by title.
- Filter or assign categories.
- Download approved files.
- Review document notifications when new approved documents are available.

## Voting

Administrators create voting events with titles, descriptions, options, start/end dates, and eligibility rules. Members can vote once per active event when eligible.

Voting rules:

- Events must have valid future date windows.
- Eligible members can cast one vote per event.
- Results are restricted until the configured workflow permits viewing.
- Administrators can export voting results as CSV.

## Meetings

Administrators schedule meetings, manage attendance, upload minutes, and export attendance reports. Members can review upcoming meetings, agendas, locations, and minutes.

Meeting tools include:

- Scheduling with conflict checks.
- Meeting type classification.
- Invitee and agenda tracking.
- Attendance states: present, absent, excused.
- Minutes upload and secure download.
- Meeting notifications and reminders.

## Finance

Administrators use Finance to record transactions, monitor budgets, review reports, and export financial data.

Finance workflows:

- Record income or expense transactions with date, category, amount, and description.
- Review income, expenses, net balance, monthly performance, and expense categories.
- Create budgets by category and fiscal period.
- Configure warning and critical budget thresholds.
- Generate budget alerts when spending reaches configured thresholds.
- Export financial report sections as CSV.

## WhatsApp Analytics

Administrators can import WhatsApp `.txt` chat exports and review analytics.

Supported rows include common WhatsApp export formats such as:

- `6/20/26, 9:01 AM - Alex: Hello team`
- `[12/31/2025, 9:15 PM] Name: Message`

Analytics include total messages, participants, messages over time, top participants, message types, peak hours, weekdays, active participants, and recent messages.

## Notifications

Notifications show event, meeting, document, budget, and voting messages. Administrators can send manual reminders and process scheduled notifications. Members can opt in or out from Profile.

## Activity Summary

Administrators use Activity Summary to review daily, weekly, and monthly activity.

The report includes:

- Dashboard widgets for meetings, voting, documents, and recent actions.
- Summary highlights.
- Module breakdown.
- Timeline bars.
- Recent activity feed.

## Bug Tracking

Use Bugs to document defects and track resolution.

Bug reports include:

- Title, severity, priority, module, environment, build/version, reproducibility, and assignment.
- Steps to reproduce.
- Expected behavior.
- Actual behavior.
- Status workflow: Open, In Progress, Fixed, Verified.
- Fix notes and verification notes.

Administrators update assignment, status, fix notes, and verification details. Regular members can report bugs but cannot verify closure.

## Admin Data Imports

Administrators can upload supported import files, validate rows, map fields, resolve duplicate conflicts, merge records, and use rollback windows after imports.

Import states include uploaded, validated, needs manual resolution, merged, failed, and rolled back.

## User Roles

Members can:

- Maintain their profile.
- Browse documents.
- Vote when eligible.
- Review meetings and minutes.
- View notifications.
- Report bugs.

Administrators can:

- Manage members and imports.
- Approve and categorize documents.
- Create voting events.
- Schedule meetings and attendance.
- Manage finance, budgets, and reports.
- Review activity summaries.
- Process notifications.
- Triage and verify bugs.

## Troubleshooting

- If sign-in fails, confirm your email/username and password, then use password reset if needed.
- If a document is missing, check whether it is approved and categorized.
- If you cannot vote, review event timing and eligibility requirements.
- If an export does not download, report a bug with steps, expected behavior, and actual behavior.
- If budget alerts do not appear, confirm the budget category matches expense transaction categories.

## Screenshot Checklist

Screenshots should be captured for these published guide sections:

- Login and registration.
- Dashboard member view.
- Dashboard admin widgets.
- Documents list and category management.
- Voting event and results.
- Meetings calendar, attendance, and minutes.
- Finance report and budget status.
- WhatsApp analytics.
- Activity Summary report.
- Bug Tracking workflow.

