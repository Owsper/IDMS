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
    add_column_if_missing(cursor, "users_data", "is_verified", "INTEGER DEFAULT 0")

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

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users_data(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users_data(username)")

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