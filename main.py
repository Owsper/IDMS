from flask import Flask, render_template, request
from database import init_db, create_user, user_login, fetch_unique_email, fetch_unique_username

app = Flask(__name__, template_folder="frontend/pages")

@app.route("/", methods=["GET", "POST"])
def register_user():
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

def login_user():
    error = None

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            error = "All fields are required."
        
        elif not user_login(email, password):
            error = "Invalid email or password."
        
        else:
            return render_template("DashboardPage.html")






    return render_template("LoginPage.html", error=error)

if __name__ == "__main__":
    app.run(debug=True)