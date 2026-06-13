import sqlite3
from pathlib import Path


DB_FILE = Path("agent_history.db")


def save_detected_birthday(post_data):

    with sqlite3.connect(DB_FILE) as conn:

        conn.execute("""
        CREATE TABLE IF NOT EXISTS instagram_birthdays (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT,
            caption TEXT,
            post_url TEXT UNIQUE,
            detected_date TEXT,
            birthday_date TEXT
        )
        """)

        conn.execute("""
        INSERT OR IGNORE INTO instagram_birthdays (

            username,
            caption,
            post_url,
            detected_date,
            birthday_date

        ) VALUES (?, ?, ?, ?, ?)
        """, (

            post_data["username"],
            post_data["caption"],
            post_data["post_url"],
            post_data["date"],
            post_data["birthday_date"],
        ))

        conn.commit()