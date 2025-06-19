"""
Simple schema migration for SQLite without extra dependencies.
Adds `role` column to `user` and `analysis` column to `library_item`.

Usage:
    python migrate_schema.py /path/to/your/tkdai.db
"""
import sqlite3
import sys
import os

def migrate(db_path):
    if not os.path.exists(db_path):
        print(f"Error: database file not found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("hi")

    # 1) Add role column to user table
    try:
        cursor.execute(
            "ALTER TABLE user ADD COLUMN role TEXT NOT NULL DEFAULT 'student'"
        )
        print("✅ Added column 'role' to 'user' table (default 'student').")
    except sqlite3.OperationalError as e:
        if 'duplicate column name' in str(e).lower():
            print("➡️  Column 'role' already exists, skipping.")
        else:
            print(f"❌ Failed to add 'role': {e}")

    print("hi2")

    # 2) Add analysis column to library_item table
    try:
        cursor.execute(
            "ALTER TABLE library_item ADD COLUMN analysis TEXT"
        )
        print("✅ Added column 'analysis' to 'library_item' table.")
    except sqlite3.OperationalError as e:
        if 'duplicate column name' in str(e).lower():
            print("➡️  Column 'analysis' already exists, skipping.")
        else:
            print(f"❌ Failed to add 'analysis': {e}")

    conn.commit()
    conn.close()
    print("🚀 Migration complete.")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python migrate_schema.py /path/to/tkdai.db")
        sys.exit(1)
    migrate(sys.argv[1])
