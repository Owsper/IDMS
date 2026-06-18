from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, abort, jsonify
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.utils import secure_filename
from database import (
    init_db,
    create_user,
    user_login,
    fetch_unique_email,
    fetch_unique_username,
    get_user_by_id,
    get_user_by_email,
    update_user_profile,
    email_exists_for_other_user,
    username_exists_for_other_user,
    get_dashboard_stats,
    get_recent_activity,
    get_member_statistics,
    get_member_growth_history,
    save_upload_metadata,
    get_approved_uploads,
    get_upload_by_id,
    mark_user_verified,
    update_user_password,
    get_connection,
    get_table_schema,
    get_import_dashboard_stats,
    create_import_job,
    get_import_job,
    update_import_job,
    replace_import_rows,
    get_import_rows,
    get_import_history,
)
import uuid
import hashlib
import os
import mimetypes
import csv
import json
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__, template_folder="frontend/pages")
app.secret_key = os.environ.get("PEXEL_SECRET_KEY", "pexel-dev-secret-key")

# Upload configuration
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB
app.config["UPLOAD_FOLDER"] = os.path.join(os.getcwd(), "secure_uploads")
app.config["PER_FILE_MAX_SIZE"] = 5 * 1024 * 1024  # 5 MB per file
app.config["ALLOWED_EXTENSIONS"] = {".pdf", ".docx", ".doc", ".txt", ".png", ".jpg", ".jpeg"}
app.config["IMPORT_FOLDER"] = os.path.join(app.config["UPLOAD_FOLDER"], "imports")
app.config["IMPORT_ALLOWED_EXTENSIONS"] = {".csv", ".xlsx", ".json", ".sql", ".db", ".sqlite"}
app.config["IMPORT_MAX_SIZE"] = 10 * 1024 * 1024
app.config["IMPORT_ROLLBACK_MINUTES"] = 60
app.config["IMPORT_BATCH_SIZE"] = 250
app.config["PASSWORD_RESET_MAX_AGE"] = 3600

# Flask-Mail configuration
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USE_SSL"] = False
mail_username = "rohanftw2466@gmail.com"
mail_password = "pais dskg fwik ftyi"
app.config["MAIL_USERNAME"] = mail_username
app.config["MAIL_PASSWORD"] = mail_password
app.config["MAIL_DEFAULT_SENDER"] = "rohanftw2466@gmail.com"

mail = Mail(app)
serializer = URLSafeTimedSerializer(app.secret_key)

# Ensure upload directory exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["IMPORT_FOLDER"], exist_ok=True)
try:
    os.chmod(app.config["UPLOAD_FOLDER"], 0o700)
except Exception:
    pass

init_db()

# Admin credentials (demo only)
ADMIN_USERNAMES = ["owsper", "christos", "arda", "jira", "salami"]
ADMIN_PASSWORDS = ["owsper", "christos", "arda", "jira", "salami"]


def is_admin_login(email_input, password):
    """Check if credentials match an admin account.
    
    Note: Admin login uses email field but compares against username list.
    This works if admin types their username into the email field.
    """
    if not email_input or not password:
        return False
    username_normalized = email_input.strip().lower()
    for idx, admin_name in enumerate(ADMIN_USERNAMES):
        if username_normalized == admin_name and password == ADMIN_PASSWORDS[idx]:
            return True
    return False


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id") and not session.get("admin_username"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("admin_username"):
            abort(403)
        return view(*args, **kwargs)
    return wrapped_view


def current_user():
    if session.get("admin_username"):
        admin_name = session["admin_username"]
        return {
            "id": 0,
            "username": admin_name,
            "email": f"{admin_name}@pexel.admin",
            "full_name": f"{admin_name.title()} Admin",
            "bio": "Pexel organizer account.",
            "skills": "Event management, judging, community support",
            "team_role": "Organizer",
            "profile_picture": "",
            "role": "Admin",
            "created_at": "Admin account",
            "updated_at": None,
            "last_login_at": "Current session",
            "is_verified": 1,
        }

    user_id = session.get("user_id")
    return get_user_by_id(user_id) if user_id else None


