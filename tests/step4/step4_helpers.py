"""Shared by the step 4 tests (SPEC section 8: human in the loop).

The fixed strings and the blocks below are copied from the SPEC on purpose: the tests check the harness against the
contract, not against its own constants. The helpers of steps 2 and 3 (a small brief, two example modules, script
builders, a recording person, a running server) are reused: this file puts those folders on the import path.

The example is the savings goal of the step 2 helpers. Step s1 (monthly_surplus) and step s3 (months_to_goal) have
modules; step s2 is the one judgment. Their descriptions, as the gate block shows them, are `SURPLUS` and `MONTHS`.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "step3"))

import step3_helpers as s3                                   # noqa: E402  (after the path is set)
from step3_helpers import h                                  # noqa: E402
from harness.model import ScriptedModel                      # noqa: E402

SESSION = h.SESSION
DAY = h.DAY
QUESTION = h.QUESTION
TODAY = DAY.isoformat()

# ---- fixed strings: 8.2 ------------------------------------------------------------------------------------------

GATE_INTRO = "Before working this out, the assistant would take some things as given that you have not confirmed:"
GATE_QUESTION = ("Go ahead on these? Type yes to go ahead. If something is not right, say so in your own words: nothing "
                 "runs, and the assistant hears what you said. Type /aside to talk it through on the side first.")
GATE_UNBACKED = h.GATE_UNBACKED
ASK_FIRST = h.ASK_FIRST

# ---- fixed strings: 8.3 ------------------------------------------------------------------------------------------

DECISION_INTRO = "Only you can decide this:"
DECISION_INTRO_STEP = "Only you can decide this. It is step {step} of the plan: {name}."
DECISION_SUGGESTS = "The assistant suggests {n}: {why}"
DECISION_QUESTION = ("Type the number of your choice, or say in your own words what you want instead. Type /aside to "
                     "talk it through on the side first.")
DECISION_QUESTION_SUGGESTED = ("Type the number of your choice, or yes to take the suggestion, or say in your own words "
                               "what you want instead. Type /aside to talk it through on the side first.")
MAX_DECISIONS = 2
ONE_DECISION = "Only one ask_decision is handled per reply. Wait for the answer to the first."
TOO_MANY_DECISIONS = ("No more decisions can be put to the person until their next message. Tell the person plainly "
                      "what is still to decide.")
DECISION_NO_QUESTION = "Say the question in plain words."
DECISION_OPTIONS = "Give two to four different options, each in plain words."
DECISION_NO_STEP = "There is no step {step} in the process."
DECISION_BAD_RECOMMENDATION = "recommendation must be the number of one of the options, or left out."
DECISION_NO_WHY = "Say in one sentence why you recommend it."
DECISION_RUNS = "runs must be a list of run ids. It may be empty."
DECISION_UNKNOWN_RUNS = "These runs are not in this conversation: {runs}."
SOMETHING_ELSE = "something else"
KINDS = ("assumptions", "judgment", "build", "finding")          # (step 5) a fourth kind

# ---- fixed strings: 8.5, 8.7 -------------------------------------------------------------------------------------

MAX_ASIDE_TURNS = 6
MAX_ASIDE_CALLS = 5
MAX_ASIDE_LOOKUPS = 3
MAX_QUERY_LENGTH = 100
ASIDE_MARK = "aside | "
ASIDE_PROMPT = "aside> "
NOTHING_WORDS = ("no", "n", "nothing", "no.")
ASIDE_OPEN = ("---- Side conversation. The main conversation waits, and will not see what is said here. Type /back to "
              "go back to it. ----")
ASIDE_CLOSE = "---- Back to the main conversation. ----"
ASIDE_FIRST = "What would you like to talk through?"
ASIDE_NESTED = "You are already in a side conversation. Type /back to go back to the main one."
ASIDE_THINKING = "(thinking)"
ASIDE_LOOKING_UP = "(looking up: {query})"
ASIDE_LIMIT = "That is as far as one side conversation goes: {limit} messages."
ASIDE_CARRY = ("Before you go back: is there anything the main conversation should know? Type it in your own words, "
               "and it is passed on exactly as you write it. Type no to pass on nothing.")
ASIDE_CARRIED = ("[harness] The person stepped aside for a side conversation that you did not see. They asked for this "
                 "to be passed on, in their own words:\n{text}")
ASIDE_NUMBERS = ("[harness] Your reply was not shown. These numbers are not in what you were given, the person's "
                 "messages here or a lookup: {numbers}. Do not work numbers out yourself. Leave the number out, or tell "
                 "the person the main conversation can work it out with a tested module. Then reply again.")
LOOKUP_TERM = "Send only the term to look up, at most {limit} characters."
LOOKUP_FAILED = "The lookup failed: {error}"
ASIDE_LOOKUP_LIMIT = "No more lookups in this side conversation. Answer with what you have."
NO_DECISIONS = "No decisions are recorded yet."

ACCEPT_WORDS = h.ACCEPT_WORDS

# ---- the modules and the words a gate shows ----------------------------------------------------------------------

SURPLUS = h.surplus_spec()["description"]            # "The money left over each month after spending."
MONTHS = h.months_spec()["description"]
YEARLY = h.yearly_spec()["description"]
ASSUME = ["Spending stays the same each month."]
OTHER_ASSUME = ["Income does not change during the year."]
EXPECT = "what comes in less what goes out"
THINKING = ("say", "  (thinking)")

SURPLUS_PLANS = {"steps": ["s1"], "plan": s3.plan_text(h.surplus_spec())}
MONTHS_PLANS = {"steps": ["s3"], "plan": s3.plan_text(h.months_spec())}
PLANS = {"monthly_surplus": SURPLUS_PLANS, "months_to_goal": MONTHS_PLANS}

TWO_CASES = ("I earn 5000 and spend 3000 a month, or 6000 and 4000 in a good month. What is left each month? "
             "I want to reach 10000 and could put 2000 a month towards it.")


# ---- the blocks of 8.2 and 8.3, worked out here -------------------------------------------------------------------

def one_line(text):
    return " ".join(text.split())


def gate_block(*items):
    """The gate block for items given as (description, assumptions, expected)."""
    lines = [GATE_INTRO]
    for k, (description, assumptions, expected) in enumerate(items, 1):
        lines += [f"  {k}. {one_line(description)}", "     Taking as given:"]
        seen = set()
        for sentence in assumptions:
            text = one_line(sentence)
            if text == "" or text.casefold() in seen:
                continue
            seen.add(text.casefold())
            lines.append(f"       - {text}")
        lines.append(f"     Expecting: {one_line(expected)}")
    return "\n".join(lines)


def surplus_item(assumptions=ASSUME, expected=EXPECT):
    return (SURPLUS, assumptions, expected)


def months_item(assumptions=ASSUME, expected=EXPECT):
    return (MONTHS, assumptions, expected)


def decision_block(question, options, recommendation=None, why="", step=None):
    """The decision block; `step` is a step dict (with id and name) or None."""
    if step is None:
        lines = [DECISION_INTRO]
    else:
        lines = [DECISION_INTRO_STEP.format(step=h.label(step["id"]), name=one_line(step["name"]))]
    lines.append(f"  {one_line(question)}")
    lines += [f"    {n}. {one_line(option)}" for n, option in enumerate(options, 1)]
    if recommendation is not None:
        lines.append("  " + DECISION_SUGGESTS.format(n=recommendation, why=one_line(why)))
    return "\n".join(lines)


def marked(text):
    return "\n".join(ASIDE_MARK + line for line in text.split("\n"))


def step_of(brief, step_id):
    return next(step for step in brief["process"] if step["id"] == step_id)


# ---- the tool calls ------------------------------------------------------------------------------------------------

DROP = object()                       # a key to leave out of the arguments of a call


def ask_decision_arguments(**changes):
    arguments = {"question": "Should the date stay or move?", "options": ["Keep the date", "Move the date"], "runs": []}
    arguments.update(changes)
    return {key: value for key, value in arguments.items() if value is not DROP}


def ask_decision(**changes):
    return h.tool("ask_decision", ask_decision_arguments(**changes))


def run_args(module="monthly_surplus", inputs=None, assumptions=ASSUME, expected=EXPECT):
    """The arguments of a run_module call (assumptions, by default, so the call needs a yes)."""
    return h.run_module(module, inputs, assumptions, expected)["tool_calls"][0]["arguments"]


def run(module="monthly_surplus", inputs=None, assumptions=ASSUME, expected=EXPECT):
    return h.run_module(module, inputs, assumptions, expected)


def run_pair(*calls, text=""):
    """One reply holding several tool calls, each given as a tool entry (as `run` and `ask_decision` give them)."""
    return {"text": text, "tool_calls": [c for entry in calls for c in entry["tool_calls"]]}


def side(text):
    """A reply of the side assistant."""
    return h.say_text(text)


def look_up(query="sinking fund"):
    return {"tool_calls": [{"name": "look_up", "arguments": {"query": query}}]}


def look_ups(*queries):
    return {"tool_calls": [{"name": "look_up", "arguments": {"query": q}} for q in queries]}


def result_of(model, call_index, position=-1):
    return json.loads(h.tool_message(model, call_index, position)["content"])


# ---- who is talking ------------------------------------------------------------------------------------------------

def aside_prompt_first_line():
    return h.prompt_text("aside.md").strip().splitlines()[0]


def role_of(system):
    """spec_writer, example_writer, example_helper, module_writer, aside or analyst."""
    if system.strip().startswith(aside_prompt_first_line()):
        return "aside"
    return h.role_of(system)


class Model(ScriptedModel):
    """A scripted model that notes each call, by role, in the person's log."""

    def __init__(self, script, person):
        super().__init__(script)
        self.person = person

    def complete(self, *, system, messages, tools=()):
        self.person.log.append(("call", role_of(system)))
        return super().complete(system=system, messages=messages, tools=tools)

    def roles(self):
        return [role_of(call["system"]) for call in self.calls]

    def of(self, role):
        return [call for call in self.calls if role_of(call["system"]) == role]


