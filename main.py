import re
from flask import Flask, render_template, request, session, redirect, url_for
from database.database import create_user, fetch_unique_email, init_db, user_login, fetch_user_by_email, update_user_data

app = Flask(__name__, template_folder="frontend/pages")
app.secret_key = "super_secret_key"
init_db()

def is_valid_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

def is_valid_phone(phone):
    # Basic check: at least 7 digits, allowed characters: +, -, space, brackets
    digits = re.sub(r"\D", "", phone)
    return len(digits) >= 7

@app.route("/register", methods=["GET", "POST"])
@app.route("/", methods=["GET", "POST"])
def register_user():
    if request.method == "POST":
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        phone = request.form.get("phone")
        email = request.form.get("email")
        password = request.form.get("password") 
        confirm_password = request.form.get("confirm_password")
        checkbox = request.form.get("terms")  

        if not first_name or not last_name or not phone or not email or not password or not confirm_password or not checkbox:
            return render_template(
                "RegisterPage.html",
                error_message="All fields are required"
            )
        
        if not is_valid_email(email):
            return render_template(
                "RegisterPage.html",
                error_message="Invalid email format"
            )

        if not is_valid_phone(phone):
            return render_template(
                "RegisterPage.html",
                error_message="Invalid phone number"
            )

        if password != confirm_password:
            return render_template(
                "RegisterPage.html",
                password_error_message="Passwords do not match"
            )
        
        if fetch_unique_email(email):
            return render_template(
                "RegisterPage.html",
                email_error_message="Email already exists"
            )

        try:
            create_user(first_name, last_name, phone, email, password)
            return redirect(url_for("login"))

        except Exception as e:
            print("ERROR:", e)
            return render_template(
                "RegisterPage.html",
                error_message="Something went wrong. Please try again."
            )

    return render_template("RegisterPage.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if user_login(email, password):
            session["user_email"] = email
            return redirect(url_for("dashboard"))
        else:
            return render_template("LoginPage.html", error_message="Invalid credentials")

    return render_template("LoginPage.html")

@app.route("/dashboard")
def dashboard():
    if "user_email" not in session:
        return redirect(url_for("login"))
    
    user = fetch_user_by_email(session["user_email"])
    return render_template("DashboardPage.html", user=user)

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_email" not in session:
        return redirect(url_for("login"))
    
    user_email = session["user_email"]
    
    if request.method == "POST":
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        member_type = request.form.get("member_type")
        address = request.form.get("address")

        current_user = fetch_user_by_email(user_email)
        
        # Validation
        if not first_name or not last_name or not email or not phone:
            return render_template("ProfilePage.html", user=current_user, error_message="All fields are required")

        if not is_valid_email(email):
             return render_template("ProfilePage.html", user=current_user, error_message="Invalid email format")
        
        if not is_valid_phone(phone):
             return render_template("ProfilePage.html", user=current_user, error_message="Invalid phone number")

        # If email is changed, check if new email is unique
        if email != user_email and fetch_unique_email(email):
             return render_template("ProfilePage.html", user=current_user, error_message="Email already exists")

        try:
            update_user_data(user_email, first_name, last_name, email, current_user["password_hash"], phone, member_type, address)
            session["user_email"] = email # Update session if email changed
            updated_user = fetch_user_by_email(email)
            return render_template("ProfilePage.html", user=updated_user, success_message="Profile updated successfully")
        except Exception as e:
            print("ERROR:", e)
            return render_template("ProfilePage.html", user=current_user, error_message="Something went wrong")

    user = fetch_user_by_email(user_email)
    return render_template("ProfilePage.html", user=user)

@app.route("/logout")
def logout():
    session.pop("user_email", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)