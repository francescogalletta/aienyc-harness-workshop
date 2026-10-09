"""Command line: `python -m harness check` and `python -m harness events` (SPEC 3.6)."""
import argparse
import sys
import uuid

from . import db
from .config import load_config
from .model import get_model


def check() -> int:
    """Prove the setup end to end: database, model, and one recorded event."""
    config = load_config()
    conn = db.connect(config.db_path)
    db.migrate(conn)
    try:
        model = get_model(config.model_provider)
        response = model.complete(system="", messages=[{"role": "user", "content": "ping"}])
    except Exception as error:
        reason = " ".join(str(error).split())       # keep it to one line
        print(f"check failed: {type(error).__name__}: {reason}", file=sys.stderr)
        return 1
    db.record_event(conn, session_id=uuid.uuid4().hex, kind="harness.check", actor="harness",
                    payload={"provider": config.model_provider, "model": config.model_name,
                             "reply": response.text, "migrations": db.applied_migrations(conn)})
    print(f"provider: {config.model_provider}")
    print(f"model:    {config.model_name}")
    print(f"database: {config.db_path}")
    print(f"reply:    {response.text}")
    return 0


def events() -> int:
    """Print the events table, oldest first."""
    conn = db.connect()
    db.migrate(conn)
    for row in db.list_events(conn):
        print(row["id"], row["ts"], row["kind"], row["actor"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m harness")
    parser.add_argument("command", choices=["check", "events"])
    command = parser.parse_args().command
    return check() if command == "check" else events()


if __name__ == "__main__":
    sys.exit(main())