IMPORT_TARGET_TABLES = {"users_data"}
IMPORT_SYSTEM_COLUMNS = {"created_at", "updated_at", "last_login_at"}


def json_response_error(message, status=400, **extra):
    payload = {"error": message}
    payload.update(extra)
    return jsonify(payload), status


def require_import_job(job_id):
    job = get_import_job(job_id)
    if not job:
        abort(404)
    return job


def safe_target_table(table_name):
    table_name = (table_name or "users_data").strip()
    if table_name not in IMPORT_TARGET_TABLES:
        abort(400, description="Unsupported import target.")
    return table_name


def import_file_path(stored_filename):
    return os.path.join(app.config["IMPORT_FOLDER"], stored_filename)


def parse_csv_file(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return [{key: value for key, value in row.items()} for row in reader]


def parse_json_file(path):
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = next((value for value in data.values() if isinstance(value, list)), [])
    else:
        rows = []

    normalized = []
    for row in rows:
        if isinstance(row, dict):
            normalized.append(row)
    return normalized


def parse_xlsx_file(path):
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise ValueError("XLSX imports require the openpyxl package.") from exc

    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows_iter = sheet.iter_rows(values_only=True)
    headers = next(rows_iter, None)
    if not headers:
        return []

    header_values = [str(value).strip() if value is not None else "" for value in headers]
    records = []
    for values in rows_iter:
        records.append({
            header_values[index]: json_safe_value(value)
            for index, value in enumerate(values)
            if index < len(header_values) and header_values[index]
        })
    return records


def json_safe_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def first_user_table(cursor):
    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        LIMIT 1
    """)
    row = cursor.fetchone()
    return row[0] if row else None


def rows_from_sqlite_connection(conn):
    cursor = conn.cursor()
    table_name = first_user_table(cursor)
    if not table_name:
        return []
    cursor.execute(f'SELECT * FROM "{table_name}"')
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def parse_sqlite_file(path):
    conn = sqlite3.connect(path)
    try:
        return rows_from_sqlite_connection(conn)
    finally:
        conn.close()


def parse_sql_file(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        script = handle.read()
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(script)
        return rows_from_sqlite_connection(conn)
    finally:
        conn.close()


def parse_import_file(path, ext):
    if ext == ".csv":
        return parse_csv_file(path)
    if ext == ".json":
        return parse_json_file(path)
    if ext == ".xlsx":
        return parse_xlsx_file(path)
    if ext in {".db", ".sqlite"}:
        return parse_sqlite_file(path)
    if ext == ".sql":
        return parse_sql_file(path)
    raise ValueError("Unsupported import file type.")


def schema_payload(table_name):
    columns = get_table_schema(table_name)
    return [{
        "name": column["name"],
        "type": column["type"],
        "required": bool(column["notnull"]) and column["dflt_value"] is None and not column["pk"],
        "primary_key": bool(column["pk"]),
        "editable": column["name"] not in IMPORT_SYSTEM_COLUMNS,
    } for column in columns]


def guess_field_mapping(headers, schema):
    normalized_headers = {str(header).strip().lower(): header for header in headers}
    mapping = {}
    for column in schema:
        column_name = column["name"]
        if not column["editable"]:
            continue
        source = normalized_headers.get(column_name.lower())
        if source:
            mapping[source] = column_name
    return mapping


def normalize_import_value(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value if value != "" else None
    return value


def validate_type(value, column_type):
    if value is None:
        return True
    column_type = (column_type or "").upper()
    if "INT" in column_type:
        try:
            int(value)
            return True
        except (TypeError, ValueError):
            return False
    if any(token in column_type for token in ["REAL", "FLOA", "DOUB"]):
        try:
            float(value)
            return True
        except (TypeError, ValueError):
            return False
    return True


def coerce_value(value, column_type):
    value = normalize_import_value(value)
    if value is None:
        return None
    column_type = (column_type or "").upper()
    if "INT" in column_type:
        return int(value)
    if any(token in column_type for token in ["REAL", "FLOA", "DOUB"]):
        return float(value)
    return str(value)


def existing_record_for(cursor, table_name, duplicate_key, mapped_data):
    value = mapped_data.get(duplicate_key)
    if value in (None, ""):
        return None
    cursor.execute(f"SELECT * FROM {table_name} WHERE {duplicate_key} = ? LIMIT 1", (value,))
    row = cursor.fetchone()
    return dict(row) if row else None


def validate_import_rows(job, mapping, duplicate_key):
    target_table = safe_target_table(job["target_table"])
    schema = schema_payload(target_table)
    editable_columns = {column["name"]: column for column in schema if column["editable"]}
    rows = parse_import_file(import_file_path(job["stored_filename"]), job["file_ext"])
    prepared = []

    conn = get_connection()
    cursor = conn.cursor()
    try:
        for index, source_row in enumerate(rows, start=1):
            mapped_data = {}
            errors = []
            for source_field, target_field in mapping.items():
                if target_field not in editable_columns:
                    continue
                column = editable_columns[target_field]
                value = normalize_import_value(source_row.get(source_field))
                if not validate_type(value, column["type"]):
                    errors.append(f"{target_field} must match {column['type'] or 'TEXT'}")
                    continue
                try:
                    mapped_data[target_field] = coerce_value(value, column["type"])
                except (TypeError, ValueError):
                    errors.append(f"{target_field} has an invalid value")

            for column in editable_columns.values():
                if column["required"] and mapped_data.get(column["name"]) in (None, ""):
                    errors.append(f"{column['name']} is required")

            email = mapped_data.get("email")
            if email and ("@" not in str(email) or "." not in str(email)):
                errors.append("email must be a valid address")

            if "password" in mapped_data and "password_hash" not in mapped_data:
                errors.append("map passwords to password_hash before import")

            existing = existing_record_for(cursor, target_table, duplicate_key, mapped_data)
            duplicate_value = str(mapped_data.get(duplicate_key) or "")
            status = "invalid" if errors else "valid"

            if not errors and existing:
                comparable_existing = {key: existing.get(key) for key in mapped_data.keys()}
                status = "duplicate" if comparable_existing == mapped_data else "conflict"

            prepared.append({
                "row_number": index,
                "source_data": source_row,
                "mapped_data": mapped_data,
                "status": status,
                "errors": errors,
                "duplicate_key": duplicate_value,
                "existing_record": existing or {},
            })
    finally:
        conn.close()

    return prepared


def row_counts(rows):
    counts = {"total": len(rows), "valid": 0, "invalid": 0, "duplicate": 0, "conflict": 0}
    for row in rows:
        status = row.get("status", "pending")
        counts[status] = counts.get(status, 0) + 1
    return counts


def generate_verification_token(email):
    return serializer.dumps(email, salt="email-verify")


def confirm_verification_token(token, expiration=3600):
    return serializer.loads(token, salt="email-verify", max_age=expiration)


def send_verification_email(email, username):
    token = generate_verification_token(email)
    verify_url = url_for("verify_email", token=token, _external=True)

    msg = Message(
        subject="Verify your Pexel account",
        recipients=[email],
        sender=app.config["MAIL_DEFAULT_SENDER"],
        body=(
            f"Hi {username},\n\n"
            f"Please verify your Pexel account by clicking this link:\n"
            f"{verify_url}\n\n"
            f"This link expires in 1 hour."
        ),
    )

    try:
        mail.send(msg)
        return True
    except Exception as e:
        app.logger.exception("Verification email failed")
        return False


def password_reset_fingerprint(user):
    """Tie a reset link to the current password so it can only be used once."""
    return hashlib.sha256(user["password_hash"].encode("utf-8")).hexdigest()[:16]


def generate_password_reset_token(user):
    return serializer.dumps(
        {"user_id": user["id"], "fingerprint": password_reset_fingerprint(user)},
        salt="password-reset",
    )


def confirm_password_reset_token(token):
    payload = serializer.loads(
        token,
        salt="password-reset",
        max_age=app.config["PASSWORD_RESET_MAX_AGE"],
    )
    user = get_user_by_id(payload.get("user_id"))
    if not user or payload.get("fingerprint") != password_reset_fingerprint(user):
        raise BadSignature("Password reset link is no longer valid.")
    return user


def send_password_reset_email(user):
    token = generate_password_reset_token(user)
    reset_url = url_for("reset_password", token=token, _external=True)
    msg = Message(
        subject="Reset your Pexel password",
        recipients=[user["email"]],
        sender=app.config["MAIL_DEFAULT_SENDER"],
        body=(
            f"Hi {user['username']},\n\n"
            "Use the link below to choose a new password:\n"
            f"{reset_url}\n\n"
            "This link expires in 1 hour and can only be used once. "
            "If you did not request this, you can ignore this email."
        ),
    )
    try:
        mail.send(msg)
        return True
    except Exception:
        app.logger.exception("Password reset email failed")
        return False


@app.route("/")
def home():
    return render_template("HomePage.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    success = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not email or not password or not confirm_password:
            error = "All fields are required."
        elif password != confirm_password:
            error = "Passwords do not match."
        else:
            if fetch_unique_username(username):
                error = "Username already exists."
            elif fetch_unique_email(email):
                error = "Email already exists."
            else:
                create_user(username, email, password)
                sent = send_verification_email(email, username)
                if sent:
                    success = "Account created. Please check your email to verify your account."
                else:
                    success = "Account created, but verification email could not be sent right now."

    return render_template("RegisterPage.html", error=error, success=success)


@app.route("/verify-email/<token>")
def verify_email(token):
    try:
        email = confirm_verification_token(token)
    except SignatureExpired:
        return render_template("VerifyPage.html", error="Your verification link has expired.")
    except BadSignature:
        return render_template("VerifyPage.html", error="Invalid verification link.")

    user = get_user_by_email(email)
    if not user:
        return render_template("VerifyPage.html", error="User not found.")

    if int(user.get("is_verified", 0)) == 1:
        return render_template("VerifyPage.html", success="Your account is already verified.")

    mark_user_verified(user["id"])
    return render_template("VerifyPage.html", success="Email verified successfully. You can now log in.")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            error = "All fields are required."
        elif is_admin_login(email, password):
            session.clear()
            session["admin_username"] = email.strip().lower()
            return redirect(url_for("dashboard"))
        else:
            user = user_login(email, password)
            if not user:
                error = "Invalid email or password."
            elif int(user.get("is_verified", 0)) != 1:
                error = "Please verify your email before logging in."
            else:
                session.clear()
                session["user_id"] = user["id"]
                return redirect(url_for("dashboard"))

    return render_template("LoginPage.html", error=error)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    success = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if email:
            user = get_user_by_email(email)
            if user:
                send_password_reset_email(user)

        # Do not reveal whether an email address is registered.
        success = "If an account exists for that email, a password reset link has been sent."

    return render_template("PasswordResetPage.html", mode="request", success=success)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        user = confirm_password_reset_token(token)
    except SignatureExpired:
        return render_template(
            "PasswordResetPage.html",
            mode="invalid",
            error="This password reset link has expired. Please request a new one.",
        ), 400
    except BadSignature:
        return render_template(
            "PasswordResetPage.html",
            mode="invalid",
            error="This password reset link is invalid or has already been used.",
        ), 400

    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not password or not confirm_password:
            error = "Both password fields are required."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm_password:
            error = "Passwords do not match."
        else:
            update_user_password(user["id"], password)
            session.clear()
            return render_template(
                "PasswordResetPage.html",
                mode="complete",
                success="Your password has been reset. You can now sign in.",
            )

    return render_template("PasswordResetPage.html", mode="reset", error=error)


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    stats = get_dashboard_stats(user["id"])
    activities = get_recent_activity(user["id"])
    member_stats = get_member_statistics() if session.get("admin_username") else None
    member_growth = get_member_growth_history() if session.get("admin_username") else []
    import_stats = get_import_dashboard_stats() if session.get("admin_username") else None
    return render_template(
        "DashboardPage.html",
        user=user,
        stats=stats,
        activities=activities,
        member_stats=member_stats,
        member_growth=member_growth,
        import_stats=import_stats,
    )


@app.route("/api/admin/member-stats")
@login_required
@admin_required
def api_admin_member_stats():
    return jsonify(get_member_statistics())


@app.route("/api/admin/member-growth")
@login_required
@admin_required
def api_admin_member_growth():
    return jsonify({"growth": get_member_growth_history()})


@app.route("/admin/import-data")
@login_required
@admin_required
def admin_import_data():
    user = current_user()
    return render_template(
        "AdminImportDataPage.html",
        user=user,
        import_stats=get_import_dashboard_stats(),
        history=get_import_history(limit=20),
    )


@app.route("/api/admin/import/upload", methods=["POST"])
@login_required
@admin_required
def api_admin_import_upload():
    target_table = safe_target_table(request.form.get("target_table", "users_data"))
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return json_response_error("Choose a database file to import.")

    original_name = secure_filename(uploaded.filename)
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in app.config["IMPORT_ALLOWED_EXTENSIONS"]:
        return json_response_error("Unsupported file type.", allowed=sorted(app.config["IMPORT_ALLOWED_EXTENSIONS"]))

    content = uploaded.read()
    if len(content) > app.config["IMPORT_MAX_SIZE"]:
        return json_response_error("File is too large.", max_size=app.config["IMPORT_MAX_SIZE"])

    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest_path = import_file_path(stored_name)
    with open(dest_path, "wb") as out:
        out.write(content)

    try:
        os.chmod(dest_path, 0o600)
    except Exception:
        pass

    try:
        rows = parse_import_file(dest_path, ext)
    except Exception as exc:
        try:
            os.remove(dest_path)
        except Exception:
            pass
        return json_response_error(str(exc))

    headers = list(rows[0].keys()) if rows else []
    schema = schema_payload(target_table)
    mapping = guess_field_mapping(headers, schema)
    job_id = create_import_job(
        admin_username=session["admin_username"],
        original_filename=original_name,
        stored_filename=stored_name,
        target_table=target_table,
        file_ext=ext,
        file_size=len(content),
    )
    update_import_job(job_id, field_mapping=json.dumps(mapping))

    return jsonify({
        "job_id": job_id,
        "file_name": original_name,
        "row_count": len(rows),
        "headers": headers,
        "schema": schema,
        "suggested_mapping": mapping,
        "duplicate_keys": [column["name"] for column in schema if column["name"] in {"id", "email", "username"}],
        "preview": rows[:20],
    })


@app.route("/api/admin/import/validate", methods=["POST"])
@login_required
@admin_required
def api_admin_import_validate():
    payload = request.get_json(silent=True) or {}
    job = require_import_job(payload.get("job_id"))
    target_table = safe_target_table(job["target_table"])
    schema_names = {column["name"] for column in schema_payload(target_table)}
    duplicate_key = payload.get("duplicate_key") or "email"
    if duplicate_key not in schema_names or duplicate_key not in {"id", "email", "username"}:
        return json_response_error("Duplicate key must be id, email, or username.")

    mapping = payload.get("mapping") or {}
    if not isinstance(mapping, dict) or not mapping:
        return json_response_error("Map at least one uploaded field to the target schema.")

    rows = validate_import_rows(job, mapping, duplicate_key)
    replace_import_rows(job["id"], rows)
    persisted_rows = get_import_rows(job["id"])
    counts = row_counts(rows)
    update_import_job(
        job["id"],
        status="validated",
        field_mapping=json.dumps(mapping),
        duplicate_key=duplicate_key,
        summary=json.dumps(counts),
    )

    return jsonify({
        "job_id": job["id"],
        "counts": counts,
        "invalid_rows": [row for row in persisted_rows if row["status"] == "invalid"][:25],
        "conflicts": [row for row in persisted_rows if row["status"] in {"duplicate", "conflict"}][:25],
        "valid_preview": [row for row in persisted_rows if row["status"] == "valid"][:20],
    })


@app.route("/api/admin/import/merge", methods=["POST"])
@login_required
@admin_required
def api_admin_import_merge():
    payload = request.get_json(silent=True) or {}
    job = require_import_job(payload.get("job_id"))
    strategy = payload.get("conflict_strategy", "skip")
    resolutions = payload.get("resolutions") or {}
    if strategy not in {"skip", "overwrite", "manual"}:
        return json_response_error("Conflict strategy must be skip, overwrite, or manual.")

    rows = get_import_rows(job["id"], statuses=["valid", "duplicate", "conflict"])
    if not rows:
        return json_response_error("Validate the import before merging.")

    target_table = safe_target_table(job["target_table"])
    schema = schema_payload(target_table)
    editable_columns = [column["name"] for column in schema if column["editable"]]
    insertable_columns = [name for name in editable_columns if name != "id"]
    duplicate_key = job.get("duplicate_key") or "email"
    now = datetime.utcnow()
    rollback_until = now + timedelta(minutes=app.config["IMPORT_ROLLBACK_MINUTES"])
    summary = {"added": 0, "updated": 0, "skipped": 0, "failed": 0, "manual": 0}

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN")
        for row in rows:
            mapped_data = {
                key: value
                for key, value in row["mapped_data"].items()
                if key in editable_columns and value is not None
            }
            if not mapped_data:
                summary["failed"] += 1
                continue

            existing = existing_record_for(cursor, target_table, duplicate_key, mapped_data)
            decision = strategy
            if strategy == "manual":
                decision = resolutions.get(str(row["id"]), "")
                if decision not in {"skip", "overwrite"}:
                    summary["manual"] += 1
                    continue

            if existing:
                if decision == "skip":
                    summary["skipped"] += 1
                    continue

                update_columns = [key for key in mapped_data.keys() if key in editable_columns and key != "id"]
                if not update_columns:
                    summary["skipped"] += 1
                    continue
                set_clause = ", ".join([f"{column} = ?" for column in update_columns])
                values = [mapped_data[column] for column in update_columns]
                values.append(existing["id"])
                cursor.execute(f"UPDATE {target_table} SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", values)
                cursor.execute("""
                    INSERT INTO import_changes (job_id, table_name, record_pk, action, before_data, after_data)
                    VALUES (?, ?, ?, 'update', ?, ?)
                """, (
                    job["id"],
                    target_table,
                    str(existing["id"]),
                    json.dumps(dict(existing)),
                    json.dumps(mapped_data),
                ))
                summary["updated"] += 1
                continue

            columns = [column for column in insertable_columns if column in mapped_data]
            if "full_name" not in columns and mapped_data.get("username"):
                mapped_data["full_name"] = mapped_data["username"]
                columns.append("full_name")
            if "is_verified" not in columns:
                mapped_data["is_verified"] = 1
                columns.append("is_verified")
            if not columns:
                summary["failed"] += 1
                continue

            placeholders = ", ".join(["?"] * len(columns))
            cursor.execute(
                f"INSERT INTO {target_table} ({', '.join(columns)}) VALUES ({placeholders})",
                [mapped_data[column] for column in columns],
            )
            record_id = cursor.lastrowid
            cursor.execute(f"SELECT * FROM {target_table} WHERE id = ?", (record_id,))
            inserted = dict(cursor.fetchone())
            cursor.execute("""
                INSERT INTO import_changes (job_id, table_name, record_pk, action, before_data, after_data)
                VALUES (?, ?, ?, 'insert', '{}', ?)
            """, (job["id"], target_table, str(record_id), json.dumps(inserted)))
            summary["added"] += 1

        cursor.execute("""
            UPDATE import_jobs
            SET status = ?,
                conflict_strategy = ?,
                summary = ?,
                merged_at = CURRENT_TIMESTAMP,
                rollback_until = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            "needs_manual_resolution" if summary["manual"] else "merged",
            strategy,
            json.dumps(summary),
            rollback_until.isoformat(timespec="seconds"),
            job["id"],
        ))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        update_import_job(job["id"], status="failed", error_message=str(exc))
        return json_response_error("Import merge failed and was rolled back.", details=str(exc), status=500)
    finally:
        conn.close()

    return jsonify({"job_id": job["id"], "summary": summary, "rollback_until": rollback_until.isoformat(timespec="seconds")})