def quiet(person):
    """The person's log without the progress line of the main conversation."""
    return [entry for entry in person.log if entry != THINKING]


def asked_of(person):
    return [text for kind, text in person.log if kind == "ask"]


def aside_system(context):
    return h.prompt_text("aside.md").replace("{context}", context)


def aside_context(brief, *, runs=(), decisions=(), looking_at=None, plans=None, today=TODAY):
    """The context of a side conversation (8.5), worked out here from its nine sections."""
    return h.sections(
        ("today", today), ("goal", brief["goal"]), ("glossary", brief["glossary"]),
        ("particulars", brief["particulars"]), ("process", brief["process"]),
        ("plans", PLANS if plans is None else plans), ("runs in this conversation", list(runs)),
        ("decisions in this conversation", list(decisions)), ("looking at", looking_at))


def example_block(k, n, example, spec):
    """The block of one worked example with scalar values (5.7)."""
    lines = [f"Example {k} of {n}"]
    for item in spec["inputs"]:
        lines.append(f"  {item['name'].replace('_', ' ')}: {example['inputs'][item['name']]}")
    lines.append(f"  Working: {example['working']}")
    lines.append(f"  Proposed answer: {example['expected']}")
    return "\n".join(lines)


# ---- a researcher that does not leave the machine ------------------------------------------------------------------

