import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB_PATH = os.environ.get("DB_PATH", str(ROOT / "app.db"))


def initialize():
    with connection() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS managers(
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions(
                token_hash TEXT PRIMARY KEY,
                manager_id INTEGER NOT NULL REFERENCES managers(id),
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS tenants(
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                unit TEXT UNIQUE NOT NULL COLLATE NOCASE,
                phone TEXT NOT NULL,
                rent INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS payments(
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                amount INTEGER NOT NULL,
                mpesa_code TEXT UNIQUE NOT NULL,
                paid_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reminders(
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL REFERENCES tenants(id),
                message TEXT NOT NULL,
                sent_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS pay_idx ON payments(tenant_id,paid_at);
            """
        )


@contextmanager
def connection():
    db = connect()
    try:
        yield db
    finally:
        db.close()


def connect():
    db = sqlite3.connect(DB_PATH, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db