@app.route("/api/admin/import/history")
@login_required
@admin_required
def api_admin_import_history():
    return jsonify({"history": get_import_history(limit=50), "stats": get_import_dashboard_stats()})


@app.route("/api/admin/import/<int:job_id>/rollback", methods=["POST"])
@login_required
@admin_required
def api_admin_import_rollback(job_id):
    job = require_import_job(job_id)
    if job.get("rolled_back_at"):
        return json_response_error("This import has already been rolled back.")
    if not job.get("rollback_until"):
        return json_response_error("This import does not have a rollback window.")

    try:
        rollback_until = datetime.fromisoformat(job["rollback_until"])
    except ValueError:
        return json_response_error("Rollback window is invalid.")
    if datetime.utcnow() > rollback_until:
        return json_response_error("Rollback window has expired.")

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN")
        cursor.execute("""
            SELECT *
            FROM import_changes
            WHERE job_id = ? AND rolled_back_at IS NULL
            ORDER BY id DESC
        """, (job_id,))
        changes = [dict(row) for row in cursor.fetchall()]
        for change in changes:
            table_name = safe_target_table(change["table_name"])
            if change["action"] == "insert":
                cursor.execute(f"DELETE FROM {table_name} WHERE id = ?", (change["record_pk"],))
            elif change["action"] == "update":
                before = json.loads(change["before_data"] or "{}")
                columns = [key for key in before.keys() if key not in {"id"}]
                set_clause = ", ".join([f"{column} = ?" for column in columns])
                cursor.execute(
                    f"UPDATE {table_name} SET {set_clause} WHERE id = ?",
                    [before[column] for column in columns] + [change["record_pk"]],
                )
            cursor.execute(
                "UPDATE import_changes SET rolled_back_at = CURRENT_TIMESTAMP WHERE id = ?",
                (change["id"],),
            )

        cursor.execute("""
            UPDATE import_jobs
            SET status = 'rolled_back',
                rolled_back_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (job_id,))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return json_response_error("Rollback failed.", details=str(exc), status=500)
    finally:
        conn.close()

    return jsonify({"job_id": job_id, "rolled_back": True})


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = current_user()
    error_message = None
    success_message = None

    if session.get("admin_username") and request.method == "POST":
        error_message = "Admin demo profile cannot be edited from this page."
        stats = get_dashboard_stats(user["id"])
        return render_template(
            "ProfilePage.html",
            user=user,
            stats=stats,
            success_message=success_message,
            error_message=error_message,
        )

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        bio = request.form.get("bio", "").strip()
        skills = request.form.get("skills", "").strip()
        team_role = request.form.get("team_role", "").strip()
        profile_picture = request.form.get("profile_picture", "").strip()

        if not full_name or not username or not email:
            error_message = "Full name, username, and email are required."
        elif "@" not in email or "." not in email:
            error_message = "Please enter a valid email address."
        elif username_exists_for_other_user(username, user["id"]):
            error_message = "Username already exists."
        elif email_exists_for_other_user(email, user["id"]):
            error_message = "Email already exists."
        else:
            update_user_profile(
                user["id"],
                full_name,
                username,
                email,
                bio,
                skills,
                team_role or "Developer",
                profile_picture,
            )
            success_message = "Profile updated successfully."
            user = current_user()

    stats = get_dashboard_stats(user["id"])
    return render_template(
        "ProfilePage.html",
        user=user,
        stats=stats,
        success_message=success_message,
        error_message=error_message,
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/meetings")
@login_required
def meetings():
    return render_template("MeetingsPage.html")


@app.route("/voting")
@login_required
def voting():
    return render_template("VotingPage.html")


@app.route("/import-files", methods=["GET", "POST"])
@login_required
def import_files():
    user = current_user()

    if request.method == "POST":
        if "files" not in request.files:
            return render_template("ImportFilesPage.html", error="No files provided.")

        files = request.files.getlist("files")
        saved_files = []
        is_admin = bool(session.get("admin_username"))

        for f in files:
            if not f or f.filename == "":
                continue

            original_name = secure_filename(f.filename)
            ext = os.path.splitext(original_name)[1].lower()

            if ext not in app.config["ALLOWED_EXTENSIONS"]:
                return render_template("ImportFilesPage.html", error=f"Invalid file type: {ext}")

            content = f.read()
            if len(content) > app.config["PER_FILE_MAX_SIZE"]:
                return render_template("ImportFilesPage.html", error=f"File too large: {original_name}")

            sha256 = hashlib.sha256(content).hexdigest()
            stored_name = f"{uuid.uuid4().hex}{ext}"
            dest_path = os.path.join(app.config["UPLOAD_FOLDER"], stored_name)

            try:
                with open(dest_path, "wb") as out:
                    out.write(content)
                os.chmod(dest_path, 0o600)
            except Exception:
                return render_template("ImportFilesPage.html", error="Failed to save file on server.")

            try:
                save_upload_metadata(
                    user_id=(None if is_admin else (user["id"] if user else None)),
                    original_filename=original_name,
                    stored_filename=stored_name,
                    mime_type=f.mimetype or "application/octet-stream",
                    size=len(content),
                    sha256=sha256,
                    approved=(1 if is_admin else 0),
                    approved_by=(session.get("admin_username") if is_admin else None),
                )
            except Exception:
                app.logger.exception("Failed saving upload metadata")
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
                return render_template("ImportFilesPage.html", error="Failed to save upload metadata.")

            saved_files.append(original_name)

        if is_admin:
            return render_template("ImportFilesPage.html", success=f"Uploaded and approved {len(saved_files)} files.")
        else:
            return render_template("ImportFilesPage.html", success=f"Uploaded {len(saved_files)} files; pending approval.")

    stats = get_dashboard_stats(user["id"]) if user else {}
    return render_template("ImportFilesPage.html", user=user, stats=stats)


@app.route("/files")
@login_required
def list_files():
    user = current_user()
    files = get_approved_uploads(limit=200)
    return render_template("DocumentsPage.html", user=user, files=files, stats=get_dashboard_stats(user["id"]))


@app.route("/files/<int:file_id>/download")
@login_required
def download_file(file_id):
    record = get_upload_by_id(file_id)
    if not record or int(record.get("approved", 0)) != 1:
        abort(404)

    stored_name = record["stored_filename"]
    return send_from_directory(app.config["UPLOAD_FOLDER"], stored_name, as_attachment=True, mimetype=record.get("mime_type"))


if __name__ == "__main__":
    app.run(debug=True)
