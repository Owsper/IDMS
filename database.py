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
    
