import sqlite3

DB_NAME = "races.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS races (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        event_name TEXT NOT NULL,
        location TEXT NOT NULL,
        race_type TEXT NOT NULL,
        finish_time TEXT NOT NULL,
        pace TEXT,
        age INTEGER,
        weight REAL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS race_splits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER NOT NULL,
    label TEXT NOT NULL,          -- e.g. "5K", "10K", "Half", "30K"
    distance_miles REAL NOT NULL, -- used for pace calc
    split_time TEXT NOT NULL,     -- HH:MM:SS
    pace TEXT,
    FOREIGN KEY (race_id) REFERENCES races(id) ON DELETE CASCADE
    )
    """)
    
    conn.commit()
    conn.close()
