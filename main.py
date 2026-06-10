from flask import Flask, render_template, request
from IDMS.database.database import insert_user_data

app = Flask(__name__, template_folder="frontend/pages")

@app.route("/", methods=["GET", "POST"])
def register_user():
    if request.method == "POST":
        full_name = request.form["full_name"]
        email = request.form["email"]
        member_type = request.form["member_type"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            return "Passwords do not match"

        insert_user_data(full_name, email, member_type, password, confirm_password)

        return "Registration successful"


    return render_template("RegisterPage.html")

if __name__ == "__main__":
    app.run(debug=True)