class FakeResearcher:
    """Answers a few terms, fails on others, and remembers exactly what it was asked."""

    def __init__(self, known=None, failing=()):
        self.known = known or {"sinking fund": "Money set aside regularly for a known future cost.",
                               "emergency fund": "Money kept aside for surprises."}
        self.failing = set(failing)
        self.queries = []

    def look_up(self, query):
        from harness.grounding import Lookup
        self.queries.append(query)
        if query in self.failing:
            raise RuntimeError("the researcher is down")
        if query in self.known:
            return Lookup(query, True, name=query, definition=self.known[query],
                          sources=({"title": "A page about " + query, "url": "https://example.org/" + query.replace(" ", "-")},),
                          origin="fake")
        return Lookup(query, False, origin="fake")


def make_desk(conn, researcher=None):
    from harness.grounding.research import ResearchDesk
    researcher = researcher or FakeResearcher()
    return ResearchDesk(researcher, conn), researcher


# ---- reading what was recorded -------------------------------------------------------------------------------------

def decision_rows(conn):
    return h.rows(conn, "decisions")


def decisions_of(conn, session_id=None):
    from harness.calc.decisions import list_decisions
    return list_decisions(conn, session_id=session_id)


def aside_events(conn):
    return [(kind, actor, payload) for kind, actor, payload in h.events(conn) if kind.startswith("aside.")]


def conversation_kinds(conn):
    """The event kinds of the conversation: those after its ask.started (the modules were installed before it)."""
    names = h.kinds(conn)
    return names[names.index("ask.started") + 1:]


def kinds_between(conn, first, last):
    """The event kinds from the first `first` to the first `last` after it, both included."""
    names = h.kinds(conn)
    start = names.index(first)
    return names[start:names.index(last, start) + 1]


# ---- a world for the evidence tests ---------------------------------------------------------------------------------

CHAT = "chat-4"
BONUS = "I also get a bonus of 1,200 in June."
SET_ASIDE = "Put 3,333 aside"


def story_script():
    """The model replies of the story told by `tell_the_story`."""
    return [
        run(assumptions=ASSUME, expected="5000 less 3000"),
        side("Steady means it does not change from month to month."),
        ask_decision(step="s2", question="How much of the surplus should be set aside?",
                     options=["Set aside all of 2,000", "Set aside the bonus of 1,200"], recommendation=1,
                     why="It keeps things simple.", runs=[1]),
        h.say_text("You will set 3,333 aside, from the 2,000 left each month."),
    ]


def story_answers():
    return ["/aside What does steady mean here?", "/back", BONUS, "yes", SET_ASIDE, "/quit"]


def tell_the_story(conn, brief, *, session_id=CHAT, today=DAY, desk=None):
    """A conversation with a gate (a side conversation opened at it, a sentence carried back), a run, a judgment
    answered in the person's own words, and a reply. Returns (model, person)."""
    from harness.calc import agent

    person = h.Person(*story_answers())
    model = Model(story_script(), person)
    agent.run_agent(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say, session_id=session_id,
                    question=QUESTION, today=today, desk=desk)
    return model, person
