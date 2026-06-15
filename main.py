from flask import Flask, render_template, request, redirect, url_for
from database import init_db, create_user, user_login, fetch_unique_email, fetch_unique_username
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
import os

app = Flask(__name__, template_folder="frontend/pages")

init_db() if not os.path.exists("main_db.db") else None

@app.route("/")
def home():
    return redirect(url_for("register"))

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
                return render_template("LoginPage.html")
    


    return render_template("RegisterPage.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():

    error = None

    admin_usernme = "owsper", "christos", "arda", "jira", "salami"
    admin_pass = "owsper", "christos", "arda", "jira", "salami"


    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            error = "All fields are required."
        
        elif email and password in admin_usernme and admin_pass:
            return render_template("DashboardPage.html")
        
        elif not user_login(email, password):
            error = "Invalid email or password."
        
        else:
            return render_template("MeetingPage.html")

    return render_template("LoginPage.html", error=error)



if __name__ == "__main__":
    app.run(debug=True)