"""Command line (SPEC 2.5): `python -m harness check`, `events`, `ui`, and the commands of the
enabled layers, found by discovery."""
import argparse
import re
import shutil
import sys
import uuid

from . import db
from .config import EXAMPLE_COPIES, EXAMPLES_DIR, UNKNOWN_EXAMPLE, load_config
from .layers import enabled
from .model import get_model, resolve_provider

EXAMPLE_COPIED = ("Copied the example '{name}' to {folder}. What you change there stays there; "
                  "delete that folder to start the example again.")
UI_ADDRESS = "The harness is at {address}"
UI_STOP = "Press Ctrl+C to stop. Your work is kept; it is there again the next time you run this."


def check(args) -> int:
    """Prove the setup end to end: database, model, and one recorded event."""
    config = load_config()
    conn = db.connect(config.db_path)
    db.apply_schemas(conn, enabled(config))
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
        conn, session_id=uuid.uuid4().hex, kind="core.check", actor="harness",
        payload={"provider": provider, "model": config.model_name, "reply": response.text})
    print(f"provider: {provider}")
    print(f"model:    {config.model_name}")
    print(f"database: {config.db_path}")
    print(f"reply:    {response.text}")
    print(f"Setup works: the model replied and the check was saved as event {event_id}.")
    return 0


def events(args) -> int:
    """Print the events table, oldest first."""
    config = load_config()
    conn = db.connect(config.db_path)
    db.apply_schemas(conn, enabled(config))
    for row in db.list_events(conn):
        print(row["id"], row["ts"], row["kind"], row["actor"])
    return 0


def ui(args) -> int:
    """Serve the page on a Session until interrupted."""
    import webbrowser

    from .core import Session
    from .ui.server import make_server

    session = Session(load_config())
    try:
        server = make_server(session, args.port)
    except OSError as error:
        session.close()
        print(f"could not start on port {args.port}: {' '.join(str(error).split())}", file=sys.stderr)
        return 1
    address = f"http://127.0.0.1:{server.server_address[1]}/"
    print(UI_ADDRESS.format(address=address), flush=True)
    print(UI_STOP, flush=True)
    if not args.no_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
        session.close()
    return 0


def _ui_arguments(parser) -> None:
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="do not open the page in the browser")


BASE_COMMANDS = {
    "check": ("prove the setup works end to end", check, None),
    "events": ("print the recorded events", events, None),
    "ui": ("open the harness in a local web page", ui, _ui_arguments),
}


def known_example(name: str) -> bool:
    return bool(re.match(r"^[a-z][a-z0-9_]*$", name)) and (EXAMPLES_DIR / name).is_dir()


def copy_example(name: str) -> None:
    """Example mode works on a copy of the example's brief and modules, made once."""
    copied = False
    for part in ("brief", "modules"):
        source, target = EXAMPLES_DIR / name / part, EXAMPLE_COPIES / name / part
        if source.is_dir() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
            copied = True
    if copied:
        print(EXAMPLE_COPIED.format(name=name, folder=EXAMPLE_COPIES / name), file=sys.stderr)


def unknown_example(name: str) -> None:
    names = sorted(path.name for path in EXAMPLES_DIR.iterdir() if path.is_dir()) if EXAMPLES_DIR.is_dir() else []
    print(UNKNOWN_EXAMPLE.format(name=name, names=", ".join(names) or "(none)"), file=sys.stderr)


def parser_for(layers) -> argparse.ArgumentParser:
    """The base commands, then each enabled layer's, in layer order."""
    parser = argparse.ArgumentParser(prog="python -m harness")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, (help_text, run, arguments) in BASE_COMMANDS.items():
        sub = commands.add_parser(name, help=help_text)
        if arguments is not None:
            arguments(sub)
        sub.set_defaults(run=run)
    for layer in layers:
        for name, command in layer.commands.items():
            sub = commands.add_parser(name, help=command.help)
            if command.arguments is not None:
                command.arguments(sub)
            sub.set_defaults(run=command.run)
    return parser


def main(argv=None) -> int:
    try:
        config = load_config()
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    if config.example is not None:
        if not known_example(config.example):
            unknown_example(config.example)
            return 1
        copy_example(config.example)
    args = parser_for(enabled(config)).parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
