"""Command line helpers.

  python manage.py init-db
  python manage.py create-admin you@example.com yourname 'a-strong-password'
  python manage.py sync            # run a full TMDB synchronisation now
"""
import sys

from app import prepare_database
from services import sync as syncer
from utils import validation  # noqa: F401
from utils.db import db
from utils.security import hash_password


def create_admin(email, username, password):
    email = email.lower()
    existing = db.one("SELECT id FROM profiles WHERE LOWER(email) = ?", [email])
    if existing:
        db.execute("UPDATE profiles SET role = 'admin' WHERE id = ?", [existing["id"]])
        print(f"{email} is now an admin.")
        return
    with db.tx() as t:
        uid = t.insert("INSERT INTO profiles (username, email, password_hash, role) VALUES (?,?,?,'admin')",
                       [username, email, hash_password(password)])
        t.execute("INSERT INTO user_preferences (user_id) VALUES (?)", [uid])
    print(f"Admin {username} <{email}> created.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "init-db":
        prepare_database()
        print("Database ready.")
    elif cmd == "create-admin" and len(sys.argv) == 5:
        prepare_database()
        create_admin(*sys.argv[2:5])
    elif cmd == "sync":
        prepare_database()
        syncer.start_sync("cli", background=False, force="--force" in sys.argv)
        latest = syncer.history(1)[0]
        print(f"Sync {latest['status']}: +{latest['titles_added']} added, {latest['titles_updated']} updated, "
              f"{latest['duplicates_skipped']} duplicates, {latest['errors']} errors")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
