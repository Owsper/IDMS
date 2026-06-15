from flask import Flask, render_template, request
from database import init_db, create_user

app = Flask(__name__, template_folder="frontend/pages")

@app.route("/", methods=["GET", "POST"])
def register_user():
    error = None

    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        admin_username = "owsper", "christos", "arda", "jira", "salami"
        admin_pass = "owsper", "christos", "arda", "jira", "salami"

        if not username or not email or not password or not confirm_password:
            error = "All fields are required."
        
        elif password != confirm_password:
            error = "Passwords do not match."
        
        elif username in admin_username and password in admin_pass:
            return render_template("DashboardPage.html")
        
        else: 
            create_user(username, email, password)
            return render_template("LoginPage.html")

    return render_template("RegisterPage.html", error=error)

def 

if __name__ == "__main__":
    app.run(debug=True)