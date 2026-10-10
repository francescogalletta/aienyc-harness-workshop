-- Layer 2: build and tested calculations (SPEC 4.1). Applied on every connect while layer 2 is on.

CREATE TABLE IF NOT EXISTS test_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    module      TEXT NOT NULL,
    fingerprint TEXT NOT NULL,        -- of the files that were tested; "" when some were missing
    reason      TEXT NOT NULL,        -- "build" | "gate" | "status"
    passed      INTEGER NOT NULL,     -- 1 or 0
    report      TEXT NOT NULL         -- JSON
);

CREATE TABLE IF NOT EXISTS modules (
    name          TEXT PRIMARY KEY,
    fingerprint   TEXT NOT NULL,      -- of the files as they were when the tests passed
    spec          TEXT NOT NULL,      -- JSON
    test_run_id   INTEGER NOT NULL REFERENCES test_runs(id),   -- the passing run it was registered on
    registered_at TEXT NOT NULL,
    session_id    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS step_modules (   -- which module carries out which step of the brief
    step_id TEXT PRIMARY KEY,
    module  TEXT NOT NULL REFERENCES modules(name)
);

CREATE TABLE IF NOT EXISTS calc_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    module      TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    test_run_id INTEGER NOT NULL REFERENCES test_runs(id),
    inputs      TEXT NOT NULL,        -- JSON, as given to the gate
    assumptions TEXT NOT NULL,        -- JSON list of sentences
    expected    TEXT NOT NULL,        -- what the agent said it expected, before the run
    output      TEXT NOT NULL         -- JSON
);

CREATE TABLE IF NOT EXISTS notes (    -- what the person said about their real situation, kept for later
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    step_id     TEXT NOT NULL,        -- the step it is about
    text        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS added_steps (   -- calculation steps added in a conversation, not in the brief
    id          INTEGER PRIMARY KEY AUTOINCREMENT,   -- the step id is 'added_<id>'
    ts          TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    name        TEXT NOT NULL,
    formula     TEXT NOT NULL,
    needs       TEXT NOT NULL,
    produces    TEXT NOT NULL,
    reason      TEXT NOT NULL
);
