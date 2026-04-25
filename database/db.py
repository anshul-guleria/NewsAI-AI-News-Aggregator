import sqlite3
from pathlib import Path

# Database file sits at the project root
DB_PATH = Path(__file__).parent.parent / "news_aggregator.db"


def get_db() -> sqlite3.Connection:
    """Return a new SQLite connection with WAL mode and row factory enabled."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables if they don't already exist."""
    conn = get_db()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    UNIQUE NOT NULL,
                email         TEXT    UNIQUE NOT NULL,
                password_hash TEXT    NOT NULL,
                created_at    TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS topics (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                topic       TEXT    UNIQUE NOT NULL,
                fetched_at  TEXT    NOT NULL,
                result_json TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_searches (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                topic_id    INTEGER NOT NULL,
                searched_at TEXT    NOT NULL,
                FOREIGN KEY (user_id)  REFERENCES users(id),
                FOREIGN KEY (topic_id) REFERENCES topics(id)
            );

            CREATE TABLE IF NOT EXISTS user_topic_subscriptions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                topic         TEXT    NOT NULL,
                subscribed_at TEXT    NOT NULL,
                UNIQUE(user_id, topic),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
        conn.commit()
        print(f"[DB] Initialized at {DB_PATH}")
    finally:
        conn.close()
