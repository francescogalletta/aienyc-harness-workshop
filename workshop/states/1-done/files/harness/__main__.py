"""Command line (SPEC 3.6, 4.5, 4.7 and 4.8): `python -m harness check`, `events`, `ground` and `ui`."""
import argparse
import json
import os
import re
import shutil
import sys
import uuid
from pathlib import Path

from . import db
from .config import EXAMPLE_COPIES, EXAMPLES_DIR, UNKNOWN_EXAMPLE, load_config
from .model import get_model, resolve_provider


def check() -> int:
    """Prove the setup end to end: database, model, and one recorded event."""
    config = load_config()
    conn = db.connect(config.db_path)
    db.migrate(conn)
    try:
        provider = resolve_provider(config.model_provider)
        model = get_model(provider)
        response = model.complete(
            system="This is a connection test.",
            messages=[{"role": "user", "content": "Reply with the single word: pong"}])
    except Exception as error:
        reason = " ".join(str(error).split())       # keep it to one line
        print(f"check failed: {type(error).__name__}: {reason}", file=sys.stderr)
        return 1
    event_id = db.record_event(
        conn, session_id=uuid.uuid4().hex, kind="harness.check", actor="harness",
        payload={"provider": provider, "model": config.model_name,
                 "reply": response.text, "migrations": db.applied_migrations(conn)})
    print(f"provider: {provider}")
    print(f"model:    {config.model_name}")
    print(f"database: {config.db_path}")
    print(f"reply:    {response.text}")
    print(f"Setup works: the model replied and the check was saved as event {event_id}.")
    return 0


def events() -> int:
    """Print the events table, oldest first."""
    conn = db.connect()
    db.migrate(conn)
    for row in db.list_events(conn):
        print(row["id"], row["ts"], row["kind"], row["actor"])
    return 0


OPENING = ("What do you want this harness to help you with?\n"
           "Describe it in your own words. A few sentences is plenty.")
HOW_TO = ("Answer each question and press Enter. Type /wrap to finish with what we have, "
          "or /quit to stop and carry on later with --resume.")


def ground(resume: bool, max_questions: int) -> int:
    """Run the grounding interview in the terminal and write the domain brief."""
    from .grounding import ResearchDesk, get_researcher, new_state, run_interview

    config = load_config()
    conn = db.connect(config.db_path)
    db.migrate(conn)
    state_path = config.db_path.parent / "grounding_state.json"

    def ask(text: str) -> str:
        print(f"\n{text}\n")
        try:
            return input("> ")
        except EOFError:        # no more input: treat it as stopping for now
            return "/quit"

    if resume:
        if not state_path.exists():
            print("There is no interview to resume. Start one with: python -m harness ground",
                  file=sys.stderr)
            return 1
        state = json.loads(state_path.read_text(encoding="utf-8"))
        print(f"Resuming the interview. {HOW_TO}")
    else:
        print(HOW_TO)
        opening = ask(OPENING).strip()
        if not opening or opening == "/quit":
            return 1
        state = new_state(uuid.uuid4().hex, opening)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")   # resumable from here on
        db.record_event(conn, session_id=state["session_id"], kind="grounding.answer",
                        actor="person", payload={"text": opening})

    try:
        desk = ResearchDesk(get_researcher(), conn)         # remembers every lookup (SPEC 4.6)
        saved = run_interview(model=get_model(), researcher=desk, ask=ask, conn=conn,
                              state=state, brief_dir=config.brief_dir, state_path=state_path,
                              max_questions=max_questions)
    except Exception as error:
        reason = " ".join(str(error).split())
        print(f"interview stopped: {type(error).__name__}: {reason}", file=sys.stderr)
        print("Nothing is lost. Carry on with: python -m harness ground --resume", file=sys.stderr)
        return 1

    if saved is None:
        print("\nStopped. Carry on later with: python -m harness ground --resume")
        return 0
    print(f"\nBrief saved ({saved['status']}):\n  {saved['page']}\n  {saved['json']}")
    return 0 if saved["status"] == "confirmed" else 1


