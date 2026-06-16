from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session
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
)
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
import os

app = Flask(__name__, template_folder="frontend/pages")
app.secret_key = os.environ.get("PIXELHACK_SECRET_KEY", "pixelhack-dev-secret-key")

init_db()

admin_username = "owsper", "christos", "arda", "jira", "salami"
admin_pass = "owsper", "christos", "arda", "jira", "salami"


def is_admin_login(username, password):
    username = username.strip().lower()
    for admin_index, admin_name in enumerate(admin_username):
        if username == admin_name and password == admin_pass[admin_index]:
            return True
    return False


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id") and not session.get("admin_username"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def current_user():
    if session.get("admin_username"):
        admin_name = session["admin_username"]
        return {
            "id": 0,
            "username": admin_name,
            "email": f"{admin_name}@pixelhack.admin",
            "full_name": f"{admin_name.title()} Admin",
            "bio": "PixelHack organizer account.",
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



if __name__ == "__main__":
    app.run(debug=True)
