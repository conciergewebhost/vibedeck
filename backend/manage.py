"""Management CLI for Vibedeck.

Run from the backend/ directory with the venv active:

    python manage.py create-user alice@example.com
    python manage.py create-user alice@example.com --password s3cret

If --password is omitted you'll be prompted (input hidden). Since v1 has
no registration UI, this is how upload-capable users are provisioned.
"""

import argparse
import getpass
import sys

from sqlalchemy import select

from database import SessionLocal
from models import User
from services.auth import hash_password


def create_user(email: str, password: str) -> int:
    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.email == email)) is not None:
            print(f"User {email!r} already exists.", file=sys.stderr)
            return 1
        user = User(email=email, hashed_password=hash_password(password))
        db.add(user)
        db.commit()
        print(f"Created user {email!r} (id={user.id}).")
        return 0
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Vibedeck management CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    cu = sub.add_parser("create-user", help="Create an upload-capable user")
    cu.add_argument("email")
    cu.add_argument("--password", help="If omitted, you'll be prompted")

    args = parser.parse_args()

    if args.command == "create-user":
        password = args.password or getpass.getpass("Password: ")
        if not password:
            print("Password must not be empty.", file=sys.stderr)
            return 2
        return create_user(args.email, password)

    return 2  # unreachable: subparser is required


if __name__ == "__main__":
    sys.exit(main())