def ui(port: int, browser: bool, max_questions: int) -> int:
    """Run the grounding interview in a local web page, until interrupted."""
    import webbrowser

    from .ui.server import make_server
    from .ui.session import GroundingSession

    config = load_config()
    conn = db.connect(config.db_path)
    db.migrate(conn)
    session = GroundingSession(config, conn, max_questions=max_questions)   # resumes an unfinished interview
    try:
        server = make_server(session, port)
    except OSError as error:
        reason = " ".join(str(error).split())
        print(f"could not start on port {port}: {reason}", file=sys.stderr)
        return 1
    address = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"The grounding interview is at {address}", flush=True)
    print("Press Ctrl+C to stop. An unfinished interview carries on the next time you run this.", flush=True)
    if browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


def known_example(name: str) -> bool:
    return bool(re.match(r"^[a-z][a-z0-9_]*$", name)) and (EXAMPLES_DIR / name).is_dir()


EXAMPLE_COPIED = ("Copied the example '{name}' to {folder}. What you change there stays there; "
                  "delete that folder to start the example again.")
LEGACY_COMMANDS = ("ground", "ui", "build", "modules", "ask", "adopt", "work")
LEGACY_LAYOUT = ("This copy has brief/ or modules/ at the top, but the harness now keeps them in my/. "
                 "Move each one you have: mkdir -p my && git mv brief my/brief && git mv modules my/modules "
                 "(plain mv if they are not committed). Then run the command again.")


def copy_example(name: str) -> None:
    """Example mode works on a copy of the example's brief and modules, made once (SPEC 4.8)."""
    copied = False
    for part in ("brief", "modules"):
        source, target = EXAMPLES_DIR / name / part, EXAMPLE_COPIES / name / part
        if source.is_dir() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
            copied = True
    if copied:
        print(EXAMPLE_COPIED.format(name=name, folder=EXAMPLE_COPIES / name), file=sys.stderr)


def legacy_layout() -> bool:
    """True for an older copy: brief/ or modules/ at the top and nothing in my/ (SPEC 4.5)."""
    if any(os.environ.get(name) for name in ("HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR", "HARNESS_EXAMPLE")):
        return False
    if Path("my/brief").exists() or Path("my/modules").exists():
        return False
    return Path("brief").is_dir() or Path("modules").is_dir()


def unknown_example(name: str) -> None:
    names = sorted(path.name for path in EXAMPLES_DIR.iterdir() if path.is_dir()) if EXAMPLES_DIR.is_dir() else []
    print(UNKNOWN_EXAMPLE.format(name=name, names=", ".join(names) or "(none)"), file=sys.stderr)


def main() -> int:
    config = load_config()
    if config.example is not None and not known_example(config.example):
        unknown_example(config.example)
        return 1
    if config.example is not None:
        copy_example(config.example)
    parser = argparse.ArgumentParser(prog="python -m harness")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="prove the setup works end to end")
    commands.add_parser("events", help="print the recorded events")
    grounding = commands.add_parser("ground", help="run the grounding interview")
    grounding.add_argument("--resume", action="store_true", help="carry on an interview you stopped")
    grounding.add_argument("--max-questions", type=int, default=12)
    page = commands.add_parser("ui", help="run the grounding interview in a local web page")
    page.add_argument("--port", type=int, default=8765)
    page.add_argument("--no-browser", action="store_true", help="do not open the page in the browser")
    page.add_argument("--max-questions", type=int, default=12)
    args = parser.parse_args()
    if args.command in LEGACY_COMMANDS and legacy_layout():
        print(LEGACY_LAYOUT, file=sys.stderr)
        return 1
    if args.command == "check":
        return check()
    if args.command == "events":
        return events()
    if args.command == "ui":
        return ui(args.port, not args.no_browser, args.max_questions)
    return ground(args.resume, args.max_questions)


if __name__ == "__main__":
    sys.exit(main())
