"""
AZSaboteur — SQL Injection Lab: Database Initialiser

Creates the SQLite database with intentionally weak seed data.
Run once before starting the Flask app:

    python init_db.py
"""

import os
import sqlite3

DB_PATH = os.environ.get("DB_PATH", "/opt/azsaboteur/app.db")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ── users table ──────────────────────────────────────────────
    cur.execute("DROP TABLE IF EXISTS users")
    cur.execute("""
        CREATE TABLE users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT    NOT NULL,
            password TEXT    NOT NULL,
            role     TEXT    NOT NULL DEFAULT 'user'
        )
    """)

    flag = os.environ.get("FLAG", "FLAG{sql1_cr3ds_dump3d}")

    users = [
        ("admin",    "SuperS3cretAdmin!",                   "admin"),
        ("jdoe",     "Password123",                         "user"),
        ("svc_deploy", flag,                                "service"),
        ("backup",   "b4ckup-2025!",                        "operator"),
    ]
    cur.executemany(
        "INSERT INTO users (username, password, role) VALUES (?, ?, ?)", users
    )

    # ── secrets table (target for UNION-based extraction) ───────
    cur.execute("DROP TABLE IF EXISTS secrets")
    cur.execute("""
        CREATE TABLE secrets (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            key_name  TEXT    NOT NULL,
            key_value TEXT    NOT NULL
        )
    """)

    next_step_secret = os.environ.get("NEXT_STEP_SECRET", "YOURFLAG{move_to_lateral_pivot}")

    secrets = [
        ("next_step_secret", next_step_secret),
        ("db_backup_key",    "aHR0cHM6Ly9zdG9yYWdlLmJsb2IuY29yZS53aW5kb3dz"),
    ]
    cur.executemany(
        "INSERT INTO secrets (key_name, key_value) VALUES (?, ?)", secrets
    )

    conn.commit()
    conn.close()
    print(f"[+] Database initialised at {DB_PATH}")


if __name__ == "__main__":
    init_db()
