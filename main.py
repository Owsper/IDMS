from flask import Flask, render_template, request
from database.database import create_user, fetch_unique_email

app = Flask(__name__, template_folder="frontend/pages")

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
            return render_template("LoginPage.html")

        except Exception as e:
            print("ERROR:", e)
            return render_template(
                "RegisterPage.html",
                error_message="Something went wrong. Please try again."
            )


    return render_template("RegisterPage.html", )

if __name__ == "__main__":
    app.run(debug=True)