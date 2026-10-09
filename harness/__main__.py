"""Command line (SPEC 3.6, 4.5, 4.7 and 5.10): `python -m harness check`, `events`, `ground`, `ui`,
`build`, `modules` and `ask`."""
import argparse
import json
import sys
import uuid
from datetime import date

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
        response = model.complete(
            system="This is a connection test.",
            messages=[{"role": "user", "content": "Reply with the single word: pong"}])
    except Exception as error:
        reason = " ".join(str(error).split())       # keep it to one line
        print(f"check failed: {type(error).__name__}: {reason}", file=sys.stderr)
        return 1
    event_id = db.record_event(
        conn, session_id=uuid.uuid4().hex, kind="harness.check", actor="harness",
        payload={"provider": config.model_provider, "model": config.model_name,
                 "reply": response.text, "migrations": db.applied_migrations(conn)})
    print(f"provider: {config.model_provider}")
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


ALL_BUILT = "Every calculation step has a tested module."
SOME_MISSING = ("Some calculation steps have no tested module yet. "
                "Run python -m harness build again to carry on.")
NO_MODULES = "No modules are registered yet. Build them with: python -m harness build"
NONE_BUILT = "No modules are built yet. Build them first with: python -m harness build"
OUTCOMES = {"built": "built", "reused": "reused", "kept": "already built"}


def terminal_ask(text: str) -> str:
    """Show text between blank lines and read the answer. The end of input counts as /quit."""
    print(f"\n{text}\n")
    try:
        return input("> ")
    except EOFError:
        return "/quit"


def build(rebuild: str | None) -> int:
    """Build a tested module for each calculation step of the brief (SPEC 5.10)."""
    from .calc.builder import build as build_modules
    from .calc.builder import load_brief

    config = load_config()
    conn = db.connect(config.db_path)
    db.migrate(conn)
    try:
        brief = load_brief(config.brief_dir)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    calculations = [step for step in brief["process"] if step.get("kind") == "calculation"]
    if not calculations and rebuild is None:
        print("The brief has no calculation steps.")
        return 0

    try:
        results = build_modules(model=get_model(), conn=conn, brief=brief, ask=terminal_ask,
                                session_id=uuid.uuid4().hex, rebuild=rebuild)
    except Exception as error:
        reason = " ".join(str(error).split())
        if rebuild is not None and type(error) is ValueError:       # an unknown module, or a step the brief lacks
            print(reason, file=sys.stderr)
        else:
            print(f"build stopped: {type(error).__name__}: {reason}", file=sys.stderr)
        return 1

    print()
    for result in results:
        if result["outcome"] == "not_built":
            print(f"{result['step']}: not built ({result['reason']})")
        else:
            print(f"{result['step']} -> {result['module']} ({OUTCOMES[result['outcome']]})")
    if rebuild is not None:
        return 0 if results and results[0]["outcome"] == "built" else 1
    if len(results) == len(calculations) and all(r["outcome"] != "not_built" for r in results):
        print(ALL_BUILT)
        return 0
    print(SOME_MISSING)
    return 1


def modules() -> int:
    """List the registered modules, each after a fresh test run (SPEC 5.10)."""
    from .calc.gate import run_tests
    from .calc.registry import file_status, list_modules

    conn = db.connect()
    db.migrate(conn)
    session_id = uuid.uuid4().hex
    registered = list_modules(conn)
    if not registered:
        print(NO_MODULES)
        return 0
    healthy = True
    for module in registered:
        status = file_status(conn, module["name"])
        run = run_tests(conn, module["name"], reason="status", session_id=session_id)
        healthy = healthy and status == "unchanged" and run["passed"]
        print(f"{module['name']}  steps: {', '.join(module['steps']) or '-'}  files: {status}  "
              f"tests: {'passed' if run['passed'] else 'failed'}  fingerprint: {module['fingerprint'][:12]}")
    if healthy:
        return 0
    print("Rebuild a module with: python -m harness build --rebuild NAME")
    return 1


def ask_about_plan(words: list[str]) -> int:
    """Answer questions about the plan, with tested modules (SPEC 5.10)."""
    from .calc.agent import run_agent
    from .calc.builder import load_brief
    from .calc.registry import list_modules

    config = load_config()
    conn = db.connect(config.db_path)
    db.migrate(conn)
    try:
        brief = load_brief(config.brief_dir)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    if not list_modules(conn):
        print(NONE_BUILT, file=sys.stderr)
        return 1
    print("Ask about your plan. Type /quit to stop.")
    try:
        run_agent(model=get_model(), conn=conn, brief=brief, ask=terminal_ask,
                  session_id=uuid.uuid4().hex, question=" ".join(words), today=date.today())
    except Exception as error:
        reason = " ".join(str(error).split())
        print(f"ask stopped: {type(error).__name__}: {reason}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
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
    building = commands.add_parser("build", help="build a tested module for each calculation step")
    building.add_argument("--rebuild", metavar="NAME", help="build this registered module again")
    commands.add_parser("modules", help="list the registered modules and test them now")
    asking = commands.add_parser("ask", help="ask a question about your plan")
    asking.add_argument("question", nargs="*")
    args = parser.parse_args()
    if args.command == "check":
        return check()
    if args.command == "events":
        return events()
    if args.command == "build":
        return build(args.rebuild)
    if args.command == "modules":
        return modules()
    if args.command == "ask":
        return ask_about_plan(args.question)
    if args.command == "ui":
        return ui(args.port, not args.no_browser, args.max_questions)
    return ground(args.resume, args.max_questions)


if __name__ == "__main__":
    sys.exit(main())
