from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, abort
from database import (
    init_db,
    create_user,
    user_login,
    fetch_unique_email,
    fetch_unique_username,
    get_user_by_id,
    update_user_profile,
    email_exists_for_other_user,
    username_exists_for_other_user,
    get_dashboard_stats,
    get_recent_activity,
    save_upload_metadata,
    get_approved_uploads,
    get_upload_by_id,
)
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from werkzeug.utils import secure_filename
import uuid
import hashlib
import os
import mimetypes

app = Flask(__name__, template_folder="frontend/pages")
app.secret_key = os.environ.get("PEXEL_SECRET_KEY", "pexel-dev-secret-key")

# Upload config: limit to 16MB per request and store files in a restricted folder
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB
app.config["UPLOAD_FOLDER"] = os.path.join(os.getcwd(), "secure_uploads")
app.config["PER_FILE_MAX_SIZE"] = 5 * 1024 * 1024  # 5 MB per file
# Allowed extensions for uploaded documents
app.config["ALLOWED_EXTENSIONS"] = {".pdf", ".docx", ".doc", ".txt", ".png", ".jpg", ".jpeg"}

# Ensure upload directory exists with restrictive permissions
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
try:
    os.chmod(app.config["UPLOAD_FOLDER"], 0o700)
except Exception:
    # chmod may fail on some filesystems; continue without crashing
    pass

init_db()

# Admin credentials (kept simple for demo/dev). Use lists for clarity and easier maintenance.
# IMPORTANT: In production, move admin credentials to a secure store or environment variables.
ADMIN_USERNAMES = ["owsper", "christos", "arda", "jira", "salami"]
ADMIN_PASSWORDS = ["owsper", "christos", "arda", "jira", "salami"]


def is_admin_login(username, password):
    """Return True if provided credentials match an admin account.

    Notes:
    - Admin accounts are stored in memory for this demo. In production use a secure store.
    - Comparison is case-insensitive for username.
    """
    if not username or not password:
        return False
    username_normalized = username.strip().lower()
    for idx, admin_name in enumerate(ADMIN_USERNAMES):
        # compare normalized username and the password at the same index
        if username_normalized == admin_name and password == ADMIN_PASSWORDS[idx]:
            return True
    return False


# Decorator to enforce authentication on routes.
# Usage: annotate routes with @login_required. It accepts both admin and normal user sessions.
def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id") and not session.get("admin_username"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def current_user():
    """Return the current authenticated user.

    Priority:
    1. If session contains 'admin_username', return a lightweight admin dict for templates.
    2. Otherwise, if session contains 'user_id', fetch the user record from the database.
    Returns None when there is no authenticated identity.
    """
    if session.get("admin_username"):
        admin_name = session["admin_username"]
        # Lightweight admin representation used across templates and permission checks
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
        }

    user_id = session.get("user_id")
    return get_user_by_id(user_id) if user_id else None

@app.route("/")
def home():
    return render_template("HomePage.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None

    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")


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
                return redirect(url_for("login"))
    


    return render_template("RegisterPage.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():

    error = None

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

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
            else:
                # Clear any previous session data (e.g., admin_username) before setting user_id
                session.clear()
                session["user_id"] = user["id"]
                return redirect(url_for("dashboard"))
            

    return render_template("LoginPage.html", error=error)


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    stats = get_dashboard_stats(user["id"])
    activities = get_recent_activity(user["id"])
    return render_template(
        "DashboardPage.html",
        user=user,
        stats=stats,
        activities=activities,
    )


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
    """Upload page. Only admin users may upload documents; successful uploads are approved.

    Validation rules:
    - Filename extension must be in ALLOWED_EXTENSIONS.
    - Each file must be <= PER_FILE_MAX_SIZE.
    - Request size limited by MAX_CONTENT_LENGTH.
    """
    user = current_user()

    # Allow authenticated users to POST files. Admin uploads are auto-approved, member uploads are saved for review.
    if request.method == "POST":
        if "files" not in request.files:
            return render_template("ImportFilesPage.html", error="No files provided.")

        files = request.files.getlist("files")
        saved_files = []

        # Determine uploader role
        is_admin = bool(session.get("admin_username"))

        for f in files:
            if not f or f.filename == "":
                continue

            original_name = secure_filename(f.filename)
            ext = os.path.splitext(original_name)[1].lower()

            # Validate extension
            if ext not in app.config["ALLOWED_EXTENSIONS"]:
                return render_template("ImportFilesPage.html", error=f"Invalid file type: {ext}")

            # Read content and enforce per-file size
            content = f.read()
            if len(content) > app.config["PER_FILE_MAX_SIZE"]:
                return render_template("ImportFilesPage.html", error=f"File too large: {original_name}")

            sha256 = hashlib.sha256(content).hexdigest()

            # Store with randomized name to avoid collisions and leakage
            stored_name = f"{uuid.uuid4().hex}{ext}"
            dest_path = os.path.join(app.config["UPLOAD_FOLDER"], stored_name)

            try:
                with open(dest_path, "wb") as out:
                    out.write(content)
                os.chmod(dest_path, 0o600)
            except Exception:
                return render_template("ImportFilesPage.html", error="Failed to save file on server.")

            # Persist metadata. Admins' uploads are auto-approved; members require approval.
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

    # GET: render page
    stats = get_dashboard_stats(user["id"]) if user else {}
    return render_template("ImportFilesPage.html", user=user, stats=stats)


# Members can view approved files
@app.route("/files")
@login_required
def list_files():
    user = current_user()
    files = get_approved_uploads(limit=200)
    return render_template("DocumentsPage.html", user=user, files=files, stats=get_dashboard_stats(user["id"]))


# Secure download endpoint: only serve files that are approved
@app.route("/files/<int:file_id>/download")
@login_required
def download_file(file_id):
    record = get_upload_by_id(file_id)
    if not record or int(record.get("approved", 0)) != 1:
        abort(404)

    stored_name = record["stored_filename"]
    # send_from_directory validates paths for us
    return send_from_directory(app.config["UPLOAD_FOLDER"], stored_name, as_attachment=True, mimetype=record.get("mime_type"))


if __name__ == "__main__":
    app.run(debug=True)
