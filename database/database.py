import sqlite3

# Initialize the database and create the users_data table 
def init_db():
    conn = sqlite3.connect("main_db.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

# Insert user data into the database
def insert_user_data(first_name, last_name, email, password_hash, phone):
    conn = sqlite3.connect("main_db.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO users_data (first_name, last_name, email, password_hash, phone)
        VALUES (?, ?, ?, ?, ?)
    """, (first_name, last_name, email, password_hash, phone))

    conn.commit()
    conn.close()
    
# Verify if the email is unique before inserting a new user
def fetch_unique_email(email):
    conn = sqlite3.connect("main_db.db")
    cursor = conn.cursor()

    cursor.execute("SELECT email FROM users_data WHERE email = ?", (email,))
    email = cursor.fetchone()
    if email is None:
        conn.close()
        print("Email is unique.")
        return True
    else:
        conn.close()
        print("Email is not unique.")
        return False
    
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

