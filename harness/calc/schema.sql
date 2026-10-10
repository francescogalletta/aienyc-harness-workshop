-- Layer 2: build and tested calculations (SPEC 4.1). Applied on every connect while layer 2 is on.

CREATE TABLE IF NOT EXISTS test_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    module      TEXT NOT NULL,
    fingerprint TEXT NOT NULL,        -- of the files that were tested; "" when some were missing
    reason      TEXT NOT NULL,        -- "build" | "gate" | "status" | "adopt"
    passed      INTEGER NOT NULL,     -- 1 or 0
    report      TEXT NOT NULL         -- JSON
);

CREATE TABLE IF NOT EXISTS modules (
    name          TEXT PRIMARY KEY,
    fingerprint   TEXT NOT NULL,      -- of the files as they were when the tests passed
    spec          TEXT NOT NULL,      -- JSON
    test_run_id   INTEGER NOT NULL REFERENCES test_runs(id),   -- the passing run it was registered on
    registered_at TEXT NOT NULL,
    session_id    TEXT NOT NULL,
    step_fingerprint TEXT NOT NULL DEFAULT ''   -- of the plan's step it was built for (SPEC 4.4); '' unknown
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

CREATE TABLE IF NOT EXISTS build_steps (   -- what the last build or adoption of each calculation step gave (SPEC 4.2)
    step_id              TEXT PRIMARY KEY,
    status               TEXT NOT NULL,       -- "built" | "not_built"; "stale", "building", "none" are worked out
    module               TEXT,                -- the module that carries the step out, when there is one
    spec                 TEXT,                -- JSON, or NULL when no spec was accepted
    departures           TEXT NOT NULL,       -- JSON list of sentences
    departures_confirmed INTEGER NOT NULL,    -- 1 or 0
    examples             TEXT NOT NULL,       -- JSON list of Example (ARCHITECTURE 3.3), checked or left out
    disagreement         TEXT NOT NULL,       -- JSON list of {"n", "expected", "code_gives"}
    reason               TEXT NOT NULL,       -- why not built; "" otherwise
    step_fingerprint     TEXT NOT NULL,       -- of the plan's step when this row was written
    ts                   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS example_confirmations (   -- the person confirmed or corrected an example
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    step_id TEXT NOT NULL,
    n       INTEGER NOT NULL,
    answer  TEXT NOT NULL                 -- JSON: the answer the person gave or confirmed
);
