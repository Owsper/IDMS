# Import Members

Admins can import legacy member records from a CSV file at:

```text
/admin/import-members
```

The page processes the file first, shows a preview, lists invalid or skipped rows, and only imports valid rows after the admin clicks **Confirm Import**.

## Supported CSV Columns

- `first_name`
- `last_name`
- `username`
- `email`
- `phone`
- `role`
- `member_type`
- `team_name`

The import writes into the existing `users_data` table. `first_name` and `last_name` become `full_name`. `member_type`, `team_name`, or `role` are mapped to `team_role` where possible. Phone and team details are stored in `bio`.

## Cleaning Rules

- Trim spaces from all text fields.
- Convert email addresses to lowercase.
- Validate email format.
- Standardize phone numbers to digits, preserving a leading `+`.
- Generate a username from the CSV username, email prefix, or name.
- Use `Participant` as the safe default app role.
- Generate and hash a temporary password with bcrypt.
- Never store plain text passwords.

## Duplicate Handling

- Email is the main unique identifier.
- If the same email appears more than once in the uploaded file, only the first valid row is kept.
- If an email already exists in `users_data`, the row is skipped.
- Existing member records are not updated by this simple import flow.

## Import Logs

Preview and final import results are stored in:

- `member_import_batches`
- `member_import_errors`

These tables are created automatically by `database.init_db()`.
