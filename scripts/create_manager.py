import argparse
import sys
import time

from auth import hash_password
from database import connection, initialize


def main():
    parser = argparse.ArgumentParser(
        description="Create or replace the one manager login."
    )
    parser.add_argument("username")
    parser.add_argument("password")
    args = parser.parse_args()
    if len(args.password) < 8:
        parser.error("password must be at least 8 characters")

    initialize()
    with connection() as db:
        db.execute(
            "DELETE FROM sessions WHERE manager_id IN "
            "(SELECT id FROM managers WHERE username<>?)",
            (args.username,),
        )
        db.execute("DELETE FROM managers WHERE username<>?", (args.username,))
        db.execute(
            """
            INSERT INTO managers(username,password_hash,created_at) VALUES(?,?,?)
            ON CONFLICT(username) DO UPDATE SET
            password_hash=excluded.password_hash,failed_attempts=0,locked_until=0
            """,
            (args.username, hash_password(args.password), int(time.time() * 1000)),
        )
        db.commit()
    print(f"Manager login saved: {args.username}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Could not create manager: {error}", file=sys.stderr)
        raise
