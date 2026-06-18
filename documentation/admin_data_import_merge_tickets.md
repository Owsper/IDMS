# Admin Data Import & Merge Module Tickets

Suggested stack: Flask, SQLite, Jinja templates, vanilla JavaScript, `openpyxl` for XLSX parsing, CSV/JSON/SQLite stdlib parsers. Future production scale can add Celery/RQ for background batch jobs and object storage for uploaded sources.

## Ticket 1: Admin-Only Access Control
Story points: 3

Acceptance criteria:
- Import Data navigation is visible only to users with the Admin role.
- `/admin/import-data` and every `/api/admin/import/*` endpoint require authenticated admin access.
- Non-admin direct requests receive `403`.
- The backend guard is shared with existing admin dashboard APIs.

## Ticket 2: Database File Upload & Preview
Story points: 5

Acceptance criteria:
- Admin can upload `.csv`, `.xlsx`, `.json`, `.sql`, `.db`, and `.sqlite` files.
- Unsupported formats and files over the configured size limit are rejected before processing.
- Server stores imported files in a private upload directory with randomized filenames.
- API returns source headers, target schema, suggested mapping, duplicate key options, row count, and the first 20 preview rows.

## Ticket 3: Field Mapping UI
Story points: 5

Acceptance criteria:
- Admin can map uploaded columns to editable target schema fields.
- Exact-name mappings are preselected when possible.
- Admin can exclude source columns from import.
- Mapping is persisted with the import job for audit purposes.

## Ticket 4: Validation Report
Story points: 8

Acceptance criteria:
- Imported rows are validated against required fields, target data types, and email format constraints.
- Duplicate and conflict rows are detected before merge using `id`, `email`, or `username`.
- Invalid rows are persisted with row-level errors and excluded from merge.
- Validation summary includes total, valid, invalid, duplicate, and conflict counts.

## Ticket 5: Merge Execution & Conflict Resolution
Story points: 8

Acceptance criteria:
- Merge runs inside a transaction.
- New records are inserted.
- Existing records can be skipped or overwritten.
- Manual mode leaves unresolved conflicts out of the merge summary until explicit per-row choices are supplied.
- Failed merges roll back all partial changes and mark the import job as failed.

## Ticket 6: Import History & Audit Trail
Story points: 5

Acceptance criteria:
- Every import job records admin username, file name, target table, file size, status, mapping, strategy, summary, and timestamps.
- Every inserted or updated record creates an `import_changes` audit row.
- Admin dashboard can retrieve import history and aggregate import widget stats.

## Ticket 7: Rollback Window
Story points: 5

Acceptance criteria:
- Successful imports include a configurable rollback deadline.
- Admin can roll back a merged import before the deadline.
- Inserted rows are deleted and updated rows are restored from the stored before snapshot.
- Rollback action is logged and cannot be repeated.

## Ticket 8: Admin Dashboard UI
Story points: 5

Acceptance criteria:
- Admin dashboard displays Total Records, Last Import Date, Pending Validations, and Duplicate Alerts.
- Import Data page includes upload area, preview table, mapping controls, merge options, progress indicator, validation report, summary report, history, and rollback action.
- Non-admin users see Documents instead of Import Data navigation.

## Ticket 9: Large File Processing Hardening
Story points: 8

Acceptance criteria:
- Parser and validator process files in configurable chunks.
- Long-running merge jobs can be moved to a background worker.
- UI can poll job progress and display batch-level status.
- Batch failures preserve enough state to retry or roll back safely.

## Ticket 10: Referential Integrity Expansion
Story points: 8

Acceptance criteria:
- Target tables expose declared foreign keys through schema metadata.
- Validation checks foreign key values before insert/update.
- Admin receives row-level relationship errors.
- Multi-table imports can be sequenced safely once additional target schemas are enabled.
