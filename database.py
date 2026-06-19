import json
import sqlite3
import bcrypt

DB_NAME = "main_db.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row):
    return dict(row) if row else None


def table_exists(cursor, table_name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(row["name"] == column_name for row in cursor.fetchall())


def add_column_if_missing(cursor, table_name, column_name, definition):
    if not column_exists(cursor, table_name, column_name):
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    add_column_if_missing(cursor, "users_data", "full_name", "TEXT DEFAULT ''")
    add_column_if_missing(cursor, "users_data", "bio", "TEXT DEFAULT ''")
    add_column_if_missing(cursor, "users_data", "skills", "TEXT DEFAULT ''")
    add_column_if_missing(cursor, "users_data", "team_role", "TEXT DEFAULT 'Developer'")
    add_column_if_missing(cursor, "users_data", "profile_picture", "TEXT DEFAULT ''")
    add_column_if_missing(cursor, "users_data", "role", "TEXT DEFAULT 'Participant'")
    add_column_if_missing(cursor, "users_data", "updated_at", "DATETIME")
    add_column_if_missing(cursor, "users_data", "last_login_at", "DATETIME")
    add_column_if_missing(cursor, "users_data", "is_verified", "BOOLEAN DEFAULT 0")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            original_filename TEXT,
            stored_filename TEXT NOT NULL,
            mime_type TEXT,
            size INTEGER,
            sha256 TEXT,
            approved INTEGER DEFAULT 0,
            approved_by TEXT,
            approved_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_uploads_user ON uploads(user_id)")
    add_column_if_missing(cursor, "uploads", "approved", "INTEGER DEFAULT 0")
    add_column_if_missing(cursor, "uploads", "approved_by", "TEXT")
    add_column_if_missing(cursor, "uploads", "approved_at", "DATETIME")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_uploads_approved ON uploads(approved)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id INTEGER NOT NULL,
            user_id INTEGER,
            admin_username TEXT,
            ip_address TEXT,
            user_agent TEXT,
            downloaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(upload_id) REFERENCES uploads(id),
            FOREIGN KEY(user_id) REFERENCES users_data(id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_document_downloads_upload ON document_downloads(upload_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_document_downloads_user ON document_downloads(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_document_downloads_date ON document_downloads(downloaded_at)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users_data(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users_data(username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_created_at ON users_data(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_last_login_at ON users_data(last_login_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username_nocase ON users_data(username COLLATE NOCASE)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_full_name_nocase ON users_data(full_name COLLATE NOCASE)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users_data(role)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_team_role ON users_data(team_role)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_verified ON users_data(is_verified)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS import_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_username TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            target_table TEXT NOT NULL DEFAULT 'users_data',
            file_ext TEXT NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'uploaded',
            field_mapping TEXT DEFAULT '{}',
            duplicate_key TEXT DEFAULT 'email',
            conflict_strategy TEXT DEFAULT 'skip',
            summary TEXT DEFAULT '{}',
            error_message TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            merged_at DATETIME,
            rollback_until DATETIME,
            rolled_back_at DATETIME
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS import_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            row_number INTEGER NOT NULL,
            source_data TEXT NOT NULL,
            mapped_data TEXT DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            errors TEXT DEFAULT '[]',
            duplicate_key TEXT DEFAULT '',
            existing_record TEXT DEFAULT '{}',
            resolution TEXT DEFAULT '',
            FOREIGN KEY(job_id) REFERENCES import_jobs(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS import_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            table_name TEXT NOT NULL,
            record_pk TEXT NOT NULL,
            action TEXT NOT NULL,
            before_data TEXT DEFAULT '{}',
            after_data TEXT DEFAULT '{}',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            rolled_back_at DATETIME,
            FOREIGN KEY(job_id) REFERENCES import_jobs(id)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_import_jobs_created ON import_jobs(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_import_rows_job ON import_rows(job_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_import_changes_job ON import_changes(job_id)")

    conn.commit()
    conn.close()


def create_user(username, email, password):
    conn = get_connection()
    cursor = conn.cursor()

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    cursor.execute("""
        INSERT INTO users_data (username, email, password_hash, full_name, is_verified)
        VALUES (?, ?, ?, ?, 0)
    """, (username.strip(), email.strip().lower(), password_hash, username.strip()))

    conn.commit()
    conn.close()


def fetch_unique_email(email):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users_data WHERE lower(email) = lower(?)", (email.strip(),))
    email_record = cursor.fetchone()
    conn.close()
    return email_record is not None


def fetch_unique_username(username):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users_data WHERE lower(username) = lower(?)", (username.strip(),))
    username_record = cursor.fetchone()
    conn.close()
    return username_record is not None


def email_exists_for_other_user(email, user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM users_data WHERE lower(email) = lower(?) AND id != ?",
        (email.strip(), user_id),
    )
    record = cursor.fetchone()
    conn.close()
    return record is not None


def username_exists_for_other_user(username, user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM users_data WHERE lower(username) = lower(?) AND id != ?",
        (username.strip(), user_id),
    )
    record = cursor.fetchone()
    conn.close()
    return record is not None


def get_user_by_id(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users_data WHERE id = ?", (user_id,))
    user = row_to_dict(cursor.fetchone())
    conn.close()
    return user


def get_user_by_email(email):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users_data WHERE lower(email) = lower(?)", (email.strip(),))
    user = row_to_dict(cursor.fetchone())
    conn.close()
    return user


def mark_user_verified(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users_data SET is_verified = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()


def update_user_password(user_id, password):
    """Replace a user's password with a newly generated bcrypt hash."""
    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE users_data
        SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?""",
        (password_hash, user_id),
    )
    conn.commit()
    updated = cursor.rowcount == 1
    conn.close()
    return updated


def user_login(email, password):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users_data WHERE lower(email) = lower(?)", (email.strip(),))
    user_data = cursor.fetchone()

    if user_data is None:
        conn.close()
        return None

    stored_password_hash = user_data["password_hash"]
    password_is_valid = bcrypt.checkpw(
        password.encode("utf-8"),
        stored_password_hash.encode("utf-8"),
    )

    if not password_is_valid:
        conn.close()
        return None

    cursor.execute(
        "UPDATE users_data SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?",
        (user_data["id"],),
    )
    conn.commit()

    cursor.execute("SELECT * FROM users_data WHERE id = ?", (user_data["id"],))
    user = row_to_dict(cursor.fetchone())
    conn.close()
    return user


def update_user_profile(user_id, full_name, username, email, bio, skills, team_role, profile_picture):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users_data
        SET full_name = ?,
            username = ?,
            email = ?,
            bio = ?,
            skills = ?,
            team_role = ?,
            profile_picture = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (
        full_name.strip(),
        username.strip(),
        email.strip().lower(),
        bio.strip(),
        skills.strip(),
        team_role.strip(),
        profile_picture.strip(),
        user_id,
    ))
    conn.commit()
    conn.close()


def count_rows(cursor, table_name, where_clause="", params=()):
    if not table_exists(cursor, table_name):
        return 0

    query = f"SELECT COUNT(*) AS total FROM {table_name}"
    if where_clause:
        query += f" WHERE {where_clause}"

    cursor.execute(query, params)
    return cursor.fetchone()["total"]


def get_dashboard_stats(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    stats = {
        "teams_joined": count_rows(cursor, "team_members", "user_id = ?", (user_id,)),
        "games_submitted": 0,
        "votes_cast": count_rows(cursor, "votes", "user_id = ?", (user_id,)),
        "upcoming_events": 0,
    }

    if table_exists(cursor, "submissions"):
        if column_exists(cursor, "submissions", "user_id"):
            stats["games_submitted"] = count_rows(cursor, "submissions", "user_id = ?", (user_id,))
        elif table_exists(cursor, "team_members") and column_exists(cursor, "submissions", "team_id"):
            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM submissions
                WHERE team_id IN (
                    SELECT team_id FROM team_members WHERE user_id = ?
                )
            """, (user_id,))
            stats["games_submitted"] = cursor.fetchone()["total"]

    if table_exists(cursor, "events"):
        stats["upcoming_events"] = count_rows(cursor, "events", "date >= CURRENT_TIMESTAMP")

    conn.close()
    return stats


def get_member_statistics():
    conn = get_connection()
    cursor = conn.cursor()

    stats = {
        "total_members": count_rows(cursor, "users_data"),
        "new_members_this_month": 0,
        "active_members": 0,
    }

    if table_exists(cursor, "users_data"):
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM users_data
            WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        """)
        stats["new_members_this_month"] = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM users_data
            WHERE last_login_at IS NOT NULL
              AND last_login_at >= datetime('now', '-30 days')
        """)
        stats["active_members"] = cursor.fetchone()["total"]

    conn.close()
    return stats


def get_member_growth_history(limit=30):
    conn = get_connection()
    cursor = conn.cursor()

    if not table_exists(cursor, "users_data"):
        conn.close()
        return []

    cursor.execute("""
        WITH daily_signups AS (
            SELECT date(created_at) AS signup_date, COUNT(*) AS members_added
            FROM users_data
            GROUP BY date(created_at)
            ORDER BY signup_date DESC
            LIMIT ?
        ),
        ordered_signups AS (
            SELECT signup_date, members_added
            FROM daily_signups
            ORDER BY signup_date ASC
        )
        SELECT
            signup_date AS date,
            (
                SELECT COUNT(*)
                FROM users_data
                WHERE date(created_at) <= ordered_signups.signup_date
            ) AS total_members
        FROM ordered_signups
    """, (limit,))

    rows = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_recent_activity(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    activities = []

    user = get_user_by_id(user_id)
    if user and user.get("last_login_at"):
        activities.append({
            "label": "Recent login",
            "detail": "You signed in to PixelHack.",
            "time": user["last_login_at"],
        })

    if user and user.get("updated_at"):
        activities.append({
            "label": "Profile updated",
            "detail": "Your public profile details were saved.",
            "time": user["updated_at"],
        })

    if table_exists(cursor, "events"):
        cursor.execute("""
            SELECT title, date
            FROM events
            WHERE date >= CURRENT_TIMESTAMP
            ORDER BY date ASC
            LIMIT 2
        """)
        for event in cursor.fetchall():
            activities.append({
                "label": "Upcoming event",
                "detail": event["title"],
                "time": event["date"],
            })

    if not activities:
        activities.append({
            "label": "Welcome",
            "detail": "Your PixelHack dashboard is ready.",
            "time": "Today",
        })

    conn.close()
    return activities[:5]


def update_user_data(verified_email, first_name, last_name, email, password_hash, phone, member_type=None, address=None):
    conn = get_connection()
    cursor = conn.cursor()
    full_name = f"{first_name} {last_name}".strip()
    cursor.execute("""
        UPDATE users_data
        SET full_name = ?, email = ?, updated_at = CURRENT_TIMESTAMP
        WHERE email = ?
    """, (full_name, email, verified_email))
    conn.commit()
    conn.close()


def save_upload_metadata(user_id, original_filename, stored_filename, mime_type, size, sha256, approved=0, approved_by=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO uploads (user_id, original_filename, stored_filename, mime_type, size, sha256, approved, approved_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, original_filename, stored_filename, mime_type, size, sha256, int(approved), approved_by))
    conn.commit()
    conn.close()


def get_uploads_for_user(user_id, limit=50):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM uploads WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


def get_approved_uploads(limit=100):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM uploads WHERE approved = 1 ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


def get_upload_by_id(upload_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM uploads WHERE id = ?", (upload_id,))
    row = cursor.fetchone()
    conn.close()
    return row_to_dict(row)


def log_document_download(upload_id, user_id=None, admin_username=None, ip_address="", user_agent=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO document_downloads (
            upload_id, user_id, admin_username, ip_address, user_agent
        )
        VALUES (?, ?, ?, ?, ?)
    """, (upload_id, user_id, admin_username, ip_address, user_agent))
    download_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return download_id


def get_table_schema(table_name):
    conn = get_connection()
    cursor = conn.cursor()
    if not table_exists(cursor, table_name):
        conn.close()
        return []

    cursor.execute(f"PRAGMA table_info({table_name})")
    rows = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_import_dashboard_stats():
    conn = get_connection()
    cursor = conn.cursor()
    stats = {
        "total_records": count_rows(cursor, "users_data"),
        "last_import_date": None,
        "pending_validations": 0,
        "duplicate_alerts": 0,
    }

    if table_exists(cursor, "import_jobs"):
        cursor.execute("""
            SELECT merged_at
            FROM import_jobs
            WHERE merged_at IS NOT NULL
            ORDER BY merged_at DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        stats["last_import_date"] = row["merged_at"] if row else None

    if table_exists(cursor, "import_rows"):
        stats["pending_validations"] = count_rows(cursor, "import_rows", "status = 'invalid'")
        stats["duplicate_alerts"] = count_rows(cursor, "import_rows", "status IN ('duplicate', 'conflict')")

    conn.close()
    return stats


def search_members(query="", role="", team_role="", verified="", limit=25, offset=0):
    """Search imported/registered members with filters and bounded pagination."""
    conn = get_connection()
    cursor = conn.cursor()
    query = (query or "").strip()
    role = (role or "").strip()
    team_role = (team_role or "").strip()
    verified = (verified or "").strip().lower()
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    clauses = []
    params = []

    if query:
        value = f"%{query}%"
        text_search = """(
            username LIKE ? COLLATE NOCASE
            OR email LIKE ? COLLATE NOCASE
            OR COALESCE(full_name, '') LIKE ? COLLATE NOCASE
        )"""
        if query.isdigit():
            clauses.append(f"(id = ? OR {text_search})")
            params.append(int(query))
        else:
            clauses.append(text_search)
        params.extend([value] * 3)

    if role:
        clauses.append("role = ? COLLATE NOCASE")
        params.append(role)
    if team_role:
        clauses.append("team_role = ? COLLATE NOCASE")
        params.append(team_role)
    if verified in {"verified", "pending"}:
        clauses.append("is_verified = ?")
        params.append(1 if verified == "verified" else 0)

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cursor.execute(f"SELECT COUNT(*) AS total FROM users_data {where_clause}", params)
    total = cursor.fetchone()["total"]

    cursor.execute(
        f"""
        SELECT id, username, email, full_name, role, team_role,
               is_verified, created_at, last_login_at
        FROM users_data
        {where_clause}
        ORDER BY lower(COALESCE(NULLIF(full_name, ''), username)), id
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    )
    members = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"members": members, "total": total, "limit": limit, "offset": offset}


def get_member_filter_options():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT role FROM users_data WHERE role IS NOT NULL AND role != '' ORDER BY role")
    roles = [row["role"] for row in cursor.fetchall()]
    cursor.execute("SELECT DISTINCT team_role FROM users_data WHERE team_role IS NOT NULL AND team_role != '' ORDER BY team_role")
    team_roles = [row["team_role"] for row in cursor.fetchall()]
    conn.close()
    return {"roles": roles, "team_roles": team_roles}


def create_import_job(admin_username, original_filename, stored_filename, target_table, file_ext, file_size):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO import_jobs (
            admin_username, original_filename, stored_filename, target_table, file_ext, file_size
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (admin_username, original_filename, stored_filename, target_table, file_ext, file_size))
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return job_id


def get_import_job(job_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM import_jobs WHERE id = ?", (job_id,))
    row = row_to_dict(cursor.fetchone())
    conn.close()
    return row


def update_import_job(job_id, **fields):
    allowed = {
        "status", "field_mapping", "duplicate_key", "conflict_strategy",
        "summary", "error_message", "merged_at", "rollback_until",
        "rolled_back_at",
    }
    updates = []
    values = []
    for key, value in fields.items():
        if key in allowed:
            updates.append(f"{key} = ?")
            values.append(value)

    if not updates:
        return

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(job_id)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE import_jobs SET {', '.join(updates)} WHERE id = ?", values)
    conn.commit()
    conn.close()


def replace_import_rows(job_id, rows):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM import_rows WHERE job_id = ?", (job_id,))
    cursor.executemany("""
        INSERT INTO import_rows (
            job_id, row_number, source_data, mapped_data, status, errors,
            duplicate_key, existing_record, resolution
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (
            job_id,
            row["row_number"],
            json.dumps(row.get("source_data", {}), default=str),
            json.dumps(row.get("mapped_data", {}), default=str),
            row.get("status", "pending"),
            json.dumps(row.get("errors", []), default=str),
            row.get("duplicate_key", ""),
            json.dumps(row.get("existing_record", {}), default=str),
            row.get("resolution", ""),
        )
        for row in rows
    ])
    conn.commit()
    conn.close()


def get_import_rows(job_id, statuses=None, limit=None):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM import_rows WHERE job_id = ?"
    params = [job_id]
    if statuses:
        placeholders = ",".join(["?"] * len(statuses))
        query += f" AND status IN ({placeholders})"
        params.extend(statuses)
    query += " ORDER BY row_number ASC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    cursor.execute(query, params)
    rows = []
    for row in cursor.fetchall():
        item = row_to_dict(row)
        item["source_data"] = json.loads(item.get("source_data") or "{}")
        item["mapped_data"] = json.loads(item.get("mapped_data") or "{}")
        item["errors"] = json.loads(item.get("errors") or "[]")
        item["existing_record"] = json.loads(item.get("existing_record") or "{}")
        rows.append(item)
    conn.close()
    return rows


def get_import_row(row_id, job_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM import_rows WHERE id = ? AND job_id = ?",
        (row_id, job_id),
    )
    item = row_to_dict(cursor.fetchone())
    conn.close()
    if not item:
        return None
    item["source_data"] = json.loads(item.get("source_data") or "{}")
    item["mapped_data"] = json.loads(item.get("mapped_data") or "{}")
    item["errors"] = json.loads(item.get("errors") or "[]")
    item["existing_record"] = json.loads(item.get("existing_record") or "{}")
    return item


def update_import_row(row_id, job_id, mapped_data, status, errors, duplicate_key, existing_record):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE import_rows
        SET mapped_data = ?, status = ?, errors = ?, duplicate_key = ?,
            existing_record = ?, resolution = ''
        WHERE id = ? AND job_id = ?
    """, (
        json.dumps(mapped_data, default=str),
        status,
        json.dumps(errors, default=str),
        duplicate_key,
        json.dumps(existing_record, default=str),
        row_id,
        job_id,
    ))
    updated = cursor.rowcount == 1
    conn.commit()
    conn.close()
    return updated


def get_import_history(limit=50):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM import_jobs
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    rows = []
    for row in cursor.fetchall():
        item = row_to_dict(row)
        item["summary"] = json.loads(item.get("summary") or "{}")
        item["field_mapping"] = json.loads(item.get("field_mapping") or "{}")
        rows.append(item)
    conn.close()
    return rows
