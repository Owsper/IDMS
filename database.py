import json
import re
import sqlite3
import bcrypt
from datetime import timedelta

DB_NAME = "main_db.db"
DEFAULT_DOCUMENT_CATEGORIES = (
    ("General", "General organization documents"),
    ("Policies", "Policies, rules, and governance documents"),
    ("Guides", "Guides, manuals, and instructional resources"),
    ("Forms", "Forms and reusable templates"),
    ("Reports", "Reports, summaries, and analysis"),
)


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
        CREATE TABLE IF NOT EXISTS document_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            is_system INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    add_column_if_missing(cursor, "document_categories", "is_system", "INTEGER NOT NULL DEFAULT 0")
    cursor.executemany("""
        INSERT OR IGNORE INTO document_categories (name, description, is_system)
        VALUES (?, ?, 1)
    """, DEFAULT_DOCUMENT_CATEGORIES)
    cursor.executemany(
        "UPDATE document_categories SET is_system = 1 WHERE name = ? COLLATE NOCASE",
        [(name,) for name, _ in DEFAULT_DOCUMENT_CATEGORIES],
    )
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_document_categories_active_name
        ON document_categories(is_active, name COLLATE NOCASE)
    """)

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
            category TEXT NOT NULL DEFAULT 'General',
            category_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(category_id) REFERENCES document_categories(id)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_uploads_user ON uploads(user_id)")
    add_column_if_missing(cursor, "uploads", "approved", "INTEGER DEFAULT 0")
    add_column_if_missing(cursor, "uploads", "approved_by", "TEXT")
    add_column_if_missing(cursor, "uploads", "approved_at", "DATETIME")
    add_column_if_missing(cursor, "uploads", "category", "TEXT NOT NULL DEFAULT 'General'")
    add_column_if_missing(cursor, "uploads", "category_id", "INTEGER")
    cursor.execute("""
        UPDATE uploads
        SET category_id = COALESCE(
            (SELECT id FROM document_categories
             WHERE name = uploads.category COLLATE NOCASE),
            (SELECT id FROM document_categories WHERE name = 'General')
        )
        WHERE category_id IS NULL
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_uploads_approved ON uploads(approved)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_uploads_category_id ON uploads(category_id)")
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_uploads_approved_category_id_title
        ON uploads(approved, category_id, lower(original_filename), id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_uploads_approved_title
        ON uploads(approved, lower(original_filename), id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_uploads_approved_category_title
        ON uploads(approved, category COLLATE NOCASE, lower(original_filename), id)
    """)

    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS document_title_search USING fts5(
            original_filename,
            content='uploads',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        )
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS uploads_title_search_insert
        AFTER INSERT ON uploads BEGIN
            INSERT INTO document_title_search(rowid, original_filename)
            VALUES (new.id, new.original_filename);
        END
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS uploads_title_search_delete
        AFTER DELETE ON uploads BEGIN
            INSERT INTO document_title_search(document_title_search, rowid, original_filename)
            VALUES ('delete', old.id, old.original_filename);
        END
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS uploads_title_search_update
        AFTER UPDATE OF original_filename ON uploads BEGIN
            INSERT INTO document_title_search(document_title_search, rowid, original_filename)
            VALUES ('delete', old.id, old.original_filename);
            INSERT INTO document_title_search(rowid, original_filename)
            VALUES (new.id, new.original_filename);
        END
    """)
    cursor.execute("INSERT INTO document_title_search(document_title_search) VALUES ('rebuild')")

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

    if table_exists(cursor, "auth_magic_links") and not table_exists(cursor, "auth_email_links"):
        cursor.execute("ALTER TABLE auth_magic_links RENAME TO auth_email_links")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auth_email_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purpose TEXT NOT NULL CHECK(purpose IN ('registration_verification', 'password_reset')),
            email TEXT NOT NULL,
            user_id INTEGER,
            link TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'email_created',
            error_message TEXT NOT NULL DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            delivered_at DATETIME,
            used_at DATETIME,
            FOREIGN KEY(user_id) REFERENCES users_data(id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_auth_email_links_status ON auth_email_links(status, created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_auth_email_links_email ON auth_email_links(email)")

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            actor_id INTEGER,
            actor_name TEXT NOT NULL DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_log_created ON activity_log(created_at)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voting_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            start_at DATETIME NOT NULL,
            end_at DATETIME NOT NULL,
            eligibility_status TEXT NOT NULL DEFAULT 'verified',
            min_membership_days INTEGER NOT NULL DEFAULT 0,
            allowed_roles TEXT NOT NULL DEFAULT '[]',
            created_by TEXT NOT NULL DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voting_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(event_id) REFERENCES voting_events(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            option_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            vote_hash TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(event_id, user_id),
            FOREIGN KEY(event_id) REFERENCES voting_events(id),
            FOREIGN KEY(option_id) REFERENCES voting_options(id),
            FOREIGN KEY(user_id) REFERENCES users_data(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eligibility_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            user_id INTEGER,
            eligible INTEGER NOT NULL,
            reason TEXT NOT NULL,
            checked_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            sent_at DATETIME NOT NULL,
            message TEXT NOT NULL,
            media_type TEXT NOT NULL DEFAULT 'text',
            source_filename TEXT NOT NULL DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_sent ON whatsapp_messages(sent_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_sender ON whatsapp_messages(sender)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_source ON whatsapp_messages(source_filename)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            recipient_id INTEGER,
            channel TEXT NOT NULL DEFAULT 'in-app',
            status TEXT NOT NULL DEFAULT 'sent',
            read_at DATETIME,
            scheduled_for DATETIME,
            sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            meeting_at DATETIME NOT NULL,
            location TEXT NOT NULL DEFAULT '',
            agenda TEXT NOT NULL DEFAULT '',
            invitees TEXT NOT NULL DEFAULT '[]',
            meeting_type TEXT NOT NULL DEFAULT 'general',
            status TEXT NOT NULL DEFAULT 'upcoming',
            created_by TEXT NOT NULL DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_meetings_at ON meetings(meeting_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_meetings_type ON meetings(meeting_type)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meeting_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('present', 'absent', 'excused')),
            recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(meeting_id, member_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meeting_minutes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            filename TEXT NOT NULL DEFAULT '',
            uploaded_by TEXT NOT NULL DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financial_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_date DATE NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
            category TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            description TEXT NOT NULL DEFAULT '',
            recorded_by TEXT NOT NULL DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            allocated_amount REAL NOT NULL CHECK(allocated_amount > 0),
            fiscal_period TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(category, fiscal_period)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bug_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            severity TEXT NOT NULL CHECK(severity IN ('Critical', 'High', 'Medium', 'Low')),
            steps TEXT NOT NULL,
            expected TEXT NOT NULL,
            actual TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Open',
            reporter TEXT NOT NULL DEFAULT '',
            resolution_notes TEXT NOT NULL DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

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


def create_auth_email_link(purpose, email, link, user_id=None, status="email_created", error_message=""):
    if purpose not in {"registration_verification", "password_reset"}:
        raise ValueError("Unsupported email link purpose.")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO auth_email_links (
            purpose, email, user_id, link, status, error_message, delivered_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        purpose,
        email.strip().lower(),
        user_id,
        link,
        status,
        error_message[:500],
    ))
    link_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return link_id


def list_auth_email_links(status=None, limit=100):
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT l.*, u.username, u.full_name
        FROM auth_email_links AS l
        LEFT JOIN users_data AS u ON u.id = l.user_id
    """
    params = []
    if status:
        query += " WHERE l.status = ?"
        params.append(status)
    query += " ORDER BY l.created_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 250)))
    cursor.execute(query, params)
    rows = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_active_auth_email_link(purpose, link, user_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT *
        FROM auth_email_links
        WHERE purpose = ? AND link = ? AND status = 'email_sent'
    """
    params = [purpose, link]
    if user_id is not None:
        query += " AND user_id = ?"
        params.append(user_id)
    query += " ORDER BY created_at DESC LIMIT 1"
    cursor.execute(query, params)
    row = row_to_dict(cursor.fetchone())
    conn.close()
    return row


def mark_auth_email_link_used(link):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE auth_email_links
        SET status = 'used', used_at = CURRENT_TIMESTAMP
        WHERE link = ? AND status != 'used'
    """, (link,))
    conn.commit()
    conn.close()


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


def save_upload_metadata(
    user_id, original_filename, stored_filename, mime_type, size, sha256,
    approved=0, approved_by=None, category="General"
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name FROM document_categories WHERE name = ? COLLATE NOCASE AND is_active = 1",
        (category,),
    )
    category_row = cursor.fetchone()
    if not category_row:
        conn.close()
        raise ValueError("Select an active document category.")
    cursor.execute("""
        INSERT INTO uploads (
            user_id, original_filename, stored_filename, mime_type, size, sha256,
            approved, approved_by, category, category_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, original_filename, stored_filename, mime_type, size, sha256,
        int(approved), approved_by, category_row["name"], category_row["id"]
    ))
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


def get_document_categories(include_inactive=False):
    conn = get_connection()
    cursor = conn.cursor()
    where_clause = "" if include_inactive else "WHERE c.is_active = 1"
    cursor.execute(f"""
        SELECT c.id, c.name, c.description, c.is_active, c.is_system,
               c.created_at, c.updated_at, COUNT(u.id) AS document_count
        FROM document_categories AS c
        LEFT JOIN uploads AS u ON u.category_id = c.id
        {where_clause}
        GROUP BY c.id
        ORDER BY c.is_active DESC, lower(c.name), c.id
    """)
    categories = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return categories


def create_document_category(name, description=""):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO document_categories (name, description)
            VALUES (?, ?)
        """, (name, description))
        category_id = cursor.lastrowid
        conn.commit()
        return category_id
    finally:
        conn.close()


def update_document_category(category_id, name, description="", is_active=True):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM document_categories WHERE id = ?", (category_id,))
        category = row_to_dict(cursor.fetchone())
        if not category:
            raise ValueError("Category not found.")

        cursor.execute("SELECT COUNT(*) AS total FROM uploads WHERE category_id = ?", (category_id,))
        document_count = cursor.fetchone()["total"]
        if not is_active and (document_count > 0 or category["name"].lower() == "general"):
            raise ValueError("Categories in use and the General category must remain active.")
        if category["is_system"] and name.lower() != category["name"].lower():
            raise ValueError("Built-in category names cannot be changed.")

        cursor.execute("""
            UPDATE document_categories
            SET name = ?, description = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (name, description, int(is_active), category_id))
        cursor.execute(
            "UPDATE uploads SET category = ? WHERE category_id = ?",
            (name, category_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_documents_for_categorization(limit=200):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.original_filename, u.category_id, u.category,
               u.approved, u.created_at, c.name AS category_name
        FROM uploads AS u
        LEFT JOIN document_categories AS c ON c.id = u.category_id
        ORDER BY u.created_at DESC, u.id DESC
        LIMIT ?
    """, (max(1, min(int(limit), 500)),))
    documents = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return documents


def assign_document_category(upload_id, category_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, original_filename FROM uploads WHERE id = ?", (upload_id,))
        document = row_to_dict(cursor.fetchone())
        if not document:
            raise ValueError("Document not found.")
        cursor.execute(
            "SELECT id, name FROM document_categories WHERE id = ? AND is_active = 1",
            (category_id,),
        )
        category = row_to_dict(cursor.fetchone())
        if not category:
            raise ValueError("Select an active document category.")

        cursor.execute("""
            UPDATE uploads
            SET category_id = ?, category = ?
            WHERE id = ?
        """, (category["id"], category["name"], document["id"]))
        conn.commit()
        return {"document": document, "category": category}
    finally:
        conn.close()


def search_approved_documents(query="", category="", limit=25, offset=0):
    conn = get_connection()
    cursor = conn.cursor()
    query = (query or "").strip()
    category = (category or "").strip()
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    clauses = ["u.approved = 1"]
    params = []
    from_clause = "uploads AS u LEFT JOIN document_categories AS c ON c.id = u.category_id"
    order_clause = "lower(COALESCE(u.original_filename, '')), u.id"

    if query:
        tokens = re.findall(r"\w+", query, flags=re.UNICODE)
        if tokens:
            fts_query = " AND ".join(f'"{token}"*' for token in tokens)
            from_clause += " JOIN document_title_search ON document_title_search.rowid = u.id"
            clauses.append("document_title_search MATCH ?")
            params.append(fts_query)
            order_clause = "bm25(document_title_search), lower(COALESCE(u.original_filename, '')), u.id"
        else:
            clauses.append("instr(COALESCE(u.original_filename, ''), ?) > 0")
            params.append(query)
    if category:
        clauses.append("""u.category_id = (
            SELECT id FROM document_categories
            WHERE name = ? COLLATE NOCASE AND is_active = 1
        )""")
        params.append(category)

    where_clause = f"WHERE {' AND '.join(clauses)}"
    cursor.execute(f"SELECT COUNT(*) AS total FROM {from_clause} {where_clause}", params)
    total = cursor.fetchone()["total"]
    cursor.execute(
        f"""
        SELECT u.id, u.original_filename, u.category_id,
               COALESCE(c.name, u.category) AS category,
               u.mime_type, u.size, u.created_at, u.approved_at
        FROM {from_clause}
        {where_clause}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    )
    documents = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"documents": documents, "total": total, "limit": limit, "offset": offset}


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


def log_activity(module, action, detail="", actor_id=None, actor_name=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO activity_log (module, action, detail, actor_id, actor_name)
        VALUES (?, ?, ?, ?, ?)
    """, (module, action, detail, actor_id, actor_name))
    activity_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return activity_id


def create_notification(category, title, body, recipient_id=None, channel="in-app", scheduled_for=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notifications (category, title, body, recipient_id, channel, scheduled_for)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (category, title, body, recipient_id, channel, scheduled_for))
    notification_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return notification_id


def _json_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


ELIGIBILITY_STATUSES = {"verified", "any"}


def normalize_voting_eligibility(eligibility):
    eligibility = eligibility or {}
    membership_status = (eligibility.get("membership_status") or "verified").strip().lower()
    if membership_status not in ELIGIBILITY_STATUSES:
        raise ValueError("Membership status rule must be verified or any.")

    try:
        min_membership_days = int(eligibility.get("min_membership_days") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Minimum membership days must be a number.") from exc
    if min_membership_days < 0:
        raise ValueError("Minimum membership days cannot be negative.")

    allowed_roles = eligibility.get("allowed_roles") or []
    if isinstance(allowed_roles, str):
        allowed_roles = allowed_roles.split(",")
    if not isinstance(allowed_roles, (list, tuple)):
        raise ValueError("Allowed roles must be a list or comma-separated string.")
    allowed_roles = [str(role).strip() for role in allowed_roles if str(role).strip()]

    return {
        "membership_status": membership_status,
        "min_membership_days": min_membership_days,
        "allowed_roles": allowed_roles,
    }


def get_eligibility_audit(limit=100):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM eligibility_audit
        ORDER BY checked_at DESC, id DESC
        LIMIT ?
    """, (limit,))
    rows = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def create_voting_event(title, description, option_labels, start_at, end_at, created_by="", eligibility=None):
    title = (title or "").strip()
    option_labels = [label.strip() for label in option_labels if label and label.strip()]
    if not title:
        raise ValueError("Voting event title is required.")
    if len(option_labels) < 2:
        raise ValueError("Add at least two candidates or options.")
    if start_at <= datetime_now():
        raise ValueError("Voting start date must be in the future.")
    if end_at <= start_at:
        raise ValueError("Voting end date must be after the start date.")
    eligibility = normalize_voting_eligibility(eligibility)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO voting_events (
            title, description, start_at, end_at, eligibility_status,
            min_membership_days, allowed_roles, created_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        title,
        (description or "").strip(),
        start_at.isoformat(timespec="seconds"),
        end_at.isoformat(timespec="seconds"),
        eligibility["membership_status"],
        eligibility["min_membership_days"],
        json.dumps(eligibility["allowed_roles"]),
        created_by,
    ))
    event_id = cursor.lastrowid
    cursor.executemany("""
        INSERT INTO voting_options (event_id, label, position)
        VALUES (?, ?, ?)
    """, [(event_id, label, index) for index, label in enumerate(option_labels)])
    conn.commit()
    conn.close()
    log_activity("Voting", "Event created", title, actor_name=created_by)
    create_notification("voting", f"Voting opened: {title}", "A voting event has been scheduled.")
    return event_id


def datetime_now():
    from datetime import datetime
    return datetime.utcnow().replace(microsecond=0)


def parse_db_datetime(value):
    from datetime import datetime
    return datetime.fromisoformat(str(value).replace("Z", "+00:00").replace(" ", "T")).replace(tzinfo=None)


def list_voting_events(include_closed=True, user_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    where = "" if include_closed else "WHERE datetime(e.start_at) <= CURRENT_TIMESTAMP AND datetime(e.end_at) > CURRENT_TIMESTAMP"
    cursor.execute(f"""
        SELECT e.*,
               COUNT(DISTINCT o.id) AS option_count,
               COUNT(DISTINCT v.id) AS vote_count,
               MAX(CASE WHEN v.user_id = ? THEN 1 ELSE 0 END) AS user_voted
        FROM voting_events e
        LEFT JOIN voting_options o ON o.event_id = e.id
        LEFT JOIN votes v ON v.event_id = e.id
        {where}
        GROUP BY e.id
        ORDER BY e.start_at DESC
    """, (user_id or -1,))
    events = [row_to_dict(row) for row in cursor.fetchall()]
    for event in events:
        cursor.execute("SELECT id, label FROM voting_options WHERE event_id = ? ORDER BY position, id", (event["id"],))
        event["options"] = [row_to_dict(row) for row in cursor.fetchall()]
        event["allowed_roles"] = _json_list(event.get("allowed_roles"))
    conn.close()
    return events


def verify_vote_eligibility(event_id, user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM voting_events WHERE id = ?", (event_id,))
    event = row_to_dict(cursor.fetchone())
    user = None
    if user_id is not None:
        cursor.execute("SELECT * FROM users_data WHERE id = ?", (user_id,))
        user = row_to_dict(cursor.fetchone())
    eligible = True
    reason = "Eligible"
    rule = {}
    if not event:
        eligible, reason = False, "Voting event not found."
    elif not user:
        eligible, reason = False, "Member not found."
    else:
        now = datetime_now()
        rule = {
            "membership_status": event["eligibility_status"],
            "min_membership_days": int(event.get("min_membership_days") or 0),
            "allowed_roles": _json_list(event.get("allowed_roles")),
        }
        if now < parse_db_datetime(event["start_at"]) or now >= parse_db_datetime(event["end_at"]):
            eligible, reason = False, "Voting is not active for this event."
        elif event["eligibility_status"] == "verified" and int(user.get("is_verified", 0)) != 1:
            eligible, reason = False, "Only verified members can vote in this event."
        else:
            roles = rule["allowed_roles"]
            if roles and user.get("role") not in roles and user.get("team_role") not in roles:
                eligible, reason = False, "Your role is not eligible for this vote."
            min_days = rule["min_membership_days"]
            if eligible and min_days:
                created = parse_db_datetime(user["created_at"])
                if created > now - timedelta(days=min_days):
                    eligible, reason = False, f"Membership must be at least {min_days} days old."
    cursor.execute("""
        INSERT INTO eligibility_audit (event_id, user_id, eligible, reason)
        VALUES (?, ?, ?, ?)
    """, (event_id, user_id, int(eligible), reason))
    conn.commit()
    conn.close()
    return {
        "eligible": eligible,
        "reason": reason,
        "event_id": event_id,
        "user_id": user_id,
        "rule": rule,
    }


def log_vote_eligibility_denial(event_id, user_id, reason):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO eligibility_audit (event_id, user_id, eligible, reason)
        VALUES (?, ?, 0, ?)
    """, (event_id, user_id, reason))
    conn.commit()
    conn.close()


def cast_vote(event_id, option_id, user_id, secret=""):
    eligibility = verify_vote_eligibility(event_id, user_id)
    if not eligibility["eligible"]:
        raise ValueError(eligibility["reason"])
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM voting_options WHERE id = ? AND event_id = ?", (option_id, event_id))
    if not cursor.fetchone():
        conn.close()
        log_vote_eligibility_denial(event_id, user_id, "Selected option is not valid for this event.")
        raise ValueError("Select a valid voting option.")
    vote_hash = bcrypt.hashpw(f"{event_id}:{option_id}:{user_id}:{secret}".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    try:
        cursor.execute("""
            INSERT INTO votes (event_id, option_id, user_id, vote_hash)
            VALUES (?, ?, ?, ?)
        """, (event_id, option_id, user_id, vote_hash))
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.close()
        raise ValueError("You have already voted in this event.") from exc
    conn.close()
    log_activity("Voting", "Vote cast", f"Event #{event_id}", actor_id=user_id)
    return True


def get_voting_results(event_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM voting_events WHERE id = ?", (event_id,))
    event = row_to_dict(cursor.fetchone())
    if not event:
        conn.close()
        raise ValueError("Voting event not found.")
    cursor.execute("""
        SELECT o.id, o.label, COUNT(v.id) AS votes
        FROM voting_options o
        LEFT JOIN votes v ON v.option_id = o.id
        WHERE o.event_id = ?
        GROUP BY o.id
        ORDER BY o.position, o.id
    """, (event_id,))
    options = [row_to_dict(row) for row in cursor.fetchall()]
    total = sum(item["votes"] for item in options)
    winning_votes = max((item["votes"] for item in options), default=0)
    winners = []
    for option in options:
        option["percentage"] = round((option["votes"] / total) * 100, 2) if total else 0
        option["winner"] = bool(total and option["votes"] == winning_votes)
        if option["winner"]:
            winners.append(option["label"])
    conn.close()
    return {
        "event": event,
        "options": options,
        "total_votes": total,
        "winner_labels": winners,
        "is_tie": len(winners) > 1,
    }


MEETING_TYPES = {"general", "board", "committee", "training"}


def normalize_meeting_invitees(invitees):
    if invitees is None:
        return []
    if isinstance(invitees, str):
        invitees = invitees.split(",")
    if not isinstance(invitees, (list, tuple)):
        raise ValueError("Invitees must be a list or comma-separated string.")
    return [str(item).strip() for item in invitees if str(item).strip()]


def get_meeting(meeting_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,))
    meeting = row_to_dict(cursor.fetchone())
    if meeting:
        meeting["invitees"] = _json_list(meeting.get("invitees"))
    conn.close()
    return meeting


def store_whatsapp_messages(messages):
    if not messages:
        return 0
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executemany("""
        INSERT INTO whatsapp_messages (sender, sent_at, message, media_type, source_filename)
        VALUES (?, ?, ?, ?, ?)
    """, [
        (m["sender"], m["sent_at"], m["message"], m.get("media_type", "text"), m.get("source_filename", ""))
        for m in messages
    ])
    conn.commit()
    conn.close()
    log_activity("WhatsApp", "Import completed", f"{len(messages)} messages imported")
    return len(messages)


def list_whatsapp_messages(limit=100):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM whatsapp_messages
        ORDER BY sent_at ASC, id ASC
        LIMIT ?
    """, (limit,))
    rows = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def whatsapp_analytics(start=None, end=None, participant="", recent_limit=10):
    conn = get_connection()
    cursor = conn.cursor()
    clauses = []
    params = []
    participant_filter = (participant or "").strip()
    if start:
        clauses.append("date(sent_at) >= date(?)")
        params.append(start)
    if end:
        clauses.append("date(sent_at) <= date(?)")
        params.append(end)
    if participant_filter:
        clauses.append("sender = ? COLLATE NOCASE")
        params.append(participant_filter)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    recent_limit = max(1, min(int(recent_limit or 10), 100))

    cursor.execute("""
        SELECT COUNT(*) AS total_messages,
               COUNT(DISTINCT sender) AS participant_count,
               MIN(sent_at) AS first_message_at,
               MAX(sent_at) AS last_message_at
        FROM whatsapp_messages
        """ + where, params)
    summary = row_to_dict(cursor.fetchone()) or {}
    total_messages = int(summary.get("total_messages") or 0)
    participant_count = int(summary.get("participant_count") or 0)
    summary["average_messages_per_participant"] = round(total_messages / participant_count, 2) if participant_count else 0

    cursor.execute("""
        SELECT date(sent_at) AS label, COUNT(*) AS count
        FROM whatsapp_messages
        """ + where + """
        GROUP BY date(sent_at)
        ORDER BY label
    """, params)
    per_day = [row_to_dict(row) for row in cursor.fetchall()]
    cursor.execute("""
        SELECT sender AS label, COUNT(*) AS count
        FROM whatsapp_messages
        """ + where + """
        GROUP BY sender
        ORDER BY count DESC, sender
        LIMIT 10
    """, params)
    top_participants = [row_to_dict(row) for row in cursor.fetchall()]
    for participant in top_participants:
        participant["percentage"] = round((participant["count"] / total_messages) * 100, 2) if total_messages else 0

    cursor.execute("""
        SELECT sender AS label,
               COUNT(*) AS message_count,
               COUNT(DISTINCT date(sent_at)) AS active_days,
               MIN(sent_at) AS first_message_at,
               MAX(sent_at) AS last_message_at
        FROM whatsapp_messages
        """ + where + """
        GROUP BY sender
        ORDER BY message_count DESC, sender
        LIMIT 10
    """, params)
    active_participants = [row_to_dict(row) for row in cursor.fetchall()]
    for participant in active_participants:
        active_days = int(participant.get("active_days") or 0)
        participant["average_per_active_day"] = round(participant["message_count"] / active_days, 2) if active_days else 0

    cursor.execute("""
        SELECT media_type AS label, COUNT(*) AS count
        FROM whatsapp_messages
        """ + where + """
        GROUP BY media_type
        ORDER BY count DESC, media_type
    """, params)
    media_types = [row_to_dict(row) for row in cursor.fetchall()]
    cursor.execute("""
        SELECT strftime('%H', sent_at) AS label, COUNT(*) AS count
        FROM whatsapp_messages
        """ + where + """
        GROUP BY strftime('%H', sent_at)
        ORDER BY label
    """, params)
    peak_hours = [row_to_dict(row) for row in cursor.fetchall()]
    cursor.execute("""
        SELECT strftime('%w', sent_at) AS weekday, COUNT(*) AS count
        FROM whatsapp_messages
        """ + where + """
        GROUP BY strftime('%w', sent_at)
        ORDER BY weekday
    """, params)
    weekday_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    weekdays = [
        {"label": weekday_names[int(row["weekday"])], "count": row["count"]}
        for row in cursor.fetchall()
    ]
    cursor.execute("""
        SELECT id, sender, sent_at, message, media_type
        FROM whatsapp_messages
        """ + where + """
        ORDER BY sent_at DESC, id DESC
        LIMIT ?
    """, params + [recent_limit])
    recent_messages = [row_to_dict(row) for row in cursor.fetchall()]
    cursor.execute("""
        SELECT DISTINCT sender AS label
        FROM whatsapp_messages
        ORDER BY sender COLLATE NOCASE
    """)
    participants = [row_to_dict(row) for row in cursor.fetchall()]
    busiest_day = max(per_day, key=lambda row: row["count"], default=None)
    busiest_hour = max(peak_hours, key=lambda row: row["count"], default=None)
    most_active_participant = top_participants[0] if top_participants else None
    conn.close()
    return {
        "summary": summary,
        "per_day": per_day,
        "top_participants": top_participants,
        "active_participants": active_participants,
        "media_types": media_types,
        "peak_hours": peak_hours,
        "weekdays": weekdays,
        "recent_messages": recent_messages,
        "participants": participants,
        "filters": {
            "start": start or "",
            "end": end or "",
            "participant": participant_filter,
            "recent_limit": recent_limit,
        },
        "busiest_day": busiest_day,
        "busiest_hour": busiest_hour,
        "most_active_participant": most_active_participant,
    }


def create_meeting(title, description, meeting_at, location, agenda, invitees, created_by="", meeting_type="general"):
    title = (title or "").strip()
    location = (location or "").strip()
    agenda = (agenda or "").strip()
    description = (description or "").strip()
    meeting_type = (meeting_type or "general").strip().lower()
    invitees = normalize_meeting_invitees(invitees)

    if not title:
        raise ValueError("Meeting title is required.")
    if meeting_type not in MEETING_TYPES:
        raise ValueError("Meeting type must be general, board, committee, or training.")
    if not hasattr(meeting_at, "isoformat"):
        raise ValueError("Meeting date and time are required.")
    if meeting_at <= datetime_now():
        raise ValueError("Meeting date must be in the future.")
    if meeting_at > datetime_now() + timedelta(days=730):
        raise ValueError("Meeting date cannot be more than two years in the future.")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM meetings
        WHERE datetime(meeting_at) BETWEEN datetime(?, '-30 minutes') AND datetime(?, '+30 minutes')
          AND lower(location) = lower(?)
        LIMIT 1
    """, (meeting_at.isoformat(timespec="seconds"), meeting_at.isoformat(timespec="seconds"), location))
    if location and cursor.fetchone():
        conn.close()
        raise ValueError("Another meeting is already scheduled near that time and location.")
    cursor.execute("""
        INSERT INTO meetings (title, description, meeting_at, location, agenda, invitees, meeting_type, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (title, description, meeting_at.isoformat(timespec="seconds"), location, agenda, json.dumps(invitees), meeting_type, created_by))
    meeting_id = cursor.lastrowid
    conn.commit()
    conn.close()
    log_activity("Meetings", "Meeting scheduled", title, actor_name=created_by)
    create_notification("meeting", f"Meeting scheduled: {title}", agenda or "A meeting has been scheduled.", scheduled_for=meeting_at.isoformat(timespec="seconds"))
    return meeting_id


def list_meetings(start=None, end=None, meeting_type="", query="", upcoming_only=False):
    conn = get_connection()
    cursor = conn.cursor()
    clauses = []
    params = []
    meeting_type = (meeting_type or "").strip().lower()
    query = (query or "").strip()
    if upcoming_only:
        clauses.append("datetime(meeting_at) >= CURRENT_TIMESTAMP")
    if start:
        clauses.append("date(meeting_at) >= date(?)")
        params.append(start)
    if end:
        clauses.append("date(meeting_at) <= date(?)")
        params.append(end)
    if meeting_type:
        clauses.append("meeting_type = ?")
        params.append(meeting_type)
    if query:
        clauses.append("""(
            title LIKE ? COLLATE NOCASE OR
            description LIKE ? COLLATE NOCASE OR
            location LIKE ? COLLATE NOCASE OR
            agenda LIKE ? COLLATE NOCASE
        )""")
        params.extend([f"%{query}%"] * 4)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cursor.execute(f"SELECT * FROM meetings {where} ORDER BY meeting_at ASC", params)
    meetings = [row_to_dict(row) for row in cursor.fetchall()]
    for meeting in meetings:
        meeting["invitees"] = _json_list(meeting.get("invitees"))
    conn.close()
    return meetings


def record_attendance(meeting_id, member_id, status):
    if status not in {"present", "absent", "excused"}:
        raise ValueError("Attendance status must be present, absent, or excused.")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM meetings WHERE id = ?", (meeting_id,))
    if not cursor.fetchone():
        conn.close()
        raise ValueError("Meeting not found.")
    cursor.execute("SELECT id FROM users_data WHERE id = ?", (member_id,))
    if not cursor.fetchone():
        conn.close()
        raise ValueError("Member not found.")
    cursor.execute("""
        INSERT INTO meeting_attendance (meeting_id, member_id, status)
        VALUES (?, ?, ?)
        ON CONFLICT(meeting_id, member_id) DO UPDATE SET
            status = excluded.status,
            recorded_at = CURRENT_TIMESTAMP
    """, (meeting_id, member_id, status))
    conn.commit()
    conn.close()
    log_activity("Meetings", "Attendance recorded", f"Meeting #{meeting_id}")


def meeting_attendance_summary():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.title AS label,
               SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) AS present,
               COUNT(a.id) AS total
        FROM meetings m
        LEFT JOIN meeting_attendance a ON a.meeting_id = m.id
        GROUP BY m.id
        ORDER BY m.meeting_at DESC
        LIMIT 12
    """)
    rows = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def add_meeting_minutes(meeting_id, title, content, filename="", uploaded_by=""):
    title = (title or "").strip()
    content = (content or "").strip()
    if not title:
        raise ValueError("Minutes title is required.")
    if not content:
        raise ValueError("Minutes content is required.")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM meetings WHERE id = ?", (meeting_id,))
    if not cursor.fetchone():
        conn.close()
        raise ValueError("Meeting not found.")
    cursor.execute("""
        INSERT INTO meeting_minutes (meeting_id, title, content, filename, uploaded_by)
        VALUES (?, ?, ?, ?, ?)
    """, (meeting_id, title, content, filename, uploaded_by))
    conn.commit()
    conn.close()
    log_activity("Meetings", "Minutes saved", title, actor_name=uploaded_by)


def create_transaction(transaction_date, tx_type, category, amount, description="", recorded_by=""):
    if tx_type not in {"income", "expense"}:
        raise ValueError("Transaction type must be income or expense.")
    amount = float(amount)
    if amount <= 0:
        raise ValueError("Amount must be positive.")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO financial_transactions (transaction_date, type, category, amount, description, recorded_by)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (transaction_date, tx_type, category.strip(), amount, description.strip(), recorded_by))
    tx_id = cursor.lastrowid
    conn.commit()
    conn.close()
    log_activity("Finance", "Transaction recorded", f"{tx_type} {category}", actor_name=recorded_by)
    return tx_id


def upsert_budget(category, allocated_amount, fiscal_period):
    amount = float(allocated_amount)
    if amount <= 0:
        raise ValueError("Budget amount must be positive.")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO budgets (category, allocated_amount, fiscal_period)
        VALUES (?, ?, ?)
        ON CONFLICT(category, fiscal_period) DO UPDATE SET allocated_amount = excluded.allocated_amount
    """, (category.strip(), amount, fiscal_period.strip()))
    conn.commit()
    conn.close()


def financial_report():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT type, COALESCE(SUM(amount), 0) AS total
        FROM financial_transactions
        GROUP BY type
    """)
    totals = {row["type"]: row["total"] for row in cursor.fetchall()}
    cursor.execute("""
        SELECT strftime('%Y-%m', transaction_date) AS label,
               SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) AS income,
               SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS expense
        FROM financial_transactions
        GROUP BY strftime('%Y-%m', transaction_date)
        ORDER BY label
    """)
    monthly = [row_to_dict(row) for row in cursor.fetchall()]
    cursor.execute("""
        SELECT category AS label, SUM(amount) AS count
        FROM financial_transactions
        WHERE type = 'expense'
        GROUP BY category
        ORDER BY count DESC
    """)
    categories = [row_to_dict(row) for row in cursor.fetchall()]
    cursor.execute("""
        SELECT b.category, b.fiscal_period, b.allocated_amount,
               COALESCE(SUM(t.amount), 0) AS spent
        FROM budgets b
        LEFT JOIN financial_transactions t
          ON lower(t.category) = lower(b.category)
         AND t.type = 'expense'
         AND strftime('%Y', t.transaction_date) = b.fiscal_period
        GROUP BY b.id
        ORDER BY b.category
    """)
    budgets = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return {
        "total_income": totals.get("income", 0),
        "total_expense": totals.get("expense", 0),
        "net_balance": totals.get("income", 0) - totals.get("expense", 0),
        "monthly": monthly,
        "categories": categories,
        "budgets": budgets,
    }


def activity_summary(period="monthly"):
    modifier = {"daily": "-1 day", "weekly": "-7 days", "monthly": "-30 days"}.get(period, "-30 days")
    conn = get_connection()
    cursor = conn.cursor()
    stats = {
        "meetings": count_rows(cursor, "meetings", f"created_at >= datetime('now', '{modifier}')"),
        "votes": count_rows(cursor, "voting_events", f"created_at >= datetime('now', '{modifier}')"),
        "documents": count_rows(cursor, "uploads", f"created_at >= datetime('now', '{modifier}')"),
        "transactions": count_rows(cursor, "financial_transactions", f"created_at >= datetime('now', '{modifier}')"),
    }
    cursor.execute("""
        SELECT module, action, detail, actor_name, created_at
        FROM activity_log
        ORDER BY created_at DESC
        LIMIT 25
    """)
    feed = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"period": period, "stats": stats, "feed": feed}


def create_bug_report(title, severity, steps, expected, actual, reporter=""):
    if severity not in {"Critical", "High", "Medium", "Low"}:
        raise ValueError("Choose a valid severity.")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO bug_reports (title, severity, steps, expected, actual, reporter)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (title.strip(), severity, steps.strip(), expected.strip(), actual.strip(), reporter))
    bug_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return bug_id


def list_bug_reports():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bug_reports ORDER BY created_at DESC")
    rows = [row_to_dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def update_bug_status(bug_id, status, notes=""):
    if status not in {"Open", "In Progress", "Fixed", "Verified"}:
        raise ValueError("Choose a valid bug status.")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE bug_reports
        SET status = ?, resolution_notes = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (status, notes.strip(), bug_id))
    conn.commit()
    conn.close()
