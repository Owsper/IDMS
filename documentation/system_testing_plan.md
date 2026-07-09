# System Testing Plan

## Objective

Verify IDMS end-to-end functionality across registration, authentication, documents, voting, meetings, finance, notifications, activity summaries, imports, and defect tracking so defects can be found, documented, fixed, and verified.

## Scope

In scope:

- Member registration, verification, login, password policy, password reset, and profile updates.
- Admin member search, document category management, upload approval, document search, and downloads.
- Voting event creation, eligibility checks, vote casting, result reporting, and CSV export.
- WhatsApp import validation, parsing, storage, and analytics.
- Meeting scheduling, attendance recording, minutes storage/download, notifications, and attendance export.
- Financial transaction recording, report generation, budget monitoring, budget alerts, and CSV export.
- Activity summary widgets, reports, recent activities, and admin dashboard display.
- Bug reporting, defect status updates, and verified fix workflow.

Out of scope:

- External SMTP delivery beyond local notification state transitions.
- Browser-specific visual regression testing.
- Load, penetration, and long-running soak testing.

## Test Strategy

System tests are implemented as `unittest` suites using isolated temporary SQLite databases. Each test initializes schema with `database.init_db()`, seeds only the records needed for the workflow, and exercises Flask routes with `main.app.test_client()` where API or page behavior matters.

The suite combines:

- Happy-path workflow tests for successful module use.
- Validation tests for malformed input, duplicate prevention, and permission boundaries.
- Report/export tests for generated summaries and CSV output.
- Regression tests for defect workflow and fix verification.

## Test Case Matrix

| Area | Test Coverage | Test Files |
| --- | --- | --- |
| Authentication | Password policy, reset tokens, email verification, login security | `src/test_password_policy.py`, `src/test_password_reset.py` |
| Members/Admin | Member listing, search, role data, admin access | `src/test_admin_members.py` |
| Documents | Categories, search, notifications, secure downloads | `src/test_document_categories.py`, `src/test_document_search.py`, `src/test_document_notifications.py`, `src/test_document_downloads.py` |
| Imports | Mapping, validation, duplicate handling, rollback metadata | `src/test_import_validation.py` |
| Voting | Event validation, eligibility, duplicate vote prevention, results export | `src/test_vote_eligibility.py`, `src/test_voting_results.py`, `src/test_new_modules.py` |
| WhatsApp Analytics | Import parsing, malformed row handling, analytics aggregation | `src/test_whatsapp_import.py`, `src/test_new_modules.py` |
| Meetings | Scheduling conflicts, attendance, minutes, notifications | `src/test_meeting_scheduling.py`, `src/test_meeting_attendance.py`, `src/test_meeting_minutes_storage.py`, `src/test_meeting_notifications.py`, `src/test_new_modules.py` |
| Finance | Transactions, reports, budget monitoring, budget alerts, exports | `src/test_financial_transactions.py`, `src/test_new_modules.py` |
| Activity Summary | Data collection, summary reports, recent activity, dashboard widgets | `src/test_activity_summary.py` |
| Defects | Bug creation, validation, status workflow, verified fixes | `src/test_system_testing.py`, `src/test_new_modules.py` |

## Defect Workflow

1. Tester documents a defect from `/bugs` with severity, reproduction steps, expected behavior, and actual behavior.
2. Admin triages the issue and moves it through `Open`, `In Progress`, `Fixed`, and `Verified`.
3. Regression tests are added or updated before marking a fix verified.
4. Resolution notes describe the fix evidence.

## Execution Command

```powershell
python -m unittest discover -s src
```

## Acceptance Criteria

- Full `unittest` suite completes successfully.
- Bug workflow can document defects and verify fixes.
- Admin-only verification actions are blocked for regular members.
- System reports and exports return current generated data.
- No critical or high defects remain open after regression execution.

## Latest Execution

Date: 2026-07-08

Command:

```powershell
python -m unittest discover -s src
```

Result: Passed, 101 tests completed.

Defects found during this execution: None.
