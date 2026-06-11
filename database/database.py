import sqlite3
import bcrypt

# Initialize the database and create the users_data table 
def init_db():
    conn = sqlite3.connect("main_db.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

# Insert user data into the database
def create_user(first_name, last_name, phone, email, password):
    conn = sqlite3.connect("main_db.db")
    cursor = conn.cursor()

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    password_hash = hashed_password.decode('utf-8')

    cursor.execute("""
        INSERT INTO users_data (first_name, last_name, phone, email, password_hash)
        VALUES (?, ?, ?, ?, ?)
    """, (first_name, last_name, phone, email, password_hash))

    conn.commit()
    conn.close()

    
# Verify if the email is unique before inserting a new user
def fetch_unique_email(email):
    conn = sqlite3.connect("main_db.db")
    cursor = conn.cursor()

    cursor.execute("SELECT email FROM users_data WHERE email = ?", (email,))
    email = cursor.fetchone()
    conn.close()

    if email is None:

        return False
    else:

        return True # EMAIL EXIST


def user_login(email, password):
    conn = sqlite3.connect("main_db.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    

    cursor.execute("SELECT email, password_hash FROM users_data WHERE email = ?", (email,))
    user_data = cursor.fetchone()
    conn.close()

    if user_data is None:
        return False
    else:
        stored_password_hash = user_data["password_hash"]
        return bcrypt.checkpw(password.encode('utf-8'), stored_password_hash.encode('utf-8'))







# Update user data in the database based on the verified email
def update_user_data(verified_email ,first_name, last_name, email, password_hash, phone):
    conn = sqlite3.connect("main_db.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users_data
        SET first_name = ?, last_name = ?, email = ?, password_hash = ?, phone = ?
        WHERE email = ?
    """, (first_name, last_name, email, password_hash, phone, verified_email))
    conn.commit()
    conn.close()

