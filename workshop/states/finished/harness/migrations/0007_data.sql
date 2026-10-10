-- Step 5: the person's account files, summaries of them, and findings (SPEC 9.1).

CREATE TABLE imports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,        -- UTC, ISO 8601
    session_id  TEXT NOT NULL,        -- the command that loaded it
    file        TEXT NOT NULL,        -- the path as given
    sha256      TEXT NOT NULL,        -- of the file's bytes
    account     TEXT NOT NULL,
    sign        TEXT NOT NULL,        -- 'out_negative' | 'out_positive': how the file writes money going out
    report      TEXT NOT NULL         -- JSON: the import dict (SPEC 9.2)
);

CREATE TABLE transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id   INTEGER NOT NULL REFERENCES imports(id),
    account     TEXT NOT NULL,
    date        TEXT NOT NULL,        -- YYYY-MM-DD
    amount      TEXT NOT NULL,        -- exact decimal as text; money out is negative
    description TEXT NOT NULL,
    balance     TEXT,                 -- exact decimal as text; NULL with no balance column or an empty cell
    row         INTEGER NOT NULL      -- the record's number in the file, from 1; the heading row counts
);

CREATE TABLE data_summaries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    session_id  TEXT NOT NULL,        -- the conversation
    inputs      TEXT NOT NULL,        -- JSON: what was asked for, as used (SPEC 9.4)
    output      TEXT NOT NULL,        -- JSON (SPEC 9.4)
    imports     TEXT NOT NULL         -- JSON list of the import ids it read
);

CREATE TABLE findings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ts               TEXT NOT NULL,
    session_id       TEXT NOT NULL,   -- the conversation
    kind             TEXT NOT NULL,   -- 'earlier' | 'data' | 'brief'
    claim            TEXT NOT NULL,
    claim_figure     TEXT NOT NULL,
    reference        TEXT NOT NULL,
    reference_figure TEXT NOT NULL,
    summary_id       INTEGER REFERENCES data_summaries(id),   -- data only
    input_name       TEXT,            -- earlier only
    earlier          TEXT,            -- earlier only: JSON {"value", "note", "ts", "session_id"} of the saved row
    pending_note     TEXT,            -- earlier only: the note of the save_input call that was not saved
    difference       TEXT NOT NULL,   -- the verifier's sentence; '' for earlier
    block            TEXT NOT NULL,   -- what the person is shown, exactly
    options          TEXT NOT NULL,   -- JSON list of the two options
    status           TEXT NOT NULL,   -- 'open' | 'decided'
    decision_id      INTEGER REFERENCES decisions(id),
    choice           TEXT,            -- '1', '2' or 'something else', once decided
    chosen           TEXT             -- the figure to use, once decided; NULL for 'something else'
);
