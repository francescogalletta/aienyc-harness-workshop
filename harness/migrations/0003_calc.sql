-- Step 2: the calculation registry and everything that runs through it (SPEC 5.5).

CREATE TABLE test_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    module      TEXT NOT NULL,
    fingerprint TEXT NOT NULL,        -- of the files that were tested; "" when some were missing
    reason      TEXT NOT NULL,        -- "build" | "gate" | "status"
    passed      INTEGER NOT NULL,     -- 1 or 0
    report      TEXT NOT NULL         -- JSON
);

CREATE TABLE modules (
    name          TEXT PRIMARY KEY,
    fingerprint   TEXT NOT NULL,      -- of the files as they were when the tests passed
    spec          TEXT NOT NULL,      -- JSON
    test_run_id   INTEGER NOT NULL REFERENCES test_runs(id),   -- the passing run it was registered on
    registered_at TEXT NOT NULL,
    session_id    TEXT NOT NULL
);

CREATE TABLE step_modules (             -- which module carries out which step of the brief
    step_id TEXT PRIMARY KEY,
    module  TEXT NOT NULL REFERENCES modules(name)
);

CREATE TABLE calc_runs (
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

CREATE TABLE inputs (                   -- what the person has told the harness, kept between sessions
    name        TEXT PRIMARY KEY,
    value       TEXT NOT NULL,        -- JSON
    note        TEXT NOT NULL,
    ts          TEXT NOT NULL,
    session_id  TEXT NOT NULL
);
